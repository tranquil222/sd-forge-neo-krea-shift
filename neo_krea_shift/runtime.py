"""Runtime-only adapter. No Forge files or checkpoint weights are rewritten."""
from functools import wraps
import inspect
import math
import re

DEFAULT_SHIFT = 1.15
SHIFT_IDS = {
    "txt2img_distilled_cfg_scale", "txt2img_hr_distilled_cfg",
    "img2img_distilled_cfg_scale",
}
SHIFT_INFO = (
    "Krea 2 timestep shift (mu / log scale). Default 1.15; 0 is unshifted. "
    "Not CFG. Comfy AuraFlow shift 4 corresponds to mu 1.3863."
)


def add_legacy_defaults(params):
    """Only known native Neo Krea metadata; never infer from a model filename."""
    version = re.match(r"^neo-(\d+)\.(\d+)", str(params.get("Version", "")))
    if params.get("UI preset") != "krea" or not version:
        return
    # Earlier Krea implementations used a different predictor.
    if tuple(map(int, version.groups())) < (2, 28):
        return
    for raw, alias in (("Shift", "Distilled CFG Scale"),
                       ("Hires Shift", "Hires Distilled CFG Scale")):
        if raw not in params and alias not in params:
            params[raw] = DEFAULT_SHIFT


def set_krea_shift(engine, shift, predictor_type):
    value = float(shift)
    if not math.isfinite(value) or not 0 <= value <= 24:
        raise ValueError("Krea Shift must be a finite mu value between 0 and 24.")
    predictor = engine.forge_objects.unet.model.predictor
    if not isinstance(predictor, predictor_type):
        raise RuntimeError(
            "Krea Shift requires Neo's PredictionFlux predictor. "
            "Disable legacy predictor overrides before generating."
        )
    # Old PredictionFlux uses `shift or self.shift`. Setting the instance first
    # makes zero work without changing that shared class for any other model.
    previous = predictor.shift
    predictor.shift = value
    try:
        predictor.set_parameters(shift=value)
    except Exception:
        predictor.shift = previous
        raise
    return value


class Runtime:
    def __init__(self, *, engine_class, predictor_type, main_entry, infotext,
                 shared, presets, gr):
        self.engine_class = engine_class
        self.predictor_type = predictor_type
        self.main_entry = main_entry
        self.infotext = infotext
        self.shared = shared
        self.presets = presets
        self.gr = gr
        self.patches = []
        self.legacy_ui = "layout_only" not in inspect.signature(main_entry.on_preset_change).parameters

    def patch(self, target, name, replacement):
        own = name in vars(target)
        original = getattr(target, name)
        self.patches.append((target, name, own, original, replacement))
        setattr(target, name, replacement)

    def shift_layout(self, preset):
        if preset == "krea":
            return dict(visible=True, label="Shift", minimum=0.0,
                        maximum=24.0, step=0.01, info=SHIFT_INFO)
        visible = self.presets.use_shift(preset)
        result = dict(visible=visible or self.presets.use_distill(preset),
                      label="Shift" if visible else "Distilled CFG Scale",
                      minimum=1.0, maximum=24.0, step=0.5, info="")
        if visible:
            result["visible"] = getattr(self.shared.opts, f"{preset}_show_shift", True)
        if preset == "qwen21":
            result.update(minimum=0.3, maximum=1.2, step=0.01)
        return result

    def update_layout(self, updates, preset):
        # Neo's native preset output contract: 17 general, 3 shift, 2 batch.
        if not isinstance(updates, (list, tuple)) or len(updates) != 22:
            raise RuntimeError("Krea Shift: unsupported Neo preset output layout; update the extension.")
        result = list(updates)
        for i in range(17, 20):
            result[i] = dict(result[i])
            if preset == "krea":
                result[i].update(self.shift_layout(preset))
            else:
                # Reset attributes we changed, but preserve other extensions'
                # explicit per-model ranges and information.
                for key in ("minimum", "maximum", "step", "info"):
                    result[i].setdefault(key, self.shift_layout(preset)[key])
        return result

    def layout_only(self, preset):
        # Keep Neo's preset bookkeeping and layout (including video controls),
        # but never replace pasted generation values with preset defaults.
        result = self.preset_callback(preset)
        return [{key: value for key, value in update.items() if key != "value"}
                for update in result]

    def install(self):
        if self.patches:
            return
        runtime = self
        old_init = self.engine_class.__init__

        @wraps(old_init)
        def init(engine, *args, **kwargs):
            old_init(engine, *args, **kwargs)
            engine.use_shift = True

        def shift(engine, shift, *args, **kwargs):
            return set_krea_shift(engine, shift, runtime.predictor_type)

        old_defaults = self.infotext._populate_defaults

        @wraps(old_defaults)
        def defaults(params):
            old_defaults(params)
            add_legacy_defaults(params)

        old_preset = self.main_entry.on_preset_change

        @wraps(old_preset)
        def preset(preset, *args, **kwargs):
            return runtime.update_layout(old_preset(preset, *args, **kwargs), preset)

        self.patch(self.engine_class, "__init__", init)
        self.patch(self.engine_class, "set_shift", shift)
        self.patch(self.infotext, "_populate_defaults", defaults)
        self.patch(self.main_entry, "on_preset_change", preset)
        self.preset_callback = preset

    def after_component(self, component, **kwargs):
        elem_id = getattr(component, "elem_id", None)
        if elem_id in SHIFT_IDS and self.shared.opts.forge_preset == "krea":
            for key, value in self.shift_layout("krea").items():
                setattr(component, key, value)
        if elem_id != "forge_ui_preset" or not self.legacy_ui:
            return
        # Stock Neo applies preset values on .change(), including programmatic
        # PNG/IIB pastes. Separate visual updates from deliberate user selections.
        # This touches only this dropdown's native preset handler, not Gradio.
        old_change = component.change
        runtime = self

        def connect(fn=None, *args, **kwargs):
            if fn is not runtime.preset_callback:
                return old_change(fn, *args, **kwargs)
            old_change(runtime.layout_only, *args, **kwargs)
            return component.input(fn, *args, **kwargs)

        self.patch(component, "change", connect)

    def model_loaded(self, engine):
        if isinstance(engine, self.engine_class):
            engine.use_shift = True

    def uninstall(self):
        for target, name, own, original, replacement in reversed(self.patches):
            if getattr(target, name) is replacement:
                if own:
                    setattr(target, name, original)
                else:
                    delattr(target, name)
        self.patches.clear()
