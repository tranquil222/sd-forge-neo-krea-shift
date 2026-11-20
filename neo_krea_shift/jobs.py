"""Per-request list expansion and per-sampling-pass ramp integration."""
from copy import copy
from dataclasses import replace
from functools import wraps
import inspect

from .runtime import set_krea_shift
from .schedules import Options, FIXED, RAMP, blend_intervals, metadata, parse_values, shift_value


def options_for(p):
    override = getattr(p, "_neo_krea_shift_options", None)
    options = override
    if options is None:
        runner = getattr(p, "scripts", None)
        for script in getattr(runner, "alwayson_scripts", ()):
            if getattr(script, "neo_krea_shift_controls", False):
                options = Options.read(*p.script_args[script.args_from:script.args_to])
                break
    options = options or Options(enabled=False)
    # Native XYZ axes run after preparation. A Shift axis varies ramp From;
    # prompt-only axes leave the prepared starting value unchanged.
    if options.enabled and options.mode == RAMP and getattr(p, "_neo_shift_prepared", False) and getattr(p, "is_xyz_pass", False):
        options = replace(options, start=shift_value(p.distilled_cfg_scale))
    return options


def prepare_request(p, options):
    """Apply plugin fields once, before selectable scripts apply their axes."""
    if not options.enabled or getattr(p, "_neo_shift_prepared", False):
        return
    if options.mode == RAMP:
        p.distilled_cfg_scale = options.start
    elif options.fixed is not None:
        p.distilled_cfg_scale = options.fixed
    if options.hr_fixed is not None and hasattr(p, "hr_distilled_cfg"):
        p.hr_distilled_cfg = options.hr_fixed
    p._neo_shift_prepared = True


def clone_job(p, options):
    child = copy(p)
    for name in ("extra_generation_params", "override_settings"):
        setattr(child, name, dict(getattr(p, name, {})))
    if hasattr(p, "styles"):
        child.styles = p.styles[:]
    # Do not mutate a parent's list when an extension extends script arguments.
    if isinstance(getattr(p, "script_args", None), list):
        child.script_args = p.script_args[:]
    child._neo_krea_shift_options = options
    return child


def combine_results(results):
    """Preserve every returned grid/sample and its own gallery-paste metadata."""
    if not results:
        return None
    result = copy(results[0])
    fields = ("all_prompts", "all_negative_prompts", "all_seeds", "all_subseeds", "infotexts")
    fallback = ("prompt", "negative_prompt", "seed", "subseed", "info")
    result.images, result.extra_images = [], []
    for field in fields:
        setattr(result, field, [])
    for part in results:
        first = getattr(part, "index_of_first_image", 0)
        for i, image in enumerate(part.images):
            result.images.append(image)
            for field, default in zip(fields, fallback):
                values = getattr(part, field, [])
                index = i if field == "infotexts" else max(0, i - first)
                getattr(result, field).append(values[index] if index < len(values) else getattr(part, default, ""))
        result.extra_images.extend(getattr(part, "extra_images", []))
    result.index_of_first_image = 0
    result.comments = "\n".join(filter(None, (getattr(part, "comments", "") for part in results)))
    return result


