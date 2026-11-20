"""Run upstream functions on CPU, stubbing only heavyweight model construction."""
import ast
import copy
import importlib.util
import inspect
import json
import logging
import os
from pathlib import Path
import re
import sys
import warnings
from functools import wraps
from types import ModuleType, SimpleNamespace as NS

import gradio as gr
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from neo_krea_shift.runtime import Runtime

SOURCE = Path(os.environ["KREA_SHIFT_TEST_SOURCE"])


def module(name, **kwargs):
    m = ModuleType(name)
    m.__dict__.update(kwargs)
    return m


def tree(filename):
    return ast.parse((SOURCE / filename).read_text(encoding="utf-8"))


def definitions(filename, names, target):
    nodes = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    nodes += [n for n in tree(filename).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    if len(nodes) != len(names) + 1:
        raise AssertionError(f"Missing upstream definitions: {filename}: {names}")
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 str(SOURCE / filename), "exec"), target.__dict__)


def import_source(filename):
    spec = importlib.util.spec_from_file_location("_test_" + filename[:-3], SOURCE / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# Use Forge's real Gradio compatibility adapter and header-checkbox component.
gradio_compat = module("_gradio_compat", gr=gr, wraps=wraps, inspect=inspect, warnings=warnings,
                      GradioDeprecationWarning=DeprecationWarning)
definitions("gradio_extensions.py", {"EventWrapper", "repair"}, gradio_compat)
# Neo disables this decorator before constructing its custom UI components.
# Otherwise Gradio saves setup=True and incorrectly rebuilds accordion events on paste.
gr.component_meta.updateable = lambda fn: fn
gradio_compat.repair(gr.Checkbox)
ui_components = module("modules.ui_components", gr=gr, wraps=wraps, __file__=str(SOURCE/"ui_components.py"))
sys.modules["modules.ui_components"] = ui_components
definitions("ui_components.py", {"InputAccordionImpl", "InputAccordion"}, ui_components)


def make_environment():
    prediction = import_source("k_prediction.py")
    presets = import_source("presets.py")
    opts = NS(forge_preset="krea", sd_model_checkpoint="test.safetensors",
              sd_modules_dropdown_use_short=True, forge_additional_modules=[],
              krea_t2i_dcfg=1.15, krea_t2i_hr_dcfg=0.9, krea_i2i_dcfg=0.65,
              infotext_skip_pasting=[], strip_whitespaces=True,
              use_old_hires_fix_width_height=False, infotext_styles="Ignore")
    opts.set = lambda key, value: setattr(opts, key, value)
    opts.save = lambda *args: None
    shared = NS(opts=opts, config_filename="not-written", state=NS(),
                cmd_opts=NS(hide_ui_dir_config=True, no_prompt_history=True))
    main = module("_test_main", gr=gr, os=os, shared=shared, module_map={}, module_list={},
                  PresetArch=presets.PresetArch, use_shift=presets.use_shift,
                  use_distill=presets.use_distill, is_video=presets.is_video)
    definitions("main_entry.py", {"on_preset_change"}, main)
    callbacks = NS(infotext_pasted_callback=lambda *args: None)
    info = module("_test_info", gr=gr, os=os, json=json, re=re, shared=shared,
                  main_entry=main, type_of_gr_update=type(gr.skip()),
                  errors=NS(report=lambda *a, **kw: None), uses_emphasis=lambda _: False,
                  script_callbacks=callbacks, registered_param_bindings=[], paste_fields={})
    for n in tree("infotext_utils.py").body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
                t.id in {"re_param_code", "re_param", "re_imagesize"} for t in n.targets):
            exec(compile(ast.Module(body=[n], type_ignores=[]), "<upstream regex>", "exec"), info.__dict__)
    definitions("infotext_utils.py", {"unquote", "quote", "_parse_info", "restore_old_hires_fix_params",
                "_extract_styles", "_populate_defaults", "parse_generation_parameters", "connect_paste",
                "ParamBinding", "PasteField", "register_paste_params_button"}, info)
    base = module("_test_base", memory_management=NS(logger=logging.getLogger("test")))
    base_class = next(n for n in tree("base.py").body if isinstance(n, ast.ClassDef) and n.name == "ForgeDiffusionEngine")
    method = next(n for n in base_class.body if isinstance(n, ast.FunctionDef) and n.name == "set_shift")
    exec(compile(ast.Module(body=[method], type_ignores=[]), "<upstream set_shift>", "exec"), base.__dict__)

    class Base:
        set_shift = base.set_shift
        def __init__(self, *args): self.use_shift = False
        def _get_predictor(self): return prediction.PredictionFlux(NS(sampling_settings={"shift": 1.15}))

    class Objects(NS):
        def shallow_copy(self): return copy.copy(self)

    krea = module("_test_krea", torch=torch, ForgeDiffusionEngine=Base, ForgeObjects=Objects,
        model_list=NS(Krea2=object()), VAE=lambda **kw: object(),
        CLIP=lambda **kw: NS(cond_stage_model=NS(qwen3vl_4b=object()), tokenizer=NS(**kw["tokenizer_dict"])),
        UnetPatcher=NS(from_model=lambda **kw: NS(model=NS(predictor=kw["k_predictor"]))),
        Qwen3VL4BEngine=lambda **kw: object())
    definitions("krea.py", {"Krea2"}, krea)
    runtime = Runtime(engine_class=krea.Krea2, predictor_type=prediction.PredictionFlux,
                      main_entry=main, infotext=info, shared=shared, presets=presets, gr=gr)
    def engine():
        return krea.Krea2(object(), dict.fromkeys(("text_encoder", "tokenizer", "vae", "transformer")))
    return NS(runtime=runtime, engine=engine, info=info, main=main, shared=shared,
              prediction=prediction, krea=krea, base=Base)


