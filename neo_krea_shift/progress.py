"""One native progress total for a Shift list, including nested XYZ plots."""


class SequenceProgress:
    def __init__(self, shared, p, count, scripted=False, img2img_steps=None):
        self.shared, self.p, self.count, self.scripted = shared, p, count, scripted
        self.passes = 2 if getattr(p, "enable_hr", False) else 1
        self.iterations = max(1, int(p.n_iter))
        self.per_plot, self.global_count = self.iterations, None
        steps = p.steps
        if getattr(p, "is_img2img", False) and img2img_steps:
            _, encoded = img2img_steps(p)
            steps = encoded + 1
        self.steps = self.iterations * (steps + (getattr(p, "hr_second_pass_steps", 0) or p.steps)
                                       if self.passes == 2 else steps)

    def __enter__(self):
        state = self.shared.state
        self.refined = getattr(state, "processing_has_refined_job_count", False)
        self.total = self.shared.total_tqdm
        self.update_total = getattr(self.total, "updateTotal", None)
        self.own_update = "updateTotal" in vars(self.total)
        if not self.scripted:
            state.job_count = self.count * self.iterations * self.passes
            state.processing_has_refined_job_count = True
        if self.scripted and self.update_total:
            # XYZ knows its Steps/Hires-steps axes. Scale its exact total rather
            # than estimating from the parent request's single Steps value.
            self.total.updateTotal = lambda value: self.update_total(value * self.count)
        elif self.update_total:
            self.update_total(self.steps * self.count)
        return self

    def begin(self, index):
        self.index, self.first = index, True
        self.shared.state.job = f"Shift {index + 1} out of {self.count}"

    def before_image(self, p):
        if self.first and self.scripted:
            # draw_xyz_grid sets its own count before its first cell. Account
            # for every Shift plot, and include Hires exactly once ourselves.
            state = self.shared.state
            observed = getattr(state, "job_count", -1)
            if observed != self.global_count:
                self.per_plot = max(self.iterations, observed)
            self.global_count = self.per_plot * self.count * self.passes
            state.job_count = self.global_count
            state.processing_has_refined_job_count = True
        self.first = False

    def __exit__(self, *exc):
        if self.scripted and self.update_total:
            if self.own_update:
                self.total.updateTotal = self.update_total
            else:
                del self.total.updateTotal
        self.shared.state.processing_has_refined_job_count = self.refined