class JobHooks:
    def __init__(self, runtime, processing, scripts, sampler_class, img2img_steps):
        self.runtime = runtime
        self.processing = processing
        self.scripts = scripts
        self.sampler_class = sampler_class
        self.img2img_steps = img2img_steps

    def is_krea(self, p):
        return isinstance(p.sd_model, self.runtime.engine_class)

    def sequence(self, p, options, callback):
        self.processing.fix_seed(p)
        results = []
        for value in parse_values(options.values):
            state = self.runtime.shared.state
            if getattr(state, "interrupted", False) or getattr(state, "stopping_generation", False):
                break
            child_options = replace(options, mode=RAMP if options.mode == RAMP else FIXED,
                                    multiple=False, values="", fixed=value,
                                    start=value if options.mode == RAMP else options.start)
            child = clone_job(p, child_options)
            child.distilled_cfg_scale = value
            child.extra_generation_params["Krea Shift mode"] = child_options.mode
            child.extra_generation_params["Krea Shift list"] = options.values
            part = callback(child)
            if part is not None:
                results.append(part)
        # Return a valid empty Processed on interruption before the first image.
        return combine_results(results) or self.processing.Processed(p, [], p.seed, "Interrupted")

    def install(self):
        hooks = self
        runtime = self.runtime
        original_inner = self.processing.process_images_inner

        @wraps(original_inner)
        def inner(p, *args, **kwargs):
            if not hooks.is_krea(p):
                return original_inner(p, *args, **kwargs)
            options = options_for(p)
            prepare_request(p, options)
            if options.run_multiple:
                # Each child re-enters for its ramp, but cannot expand again.
                return hooks.sequence(p, options, lambda child: inner(child, *args, **kwargs))
            p.extra_generation_params = dict(p.extra_generation_params)
            p.extra_generation_params.update(metadata(options, []))
            if options.enabled and hasattr(p, "hr_distilled_cfg"):
                # Preserve an actual XYZ Hires Shift override, not the original UI field.
                p.extra_generation_params["Krea Shift hires fixed"] = p.hr_distilled_cfg
            if options.enabled and options.mode == RAMP:
                names = [getattr(p, "sampler_name", "")]
                if options.hires and getattr(p, "enable_hr", False):
                    names.append(getattr(p, "hr_sampler_name", ""))
                if any(str(name).lower() in ("ddim", "plms") for name in names):
                    raise ValueError("Krea Shift ramp needs a sigma-based sampler such as Euler; DDIM/PLMS do not use this schedule.")
                old_shift, old_hr = p.distilled_cfg_scale, getattr(p, "hr_distilled_cfg", None)
                p.distilled_cfg_scale = options.start
                if options.hires and old_hr is not None:
                    p.hr_distilled_cfg = options.start
                try:
                    return original_inner(p, *args, **kwargs)
                finally:
                    p.distilled_cfg_scale = old_shift
                    if old_hr is not None:
                        p.hr_distilled_cfg = old_hr
            return original_inner(p, *args, **kwargs)

        original_run = self.scripts.ScriptRunner.run

        @wraps(original_run)
        def run(runner, p, *args):
            # Loop OUTSIDE selectable scripts. Stock XYZ only keeps one image per
            # cell: returning a hidden batch inside a cell would lose comparisons.
            # Each list entry instead gets its own complete prompt XYZ grid.
            if getattr(runtime.shared.opts, "forge_preset", None) == "krea":
                options = options_for(p)
                prepare_request(p, options)
                if args and args[0] and options.run_multiple:
                    return hooks.sequence(p, options, lambda child: original_run(runner, child, *args))
            return original_run(runner, p, *args)

        original_sigmas = self.sampler_class.get_sigmas

        @wraps(original_sigmas)
        def sigmas(sampler, p, steps):
            if not hooks.is_krea(p):
                return original_sigmas(sampler, p, steps)
            options = options_for(p)
            hires = bool(getattr(p, "is_hr_pass", False))
            if not options.enabled or options.mode != RAMP or (hires and not options.hires):
                return original_sigmas(sampler, p, steps)
            if "sigmas" not in inspect.signature(sampler.func).parameters:
                raise ValueError("Krea Shift ramp needs a sampler that uses the full sigma schedule, such as Euler.")
            if getattr(p, "sampler_noise_scheduler_override", None) is not None:
                raise ValueError("Krea Shift ramp cannot be combined with another custom noise-schedule override.")
            predictor = p.sd_model.forge_objects.unet.model.predictor
            previous = predictor.shift
            try:
                set_krea_shift(p.sd_model, options.start, runtime.predictor_type)
                first = original_sigmas(sampler, p, steps)
                if len(first) < 2:
                    return first
                start = max(0, min(int(getattr(p, "_neo_shift_suffix", 0)), len(first) - 2))
                shifts = options.progression(len(first) - 1 - start)
                grids = {options.start: first}
                for mu in dict.fromkeys(shifts):
                    if mu not in grids:
                        set_krea_shift(p.sd_model, mu, runtime.predictor_type)
                        grids[mu] = original_sigmas(sampler, p, steps)
                result = blend_intervals(grids, shifts, start)
                details = metadata(options, shifts, hires)
                details.pop("Krea Shift hires fixed", None)  # Captured before the pass by inner().
                p.extra_generation_params.update(details)
                p.extra_generation_params["Hires Shift" if hires else "Shift"] = options.start
                return result
            finally:
                set_krea_shift(p.sd_model, previous, runtime.predictor_type)

        original_i2i = self.sampler_class.sample_img2img

        @wraps(original_i2i)
        def img2img(sampler, p, x, noise, conditioning, unconditional_conditioning, steps=None, image_conditioning=None):
            options = options_for(p) if hooks.is_krea(p) else None
            if options is None or not options.enabled or options.mode != RAMP:
                return original_i2i(sampler, p, x, noise, conditioning, unconditional_conditioning,
                                    steps=steps, image_conditioning=image_conditioning)
            old = getattr(p, "_neo_shift_suffix", None)
            full, encoded = hooks.img2img_steps(p, steps)
            p._neo_shift_suffix = max(0, full - encoded - 1)
            try:
                return original_i2i(sampler, p, x, noise, conditioning, unconditional_conditioning,
                                    steps=steps, image_conditioning=image_conditioning)
            finally:
                if old is None:
                    del p._neo_shift_suffix
                else:
                    p._neo_shift_suffix = old

        runtime.patch(self.processing, "process_images_inner", inner)
        runtime.patch(self.scripts.ScriptRunner, "run", run)
        runtime.patch(self.sampler_class, "get_sigmas", sigmas)
        runtime.patch(self.sampler_class, "sample_img2img", img2img)