def infotext(shift=0.65, hires=1.39, preset="krea"):
    text = f"Test scene\nSteps: 8, Sampler: Euler, CFG scale: 1, Seed: 42, Size: 1024x1024, UI preset: {preset}, Version: neo-2.32"
    if shift is not None:
        text += f", Shift: {shift}"
    if hires is not None:
        text += f", Hires Shift: {hires}"
    return text


def generated_infotext(env, shift, hires=None, extra=None):
    """Actual upstream PNG infotext writer, with a minimal processing record."""
    opts = env.shared.opts
    defaults = dict(CLIP_stop_at_last_layers=1, eta_noise_seed_delta=0,
        add_model_name_to_info=True, add_model_hash_to_info=False,
        forge_unet_storage_dtype="Automatic", inpainting_mask_weight=1,
        scaling_factor=1, save_init_img=False, randn_source="CPU", tiling=False,
        add_version_to_infotext=True, add_user_name_to_info=False)
    for key, value in defaults.items(): setattr(opts, key, value)
    engine = env.engine()
    engine.use_distilled_cfg_scale = False
    engine.is_sd1 = False
    engine.set_shift(shift)
    p = NS(sd_model=engine, distilled_cfg_scale=shift, batch_size=1,
        all_negative_prompts=[""], get_token_merging_ratio=lambda **kw: 0,
        steps=8, sampler_name="Euler", scheduler="Simple", cfg_scale=1,
        restore_faces=False, width=1024, height=1024, sd_model_name="test",
        subseed_strength=0, seed_resize_from_w=0, seed_resize_from_h=0,
        is_using_inpainting_conditioning=False, extra_generation_params={"UI preset": "krea"})
    if hires is not None:
        p.extra_generation_params["Hires Shift"] = hires
    p.extra_generation_params.update(extra or {})
    ns = module("_test_processing", opts=opts, shared=env.shared, os=os,
        _overridden_modules=[], infotext_utils=env.info, program_version=lambda: "neo-2.32")
    definitions("processing.py", {"create_infotext"}, ns)
    return ns.create_infotext(p, ["Test scene"], [42], [0])
