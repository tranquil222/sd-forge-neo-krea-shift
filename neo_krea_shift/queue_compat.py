"""Optional Neo Queue row planning; no queue or Forge files are changed."""
from functools import wraps
import sys

from .schedules import parse_values


def queue_runtime():
    integration = sys.modules.get("neo_queue.integration")
    return getattr(integration, "runtime", None)


def expand_plan(queue, job, values, base_count=None, size=None):
    summary = job["summary"]
    if summary.get("krea_shift_runs") == len(values):
        return job
    base_count = base_count or summary["count"]
    size = size or summary["size"]
    base = job["rows"][:base_count * size]
    rows = [dict(row, krea_shift=value) for value in values for row in base]
    summary = dict(summary, count=base_count * len(values), size=size,
                   krea_shift_runs=len(values), krea_shift_batch_count=base_count)
    queue.store.update(job["id"], summary=summary, rows=rows)
    return queue.store.get(job["id"], job.get("owner"))


def prepare_active_queue(p, values):
    """Also repair a job captured before this adapter was installed."""
    queue = queue_runtime()
    if (queue is None or not getattr(queue, "_krea_shift_plan_installed", False)
            or getattr(p, "is_img2img", False)):
        return
    with queue.active_mutex, queue.store.lock:
        active = queue.active or queue.external
        if active:
            job = queue.store.get(active["job_id"], active["owner"])
            expand_plan(queue, job, values, p.n_iter, p.batch_size)


def install(runtime):
    queue = queue_runtime()
    if queue is None or getattr(queue, "_krea_shift_plan_installed", False):
        return
    # Only attach to the row-based Neo Queue API; other queue extensions and
    # older APIs continue to use ordinary native Forge progress.
    if not all(hasattr(queue, attr) for attr in ("enqueue", "update_batch", "positions", "active_mutex", "store")):
        return
    original_enqueue = queue.enqueue

    @wraps(original_enqueue)
    def enqueue(values, model_values, *args, **kwargs):
        def value(name, default=None):
            index = queue.positions.get("txt2img_krea_shift_" + name)
            return values[index] if index is not None and index < len(values) else default
        shifts = None
        if (model_values[3] == "krea" and value("options-checkbox", False)
                and value("multiple", False)):
            shifts = parse_values(value("values", ""))
        # Validate before inserting a job. Keep its captured controls untouched:
        # each child still renders the original batch, not the expanded total.
        with queue.store.lock:
            job = original_enqueue(values, model_values, *args, **kwargs)
            return expand_plan(queue, job, shifts) if shifts else job

    original_batch = queue.update_batch

    @wraps(original_batch)
    def update_batch(p):
        offset = getattr(p, "_neo_shift_row_offset", None)
        if offset is not None and not hasattr(p, "_neo_shift_queue_bound"):
            p._neo_queue_slots = list(range(offset, offset + len(p.all_prompts)))
            p._neo_shift_queue_bound = True
        return original_batch(p)

    runtime.patch(queue, "enqueue", enqueue)
    runtime.patch(queue, "update_batch", update_batch)
    if hasattr(queue, "requeue_new_seeds"):
        original_reseed = queue.requeue_new_seeds

        @wraps(original_reseed)
        def requeue_new_seeds(*args, **kwargs):
            job = original_reseed(*args, **kwargs)
            base_count = job["summary"].get("krea_shift_batch_count")
            if base_count:
                span = base_count * job["summary"]["size"]
                seeds = [row["seed"] for row in job["rows"][:span]]
                rows = [dict(row, seed=seeds[i % span]) for i, row in enumerate(job["rows"])]
                queue.store.update(job["id"], rows=rows)
                return queue.store.get(job["id"], job.get("owner"))
            return job

        runtime.patch(queue, "requeue_new_seeds", requeue_new_seeds)
    runtime.patch(queue, "_krea_shift_plan_installed", True)
