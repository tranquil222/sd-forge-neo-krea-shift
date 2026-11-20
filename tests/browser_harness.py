"""Small real-Gradio harness for stock Neo + stock IIB metadata transfer.

No Forge server, model weights, GPU, network shares, or user settings are loaded.
"""
import logging
import os
from pathlib import Path

import gradio as gr
from PIL import Image, PngImagePlugin

from support import make_environment, generated_infotext, definitions, module
from neo_krea_shift.ui import controls
from neo_krea_shift.schedules import Options, RAMP, metadata

env = make_environment()
env.runtime.install()
artifacts = Path(os.environ["KREA_SHIFT_TEST_ARTIFACTS"])
artifacts.mkdir(parents=True, exist_ok=True)
for shift in (0, .65, 1.39, 4.02):
    meta = PngImagePlugin.PngInfo()
    meta.add_text("parameters", generated_infotext(env, shift, .9))
    Image.new("RGB", (16, 16), "orange").save(artifacts / f"shift-{shift}.png", pnginfo=meta)
ramp_options = Options(mode=RAMP, start=0, end=2, curve="Hold then switch", switch=70, hires=True)
meta = PngImagePlugin.PngInfo()
meta.add_text("parameters", generated_infotext(env, 0, .9,
              extra=metadata(ramp_options, ramp_options.progression(8))))
Image.new("RGB", (16,16), "orange").save(artifacts / "shift-ramp.png", pnginfo=meta)

iib = module("_test_iib", gr=gr, Image=Image, send=env.info, locale="en",
             send_img_path={}, logger=logging.getLogger("iib-test"))
# IIB's actual reader takes the native PNG parameters path before any fallback.
definitions("iib_tool.py", {"read_sd_webui_gen_info_from_image"}, iib)
definitions("iib_setup.py", {"on_ui_tabs"}, iib)

with gr.Blocks(analytics_enabled=False,
               css=(Path(__file__).resolve().parents[1]/"style.css").read_text()) as demo:
    gr.Markdown("Krea2 Shift integration test — stock Neo functions / stock IIB bridge")
    preset = gr.Dropdown(["krea", "flux"], value="krea", label="UI Preset", elem_id="forge_ui_preset")
    env.runtime.after_component(preset)
    targets = [gr.Textbox(visible=False) for _ in range(17)]
    shifts = []
    for ident in ("txt2img_distilled_cfg_scale", "txt2img_hr_distilled_cfg", "img2img_distilled_cfg_scale"):
        slider = gr.Slider(1, 24, value=1.15, step=.5, label=ident, elem_id=ident)
        env.runtime.after_component(slider)
        shifts.append(slider)
    targets += shifts + [gr.Slider(1, 8, value=1), gr.Slider(1, 8, value=1)]
    preset.change(env.main.on_preset_change, inputs=[preset], outputs=targets, queue=False)
    demo.load(env.main.on_preset_change, inputs=[preset], outputs=targets, queue=False)

    fields = [(shifts[0], "Distilled CFG Scale"), (shifts[1], "Hires Distilled CFG Scale"),
              (preset, "UI preset")]
    _, ramp_fields = controls(gr)
    _, i2i_ramp_fields = controls(gr, True)
    fields += ramp_fields
    i2i_fields = [(shifts[2], "Distilled CFG Scale"), (preset, "UI preset")] + i2i_ramp_fields
    info = gr.Textbox(label="PNG Info metadata", elem_id="png_metadata")
    png = gr.Image(type="pil", label="PNG Info source", elem_id="png_source")
    png.change(lambda image: image.info.get("parameters", "") if image else "", inputs=png, outputs=info)
    send = gr.Button("PNG Info — Send to txt2img", elem_id="png_send")
    env.info.connect_paste(send, fields, info, None, "txt2img")
    send_i2i = gr.Button("PNG Info — Send to img2img", elem_id="png_send_i2i")
    env.info.connect_paste(send_i2i, i2i_fields, info, None, "img2img")

    # A path selector stands in for IIB's Vue file browser/API, but image loading,
    # its PNG reader, ParamBinding registration and Send buttons are unmodified.
    path = gr.Textbox(label="IIB selected file", elem_id="iib_path")
    choose = gr.Button("Select IIB file", elem_id="iib_choose")
    ready = gr.Textbox(label="Selected", elem_id="iib_ready")
    def select(filename):
        iib.send_img_path["value"] = filename
        return filename
    choose.click(select, inputs=path, outputs=ready)
    iib.on_ui_tabs()
    for binding in env.info.registered_param_bindings:
        if binding.tabname in ("txt2img", "img2img"):
            dest = fields if binding.tabname == "txt2img" else i2i_fields
            env.info.connect_paste(binding.paste_button, dest, binding.source_text_component, None, binding.tabname)

demo.launch(server_name="127.0.0.1", server_port=7863, inbrowser=False,
            allowed_paths=[str(artifacts)], quiet=True)
