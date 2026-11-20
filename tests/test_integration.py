import copy
import math
import importlib.util
import json
import os
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

import gradio as gr
from PIL import Image, PngImagePlugin
import torch

from support import make_environment, infotext, definitions, module, tree, generated_infotext


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.e = make_environment()
        self.e.runtime.install()
        self.addCleanup(self.e.runtime.uninstall)

    def test_real_krea_constructor_enables_only_krea(self):
        self.assertTrue(self.e.engine().use_shift)
        self.assertFalse(self.e.base().use_shift)

    def test_actual_schedule_zero_decimals_and_return_to_default(self):
        engine = self.e.engine()
        predictor = engine.forge_objects.unet.model.predictor
        t = torch.tensor([0.1, 0.25, 0.5, 0.75, 1.0])
        for value in (0.65, 0, 0.5, 1.15, 1.39, 4.02, 1.15):
            self.assertEqual(engine.set_shift(value, width=1024, height=1024), value)
            expected = math.exp(value) * t / (1 + (math.exp(value) - 1) * t)
            torch.testing.assert_close(predictor.sigma(t), expected)
            self.assertTrue(torch.all(predictor.sigmas[1:] >= predictor.sigmas[:-1]))
        other = self.e.prediction.PredictionFlux(NS(sampling_settings={"shift": 1.15}))
        self.assertEqual(other.shift, 1.15)

    def test_validation_does_not_corrupt_current_predictor(self):
        engine = self.e.engine()
        predictor = engine.forge_objects.unet.model.predictor
        for value in (float("nan"), float("inf"), -1, 25):
            with self.assertRaises(ValueError): engine.set_shift(value)
            self.assertEqual(predictor.shift, 1.15)
        engine.forge_objects.unet.model.predictor = object()
        with self.assertRaisesRegex(RuntimeError, "legacy predictor"):
            engine.set_shift(0.65)

    def test_native_preset_controls_and_restore_other_presets(self):
        updates = self.e.main.on_preset_change("krea")
        self.assertEqual([u["value"] for u in updates[17:20]], [1.15, .9, .65])
        for u in updates[17:20]:
            self.assertEqual((u["minimum"], u["step"], u["visible"]), (0, .01, True))
        for preset in ("flux", "wan", "sd", "qwen21"):
            result = self.e.main.on_preset_change(preset)
            for u in result[17:20]: self.assertEqual(u["info"], "")

    def test_programmatic_preset_change_keeps_pasted_values(self):
        self.e.shared.opts.forge_preset = "flux"
        saves = []
        self.e.shared.opts.save = lambda *args: saves.append(args)
        updates = self.e.runtime.layout_only("krea")
        self.assertTrue(all("value" not in u for u in updates))
        self.assertEqual(self.e.shared.opts.forge_preset, "krea")
        self.assertTrue(updates[17]["visible"])
        self.assertEqual(saves, [])
        self.e.main.on_preset_change("krea")
        self.assertEqual(len(saves), 1)

    def test_png_file_roundtrip_native_parser_and_slider_conversion(self):
        shift = gr.Slider(minimum=0, maximum=24, step=.01, value=1.15)
        hires = gr.Slider(minimum=0, maximum=24, step=.01, value=1.15)
        with tempfile.TemporaryDirectory() as folder:
            for value in (0, .5, .65, .9, 1.15, 1.39, 4.02):
                path = Path(folder) / "metadata.png"
                metadata = PngImagePlugin.PngInfo()
                metadata.add_text("parameters", generated_infotext(self.e, value, 1.39))
                Image.new("RGB", (8, 8)).save(path, pnginfo=metadata)
                with Image.open(path) as png:
                    parsed = self.e.info.parse_generation_parameters(png.info["parameters"])
                self.assertEqual(self.e.info._parse_info(shift, "Distilled CFG Scale", parsed)["value"], value)
                self.assertEqual(self.e.info._parse_info(hires, "Hires Distilled CFG Scale", parsed)["value"], 1.39)

    def test_legacy_defaults_aliases_and_skip_settings(self):
        parse = self.e.info.parse_generation_parameters
        self.assertEqual(parse(infotext(None, None))["Distilled CFG Scale"], 1.15)
        for wrong in ("Version: ComfyUI", "Version: neo-2.27"):
            self.assertNotIn("Distilled CFG Scale", parse(infotext(None, None).replace("Version: neo-2.32", wrong)))
        self.assertNotIn("Distilled CFG Scale", parse(infotext(None, None, "flux")))
        aliases = infotext(0).replace("Shift:", "Distilled CFG Scale:")
        self.assertEqual(float(parse(aliases)["Distilled CFG Scale"]), 0)
        self.e.shared.opts.infotext_skip_pasting = ["Distilled CFG Scale"]
        self.assertNotIn("Distilled CFG Scale", parse(infotext()))

    def test_install_idempotency_and_uninstall(self):
        patched = self.e.krea.Krea2.set_shift
        self.e.runtime.install()
        self.assertIs(patched, self.e.krea.Krea2.set_shift)
        self.e.runtime.uninstall()
        self.assertIs(self.e.krea.Krea2.set_shift, self.e.base.set_shift)
        self.assertFalse(self.e.engine().use_shift)

    def test_already_loaded_krea_is_enabled(self):
        engine = self.e.engine()
        engine.use_shift = False
        self.e.runtime.model_loaded(engine)
        self.assertTrue(engine.use_shift)
        other = self.e.base()
        self.e.runtime.model_loaded(other)
        self.assertFalse(other.use_shift)

    @unittest.skipUnless(os.environ.get("KREA_SHIFT_CUSTOM_IIB"), "Optional custom IIB adapter not configured")
    def test_custom_iib_normal_and_legacy_do_not_require_custom_core(self):
        package = module("_custom_iib")
        package.__path__ = [str(Path(os.environ["KREA_SHIFT_CUSTOM_IIB"]).parent)]
        sys.modules[package.__name__] = package
        spec = importlib.util.spec_from_file_location("_custom_iib.metadata_transfer", os.environ["KREA_SHIFT_CUSTOM_IIB"])
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        self.e.info.get_override_settings = lambda *a, **kw: []
        from neo_krea_shift.ui import controls
        from neo_krea_shift.schedules import Options, RAMP, metadata
        with gr.Blocks():
            _, ramp_fields = controls(gr)
        ramp = Options(mode=RAMP, start=0, end=2, curve="Hold then switch", switch=70)
        for legacy in (False, True):
            for value in (0, .65, 1.39, 4.02):
                shift = gr.Slider(0, 24, value=9, step=.01, elem_id="txt2img_distilled_cfg_scale")
                hires = gr.Slider(0, 24, value=9, step=.01, elem_id="txt2img_hr_distilled_cfg")
                preset = gr.Dropdown(["krea", "flux"], value="flux", elem_id="forge_ui_preset")
                fields = [(shift, "Distilled CFG Scale"), (hires, "Hires Distilled CFG Scale"), (preset, "UI preset")] + ramp_fields
                handler, outputs = adapter.make_metadata_handler(
                    self.e.info, NS(infotext_pasted_callback=lambda *a: None), gr,
                    {"fields": fields}, keep_model=legacy)
                result = handler(json.dumps({"requestId": "test", "infotext": generated_infotext(self.e, value, .9)}))
                self.assertTrue(json.loads(result[-1])["ok"])
                mapped = dict(zip((getattr(c, "elem_id", None) for c in outputs), result))
                self.assertEqual(mapped[shift.elem_id]["value"], value)
                self.assertEqual(mapped[hires.elem_id]["value"], .9)
                result = handler(json.dumps({"requestId":"ramp", "infotext":generated_infotext(
                    self.e, 0, extra=metadata(ramp, ramp.progression(8)))}))
                mapped = dict(zip((getattr(c,"elem_id",None) for c in outputs),result))
                self.assertTrue(json.loads(result[-1])["ok"])
                self.assertEqual(mapped["txt2img_krea_shift_mode"]["value"],RAMP)
                self.assertEqual(mapped["txt2img_krea_shift_to"]["value"],2)
                self.assertEqual(mapped["txt2img_krea_shift_switch"]["value"],70)

    def test_stock_xyz_cell_and_loop_apply_each_shift_and_preserve_metadata(self):
        # Execute the upstream cell body and grid loop, not a reimplementation.
        values = [0, .5, .9, 1.15, 1.39, 1.79]
        engine = self.e.engine()
        observed = []
        p = NS(seed=42, styles=[], override_settings={}, extra_generation_params={},
               n_iter=1, width=8, height=8, distilled_cfg_scale=9)
        state = NS(interrupted=False, stopping_generation=False)
        def process(pc):
            engine.set_shift(pc.distilled_cfg_scale)
            sigma = float(engine.forge_objects.unet.model.predictor.sigma(torch.tensor(.5)))
            observed.append((pc.distilled_cfg_scale, sigma, pc.seed))
            return NS(images=[Image.new("RGB", (8,8))], prompt="Test", seed=pc.seed,
                      infotexts=[infotext(pc.distilled_cfg_scale)], width=8, height=8)
        ns = module("_test_xyz", copy=copy.copy, Image=Image, shared=NS(state=state),
                    images=NS(GridAnnotation=lambda *args: None,
                              image_grid=lambda imgs, rows: imgs[0]),
                    p=p, xs=values, ys=[None], zs=[None], process_images=process,
                    vary_seeds_x=False, vary_seeds_y=False, vary_seeds_z=False,
                    grid_infotext=["already set", "already set"])
        definitions("xyz_grid.py", {"apply_field", "draw_xyz_grid"}, ns)
        ns.x_opt = NS(apply=ns.apply_field("distilled_cfg_scale"))
        ns.y_opt = ns.z_opt = NS(apply=lambda *args: None)
        import ast
        cell = next(n for n in ast.walk(tree("xyz_grid.py")) if isinstance(n, ast.FunctionDef) and n.name == "cell")
        exec(compile(ast.Module(body=[cell], type_ignores=[]), "<upstream XYZ cell>", "exec"), ns.__dict__)
        result = ns.draw_xyz_grid(p, values, [None], [None], list(map(str, values)), [""], [""],
                                  ns.cell, False, True, False, "x", "y", 0)
        self.assertEqual([row[0] for row in observed], values)
        self.assertEqual(len(set(row[1] for row in observed)), len(values))
        self.assertTrue(all(row[2] == 42 for row in observed))
        self.assertEqual(p.distilled_cfg_scale, 9)
        for text, value in zip(result.infotexts[2:], values):
            self.assertEqual(float(self.e.info.parse_generation_parameters(text)["Distilled CFG Scale"]), value)


if __name__ == "__main__": unittest.main()
