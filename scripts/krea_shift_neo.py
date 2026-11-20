"""Entrypoint loaded by Forge Neo's extension loader."""
import logging

from modules import script_callbacks, scripts

_runtime = None


def install():
    global _runtime
    if _runtime is not None:
        return
    runtime = None
    try:
        import gradio as gr
        from backend.diffusion_engine.krea import Krea2
        from backend.modules.k_prediction import PredictionFlux
        from modules import infotext_utils, shared
        from modules_forge import main_entry, presets
        from neo_krea_shift.runtime import Runtime

        runtime = Runtime(engine_class=Krea2, predictor_type=PredictionFlux,
                          main_entry=main_entry, infotext=infotext_utils,
                          shared=shared, presets=presets, gr=gr)
        runtime.install()
        from modules import processing, sd_samplers_common
        from modules.sd_samplers_kdiffusion import KDiffusionSampler
        from neo_krea_shift.jobs import JobHooks
        JobHooks(runtime, processing, scripts, KDiffusionSampler,
                 sd_samplers_common.setup_img2img_steps).install()
        _runtime = runtime
        logging.getLogger(__name__).info("Krea2 Shift loaded. Enable its panel checkbox to apply fixed Shift, multiple runs or per-step ramps.")
    except (ImportError, AttributeError) as error:
        if runtime is not None:
            runtime.uninstall()
        logging.getLogger(__name__).error("Krea Shift unavailable on this Forge build: %s", error)


def after_component(component, **kwargs):
    if _runtime is not None:
        _runtime.after_component(component, **kwargs)


def model_loaded(engine):
    if _runtime is not None:
        _runtime.model_loaded(engine)


def app_started(demo, app):
    if _runtime is not None:
        from neo_krea_shift.queue_compat import install as install_queue
        install_queue(_runtime)


def uninstall():
    global _runtime
    if _runtime is not None:
        _runtime.uninstall()
        _runtime = None


script_callbacks.on_before_ui(install)
script_callbacks.on_after_component(after_component)
script_callbacks.on_model_loaded(model_loaded)
script_callbacks.on_app_started(app_started)
script_callbacks.on_script_unloaded(uninstall)


class Script(scripts.Script):
    neo_krea_shift_controls = True

    def title(self):
        return "Krea2 Shift"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        import gradio as gr
        from neo_krea_shift.ui import controls
        components, self.infotext_fields = controls(gr, is_img2img)
        return components
