"""Progress totals and optional integration with the real local Neo Queue."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from PIL import Image
from support import make_environment, module
from neo_krea_shift.progress import SequenceProgress
from neo_krea_shift.queue_compat import install


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.totals = []
        self.shared = NS(state=NS(job_count=-1, job_no=0, processing_has_refined_job_count=False),
                         total_tqdm=NS(updateTotal=self.totals.append))
        self.p = NS(n_iter=2, batch_size=3, steps=14, enable_hr=False)

    def test_counts_all_shifts_batches_and_hires_once_not_batch_size(self):
        for hires, jobs, steps in ((False, 8, 112), (True, 16, 152)):
            self.p.enable_hr, self.p.hr_second_pass_steps = hires, 5
            with SequenceProgress(self.shared, self.p, 4) as progress:
                self.assertEqual(self.shared.state.job_count, jobs)
                self.assertEqual(self.totals[-1], steps)
                for i in range(4):
                    progress.begin(i)
                    progress.before_image(self.p)
                    self.assertEqual(self.shared.state.job_count, jobs)
                    self.assertTrue(self.shared.state.processing_has_refined_job_count)
            self.assertFalse(self.shared.state.processing_has_refined_job_count)

    def test_xyz_exact_step_totals_are_multiplied_and_wrapper_restored(self):
        original = self.shared.total_tqdm.updateTotal
        self.p.enable_hr = True
        with SequenceProgress(self.shared, self.p, 4, scripted=True) as progress:
            for i in range(4):
                progress.begin(i)
                # Native XYZ calculates all cells' steps (including Steps axes)
                # before assigning its batch count and entering the first cell.
                self.shared.total_tqdm.updateTotal(120)
                self.shared.state.job_count = 6
                progress.before_image(self.p)
                self.assertEqual(self.shared.state.job_count, 48)
                self.assertEqual(self.totals[-1], 480)
                progress.before_image(self.p)
                self.assertEqual(self.shared.state.job_count, 48)
        self.assertIs(self.shared.total_tqdm.updateTotal, original)

    def test_img2img_only_counts_sampled_steps_and_exception_restores_hooks(self):
        self.p.is_img2img = True
        with SequenceProgress(self.shared, self.p, 4, img2img_steps=lambda p:(14, 6)):
            self.assertEqual(self.totals[-1], 56)
        original = self.shared.total_tqdm.updateTotal
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with SequenceProgress(self.shared, self.p, 4, scripted=True):
                raise RuntimeError("stop")
        self.assertIs(self.shared.total_tqdm.updateTotal, original)


@unittest.skipUnless(os.environ.get("KREA_SHIFT_QUEUE_ROOT"), "Optional Neo Queue installation not configured")
class QueueProgressTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.environ["KREA_SHIFT_QUEUE_ROOT"])
        self.addCleanup(lambda:sys.path.remove(os.environ["KREA_SHIFT_QUEUE_ROOT"]))
        from neo_queue.runtime import QueueRuntime
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.queue = QueueRuntime(self.temp.name)
        self.env = make_environment()
        self.addCleanup(self.env.runtime.uninstall)
        shared = self.env.shared
        shared.opts.data_labels = {}
        shared.opts.forge_unet_storage_dtype = "Automatic"
        shared.prompt_styles = NS(apply_styles_to_prompt=lambda p,s:p, apply_negative_styles_to_prompt=lambda p,s:p)
        self.state = shared.state
        self.state.__dict__.update(job_count=4, job_no=0, sampling_step=0, preview_step=0,
            sampling_steps=14, time_start=0, interrupted=False, skipped=False)
        stubs = {"modules":module("modules", shared=shared, progress=NS(current_task="test"),
                    processing=NS(get_fixed_seed=lambda x:int(x)),
                    rng=NS(ImageRNG=lambda *a,**kw:NS()),
                    sd_models=NS(get_closet_checkpoint_match=lambda _:NS(title="model",name="model"))),
                 "modules_forge":module("modules_forge",main_entry=NS(module_list={}),presets=NS(is_video=lambda _:1)),
                 "neo_queue.integration":module("neo_queue.integration",runtime=self.queue)}
        patcher = patch.dict(sys.modules, stubs)
        patcher.start()
        self.addCleanup(patcher.stop)
        defaults = dict(task="task(test)", txt2img_batch_count=1, txt2img_batch_size=1, script_list=0,
            txt2img_seed=42, txt2img_subseed=52, txt2img_prompt="robot", txt2img_neg_prompt="",
            txt2img_styles=[], txt2img_steps=14, txt2img_cfg_scale=1, txt2img_sampling="Euler",
            txt2img_scheduler="Simple",txt2img_width=1024,txt2img_height=1024,
            txt2img_hr=False,txt2img_hires_steps=0,txt2img_subseed_show=False,txt2img_subseed_strength=0,
            txt2img_krea_shift_multiple=True,txt2img_krea_shift_values="0.1,0.2,0.4,0.5")
        defaults["txt2img_krea_shift_options-checkbox"] = True
        self.values = list(defaults.values())
        self.queue.positions = {key:i for i,key in enumerate(defaults)}
        self.queue.inputs = [NS(elem_id=key) for key in defaults]
        install(self.env.runtime)

    def enqueue(self, native=False):
        if native:
            job = self.queue.begin_native(self.values, None)
        else:
            job = self.queue.enqueue(self.values, ["model", [], "Automatic", "krea"], use_batch=True)
            self.queue.store.claim()
            self.queue.active = dict(job_id=job["id"],owner=None,task_id="test")
        return job

    def child(self, index):
        return NS(iteration=0,n_iter=1,batch_size=1,batch_index=0,steps=14,enable_hr=False,is_hr_pass=False,
            _neo_shift_row_offset=index,all_prompts=["robot"],all_negative_prompts=[""],all_seeds=[42],all_subseeds=[52],
            prompts=["robot"],negative_prompts=[""],seeds=[42],subseeds=[52])

    def test_fourteen_step_runs_report_separate_rows_and_fifty_six_total(self):
        job = self.enqueue()
        self.assertEqual(len(job["rows"]),4)
        self.assertEqual(job["summary"]["count"],4)
        # Do not multiply the actual batch count in the captured request.
        self.assertEqual(job["payload"]["args"][self.queue.positions["txt2img_batch_count"]],1)
        images = []
        for index in range(4):
            p = self.child(index)
            self.queue.update_batch(p)
            self.queue.sampler_started(p,14)
            self.state.preview_step, self.state.sampling_step = 7,6
            view = self.queue.view()["jobs"][0]
            self.assertEqual((view["sampling_total_step"],view["sampling_total_steps"]),(index*14+7,56))
            self.assertEqual(view["current_image"],index+1)
            self.assertEqual(view["rows"][index]["sampling_step"],7)
            self.state.preview_step = 14
            self.queue.sampler_finished(p)
            image = Image.new("RGB", (8,8))
            self.queue.image_processed(p,NS(image=image))
            images.append(image)
            self.state.job_no += 1
            self.state.preview_step = self.state.sampling_step = 0
        self.assertEqual([im._neo_queue_row[1] for im in images],[0,1,2,3])
        self.assertEqual([row["status"] for row in self.queue.store.get(job["id"])["rows"]],["completed"]*4)

    def test_native_generate_and_disabled_panel_plans(self):
        job = self.enqueue(native=True)
        self.assertEqual(len(job["rows"]),4)
        self.queue.update_batch(self.child(0))
        self.assertEqual(self.queue.external["current_rows"],[0])
        self.values[self.queue.positions["task"]] = "task(disabled)"
        self.values[self.queue.positions["txt2img_krea_shift_options-checkbox"]] = False
        other = self.queue.enqueue(self.values,["model",[],"Automatic","krea"],use_batch=True)
        self.assertEqual(len(other["rows"]),1)

    def test_removal_does_not_reuse_a_completed_slot(self):
        from neo_queue.batches import original_row
        job = self.enqueue()
        self.queue.store.remove_image(job["id"],2,protected_through=-1)
        for index in range(4):
            p = self.child(index)
            self.queue.update_batch(p)
            if index == 2:
                self.assertEqual(p.prompts,[])
            else:
                self.assertEqual(original_row(p),index)
        self.assertEqual(self.state.job_count,3)
        self.assertEqual(self.queue.store.get(job["id"])["rows"][2]["status"],"removed")

    def test_invalid_list_is_rejected_before_inserting_a_job(self):
        self.values[self.queue.positions["txt2img_krea_shift_values"]] = "0.1,"
        with self.assertRaises(ValueError):
            self.enqueue()
        self.assertEqual(self.queue.store.jobs,[])

    def test_multi_image_batches_and_hires_have_distinct_slots_and_step_totals(self):
        for name,value in (("txt2img_batch_count",2),("txt2img_batch_size",2),
                           ("txt2img_hr",True),("txt2img_hires_steps",5)):
            self.values[self.queue.positions[name]]=value
        job=self.enqueue()
        self.assertEqual(len(job["rows"]),16)
        done=0
        for run in range(4):
            p=self.child(run)
            p._neo_shift_row_offset=run*4
            p.n_iter,p.batch_size,p.enable_hr,p.hr_second_pass_steps=2,2,True,5
            p.all_prompts,p.all_negative_prompts=["robot"]*4,[""]*4
            p.all_seeds,p.all_subseeds=[42,43,44,45],[52,53,54,55]
            for iteration in range(2):
                p.iteration=iteration
                self.queue.update_batch(p)
                for hires,steps in ((False,14),(True,5)):
                    p.is_hr_pass=hires
                    self.queue.sampler_started(p,steps)
                    self.state.preview_step=steps
                    done+=steps
                    view=self.queue.view()["jobs"][0]
                    self.assertEqual((view["sampling_total_step"],view["sampling_total_steps"]),(done,152))
                    self.queue.sampler_finished(p)
                for batch_index in range(2):
                    p.batch_index=batch_index
                    self.queue.image_processed(p,NS(image=Image.new("RGB",(8,8))))
        self.assertEqual(done,152)
        self.assertEqual([r["seed"] for r in self.queue.store.get(job["id"])["rows"]],[42,43,44,45]*4)

    def test_requeue_new_seeds_repeats_comparison_seed_pattern(self):
        job=self.enqueue()
        self.queue.store.finish(job["id"],"completed")
        requeued=self.queue.requeue_new_seeds(job["id"])
        seeds=[r["seed"] for r in requeued["rows"]]
        self.assertEqual(len(set(seeds)),1)
        self.assertNotEqual(seeds[0],42)
