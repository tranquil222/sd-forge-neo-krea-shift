"""Run native Neo sampler/XYZ/paste code on CPU, without model weights."""
import ast
from copy import copy
import inspect
import importlib.util
from pathlib import Path
import random
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import gradio as gr
import numpy as np
from PIL import Image
from scipy import stats
import torch

from support import make_environment, definitions, module, tree, generated_infotext
from neo_krea_shift.jobs import JobHooks, options_for
from neo_krea_shift.schedules import Options, FIXED, VALUES, RAMP, CURVES, parse_values
from neo_krea_shift.ui import controls


def methods(filename, classname, names, target):
    cls = next(n for n in tree(filename).body if isinstance(n, ast.ClassDef) and n.name == classname)
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), target.__dict__)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.e = make_environment()
        self.e.runtime.install()
        self.addCleanup(self.e.runtime.uninstall)
        self.e.shared.total_tqdm = NS(clear=lambda: None)
        self.e.shared.state.interrupted = False
        self.e.shared.state.stopping_generation = False
        opts = self.e.shared.opts
        for name, value in dict(always_discard_next_to_last_sigma=False, sigma_min=0,
                sigma_max=0, rho=0, beta_dist_alpha=.6, beta_dist_beta=.6,
                img2img_fix_steps=False, img2img_extra_noise=0, sgm_noise_multiplier=False).items():
            setattr(opts, name, value)
        sched = module("_sched", torch=torch, np=np, stats=stats, shared=self.e.shared)
        definitions("sd_schedulers.py", {"simple_scheduler", "beta_scheduler"}, sched)
        sched.schedulers_map = {name:NS(label=name, function=fn, default_rho=-1, need_inner_model=True)
            for name, fn in (("Simple", sched.simple_scheduler), ("Beta", sched.beta_scheduler))}
        common = module("_common", opts=opts)
        definitions("sd_samplers_common.py", {"setup_img2img_steps"}, common)
        native = module("_sampler", opts=opts, torch=torch, inspect=inspect,
            sd_schedulers=sched, devices=NS(cpu=torch.device("cpu")), sd_samplers_common=common,
            sampling_prepare=lambda *a, **k: None, sampling_cleanup=lambda *a: None)
        methods("sd_samplers_kdiffusion.py", "KDiffusionSampler", {"get_sigmas", "sample", "sample_img2img"}, native)
        self.Sampler = type("Sampler", (), {name:getattr(native, name) for name in ("get_sigmas", "sample", "sample_img2img")})
        self.original_sigmas = native.get_sigmas
        self.engine = self.e.engine()
        self.engine.forge_objects.unet.model_options = {"transformer_options": {}}
        predictor = self.engine.forge_objects.unet.model.predictor
        class Linker:
            @property
            def sigmas(self): return predictor.sigmas
        linker = Linker()
        linker.predictor, linker.inner_model = predictor, self.engine
        self.sampler = self.Sampler()
        self.sampler.model_wrap, self.sampler.model_wrap_cfg = linker, NS()
        self.sampler.config = NS(options={})
        self.sampler.func = lambda model, x, sigmas, **kw: sigmas
        self.sampler.initialize = lambda p: {}
        self.sampler.launch_sampling = lambda count, fn: fn()
        self.sampler.add_infotext = lambda p: None
        self.sampler.s_min_uncond, self.sampler.callback_state = 0, None
        self.seen = []
        self.processing = module("_processing", random=random)
        definitions("processing.py", {"get_fixed_seed", "fix_seed"}, self.processing)
        self.processing.process_images_inner = self.generate
        self.processing.Processed = lambda p, imgs, seed, info: NS(images=imgs, seed=seed, info=info)
        scripts = module("_scripts", shared=self.e.shared)
        methods("scripts.py", "ScriptRunner", {"run"}, scripts)
        self.Runner = type("ScriptRunner", (), {"run":scripts.run})
        scripts.ScriptRunner = self.Runner
        self.hooks = JobHooks(self.e.runtime, self.processing, scripts, self.Sampler, common.setup_img2img_steps)
        self.hooks.install()
        self.p = NS(sd_model=self.engine, distilled_cfg_scale=.9, hr_distilled_cfg=1.39,
            extra_generation_params={}, override_settings={}, styles=[], prompt="red", seed=42, subseed=0,
            n_iter=1, batch_size=1, width=8, height=8, steps=8, cfg_scale=1,
            scheduler="Simple", hr_scheduler="Beta", is_hr_pass=False,
            sampler_noise_scheduler_override=None, denoising_strength=.5, script_args=[], scripts=None)

    def generate(self, p):
        self.engine.set_shift(p.distilled_cfg_scale)
        sigmas = self.sampler.sample(p, torch.zeros(1, 4, 2, 2), None, None)
        text = generated_infotext(self.e, p.distilled_cfg_scale, extra=p.extra_generation_params)
        self.seen.append((p.prompt, p.distilled_cfg_scale, p.seed, sigmas, text))
        return NS(images=[Image.new("RGB", (8,8))], extra_images=[], seed=p.seed, subseed=p.subseed,
            prompt=p.prompt, negative_prompt="", info=text, comments="", width=8, height=8,
            index_of_first_image=0, all_seeds=[p.seed], all_subseeds=[p.subseed],
            all_prompts=[p.prompt], all_negative_prompts=[""], infotexts=[text])

    def ramp(self, **kw):
        self.p._neo_krea_shift_options = Options(mode=RAMP, **kw)

    def test_ramps_reach_terminal_zero_in_both_directions_every_curve(self):
        for scheduler in ("Simple", "Beta"):
            self.p.scheduler = scheduler
            for curve in CURVES:
                for start, end in ((0, 2), (2, 0), (.5, 1.15), (0,24), (24,0)):
                    with self.subTest(scheduler=scheduler, curve=curve, endpoints=(start,end)):
                        self.ramp(start=start, end=end, curve=curve)
                        grid = self.sampler.get_sigmas(self.p, 8)
                        self.assertEqual(len(grid), 9)
                        self.assertTrue(torch.isfinite(grid).all())
                        self.assertTrue((grid[:-1] >= grid[1:]).all())
                        self.assertEqual(float(grid[0]), 1)
                        self.assertEqual(float(grid[-1]), 0)
                        values = self.p.extra_generation_params["Krea Shift steps"].split(", ")
                        self.assertEqual((float(values[0]),float(values[-1])), (start,end))
                        self.assertEqual(self.sampler.model_wrap.predictor.shift, 1.15)

    def test_equal_endpoints_are_bit_exact_native_including_zero(self):
        for scheduler in ("Simple", "Beta"):
            self.p.scheduler = scheduler
            for mu in (0, .65, 1.15, 4):
                self.engine.set_shift(mu)
                expected = self.original_sigmas(self.sampler, self.p, 8)
                self.ramp(start=mu, end=mu)
                self.assertTrue(torch.equal(self.sampler.get_sigmas(self.p, 8), expected))

    def test_actual_img2img_sampler_receives_ramp_over_sampled_suffix(self):
        self.engine.set_shift(.5)
        baseline = self.original_sigmas(self.sampler, self.p, 8)[3:]
        self.ramp(start=.5, end=2)
        x = torch.zeros(1,4,2,2)
        actual = self.sampler.sample_img2img(self.p, x, x, None, None)
        self.assertEqual(len(actual), 6)  # t_enc=4, five actual sampling intervals
        self.assertEqual(actual[0], baseline[0])
        self.assertEqual(actual[-1], baseline[-1])
        self.assertFalse(torch.equal(actual, baseline))
        self.assertEqual(len(self.p.extra_generation_params["Krea Shift steps"].split(", ")), 5)
        self.assertFalse(hasattr(self.p, "_neo_shift_suffix"))

    def test_hires_uses_its_own_shift_unless_opted_in_and_restores_fields(self):
        self.p.is_hr_pass = True
        self.engine.set_shift(1.39)
        baseline = self.original_sigmas(self.sampler, self.p, 8)
        self.ramp(start=0, end=2)
        self.assertTrue(torch.equal(self.sampler.get_sigmas(self.p, 8), baseline))
        self.ramp(start=0, end=2, hires=True)
        self.processing.process_images_inner(self.p)
        self.assertIn("Hires Krea Shift steps", self.p.extra_generation_params)
        self.assertEqual(self.p.distilled_cfg_scale, .9)
        self.assertEqual(self.p.hr_distilled_cfg, 1.39)

    def test_one_step_and_penultimate_discard(self):
        self.ramp(start=0, end=2)
        self.assertEqual(self.sampler.get_sigmas(self.p, 1).tolist(), [1,0])
        self.assertEqual(self.p.extra_generation_params["Krea Shift steps"], "0")
        self.sampler.config.options["discard_next_to_last_sigma"] = True
        self.assertEqual(len(self.sampler.get_sigmas(self.p, 8)), 9)

    def test_non_krea_does_not_expand_or_apply_ramp(self):
        self.p.sd_model = NS(forge_objects=self.engine.forge_objects)
        self.p._neo_krea_shift_options = Options(mode=VALUES, values="0,.5,2")
        self.processing.process_images_inner(self.p)
        self.assertEqual(len(self.seen), 1)
        self.assertEqual(self.seen[0][1], .9)
        self.ramp(start=0, end=2)
        grid = self.sampler.get_sigmas(self.p, 8)
        self.assertTrue(torch.equal(grid, self.original_sigmas(self.sampler, self.p, 8)))

    def test_ramp_settings_round_trip_real_writer_and_paste_fields(self):
        self.ramp(start=0, end=2, curve="Hold then switch", switch=70, hires=True)
        result = self.processing.process_images_inner(self.p)
        params = self.e.info.parse_generation_parameters(result.infotexts[0])
        with gr.Blocks():
            _, fields = controls(gr)
        pasted = Options.read(*(fn(params) for _,fn in fields))
        self.assertEqual(pasted, self.p._neo_krea_shift_options)
        self.assertEqual(params["Krea Shift algorithm"], "interval-v1")
        old = self.e.info.parse_generation_parameters(generated_infotext(self.e, .65))
        self.assertEqual(Options.read(*(fn(old) for _,fn in fields)).mode, FIXED)

    def test_list_uses_same_seed_every_output_has_own_native_metadata(self):
        self.p.seed = self.p.subseed = -1
        # Read from actual always-on argument slice, not the private override.
        self.p.scripts = NS(alwayson_scripts=[NS(neo_krea_shift_controls=True,args_from=1,args_to=8)])
        self.p.script_args = [0, VALUES, "2, 0, .65, 2", 0, 2, "Linear", 50, False]
        result = self.processing.process_images_inner(self.p)
        self.assertEqual([r[1] for r in self.seen], [2,0,.65,2])
        self.assertEqual(len({r[2] for r in self.seen}), 1)
        self.assertNotEqual(self.seen[0][2], -1)
        self.assertEqual(len(result.images), 4)
        self.assertEqual(self.p.distilled_cfg_scale, .9)
        for text, value in zip(result.infotexts, (2,0,.65,2)):
            parsed = self.e.info.parse_generation_parameters(text)
            self.assertEqual(float(parsed["Distilled CFG Scale"]), value)
            self.assertEqual(parsed["Krea Shift mode"], FIXED)

    def test_list_wraps_actual_script_runner_and_stock_xyz_cell_and_grid(self):
        self.p._neo_krea_shift_options = Options(mode=VALUES, values="0,.65,2")
        runner = self.Runner()
        def plot(p):
            # Actual stock XYZ cell and draw loop, using prompt replacement axis.
            ns = module("_xyz", copy=copy, Image=Image, shared=self.e.shared,
                images=NS(GridAnnotation=lambda *a:None, image_grid=lambda imgs, rows:imgs[0]),
                p=p, xs=["red","blue"], ys=[None], zs=[None], process_images=self.processing.process_images_inner,
                vary_seeds_x=False, vary_seeds_y=False, vary_seeds_z=False, grid_infotext=["grid","grid"])
            definitions("xyz_grid.py", {"draw_xyz_grid", "apply_field"}, ns)
            ns.x_opt=NS(apply=ns.apply_field("prompt"))
            ns.y_opt=ns.z_opt=NS(apply=lambda *a:None)
            cell=next(n for n in ast.walk(tree("xyz_grid.py")) if isinstance(n,ast.FunctionDef) and n.name=="cell")
            exec(compile(ast.Module(body=[cell],type_ignores=[]),"<native XYZ>","exec"),ns.__dict__)
            return ns.draw_xyz_grid(p, ns.xs, [None],[None], ns.xs,[""],[""],ns.cell,False,True,False,"x","y",0)
        runner.selectable_scripts=[NS(args_from=1,args_to=1,run=plot)]
        result=runner.run(self.p,1)
        self.assertEqual([(r[0],r[1]) for r in self.seen],
            [(prompt,shift) for shift in (0,.65,2) for prompt in ("red","blue")])
        self.assertEqual(len(result.images),12)  # main grid + subgrid + two cells, for EACH shift
        self.assertEqual(len(result.infotexts),12)
        self.assertEqual(len(result.all_seeds),12)

    def test_interruption_keeps_finished_list_results(self):
        original=self.processing.process_images_inner
        self.p._neo_krea_shift_options=Options(mode=VALUES,values="0,1,2")
        def partial(child):
            result=original(child)
            self.e.shared.state.interrupted=True
            return result
        result=self.hooks.sequence(self.p,options_for(self.p),partial)
        self.assertEqual(len(result.images),1)
        self.assertEqual(self.seen[0][1],0)

    def test_custom_schedule_and_adaptive_sampler_report_incompatibility(self):
        self.ramp(start=0,end=2)
        self.p.sampler_noise_scheduler_override=lambda n:torch.zeros(n+1)
        with self.assertRaisesRegex(ValueError,"override"):
            self.sampler.get_sigmas(self.p,8)
        self.p.sampler_noise_scheduler_override=None
        self.sampler.func=lambda model,x,sigma_min,sigma_max:None
        with self.assertRaisesRegex(ValueError,"full sigma"):
            self.sampler.get_sigmas(self.p,8)
        self.assertEqual(self.sampler.model_wrap.predictor.shift,1.15)

    def test_ddim_does_not_silently_ignore_ramp_and_errors_restore_request(self):
        self.ramp(start=0,end=2)
        self.p.sampler_name="DDIM"
        with self.assertRaisesRegex(ValueError,"DDIM/PLMS"):
            self.processing.process_images_inner(self.p)
        self.assertEqual(self.p.distilled_cfg_scale,.9)
        self.p.sampler_name="Euler"
        self.p.sampler_noise_scheduler_override=lambda n:torch.zeros(n+1)
        with self.assertRaisesRegex(ValueError,"override"):
            self.processing.process_images_inner(self.p)
        self.assertEqual(self.p.distilled_cfg_scale,.9)
        self.assertEqual(self.p.hr_distilled_cfg,1.39)

    def test_invalid_lists_and_hidden_fields(self):
        self.assertEqual(parse_values(" .65,0, 2,.65 "),(.65,0,2,.65))
        for text in ("",",","0,","nan","inf","-1","25","1,word"):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_values(text)
        self.assertEqual(Options.read(FIXED,"bad",None,None,"bad",None,None),Options())

    def test_extension_entrypoint_registers_and_installs_with_native_interfaces(self):
        self.e.runtime.uninstall()
        callbacks={}
        cb=module("modules.script_callbacks")
        for name in ("before_ui","after_component","model_loaded","script_unloaded"):
            setattr(cb,"on_"+name,lambda fn,name=name:callbacks.update({name:fn}))
        scripts=module("modules.scripts", Script=type("Script",(),{}), AlwaysVisible=object(), ScriptRunner=self.Runner)
        common=module("modules.sd_samplers_common", setup_img2img_steps=self.hooks.img2img_steps)
        stubs={
            "modules":module("modules",script_callbacks=cb,scripts=scripts,processing=self.processing,
                sd_samplers_common=common,infotext_utils=self.e.info,shared=self.e.shared),
            "backend.diffusion_engine.krea":module("backend.diffusion_engine.krea",Krea2=self.e.krea.Krea2),
            "backend.modules.k_prediction":self.e.prediction,
            "modules_forge":module("modules_forge",main_entry=self.e.main,presets=self.e.runtime.presets),
            "modules.sd_samplers_kdiffusion":module("modules.sd_samplers_kdiffusion",KDiffusionSampler=self.Sampler),
        }
        path=Path(__file__).resolve().parents[1]/"scripts/krea_shift_neo.py"
        spec=importlib.util.spec_from_file_location("_entry_test",path)
        entry=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,stubs):
            spec.loader.exec_module(entry)
            callbacks["before_ui"]()
            self.assertIsNotNone(entry._runtime)
            self.addCleanup(entry.uninstall)
            with gr.Blocks():
                script=entry.Script()
                self.assertEqual(len(script.ui(False)),7)
                self.assertEqual(len(script.infotext_fields),7)
            self.assertTrue(self.e.engine().use_shift)
            callbacks["script_unloaded"]()
            self.assertFalse(self.e.engine().use_shift)


if __name__=="__main__":unittest.main()
