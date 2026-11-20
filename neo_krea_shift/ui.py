"""Always-on controls leave Forge's selectable Script slot free for prompt XYZ."""
from .schedules import FIXED, VALUES, RAMP, MODES, CURVES


def controls(gr, is_img2img=False):
    prefix = "img2img" if is_img2img else "txt2img"
    with gr.Accordion("Krea Shift options", open=False, elem_id=f"{prefix}_krea_shift_options"):
        mode = gr.Radio(MODES, value=FIXED, label="Shift mode", interactive=True, elem_id=f"{prefix}_krea_shift_mode")
        values = gr.Textbox(label="Shift values", value="", visible=False, interactive=True,
            elem_id=f"{prefix}_krea_shift_values",
            placeholder="Enter comma-separated Shift values, e.g. 0.5, 0.65, 1.15",
            info="One run per value, using the same starting seed. Prompt X/Y/Z stays available; each value gets a complete plot.")
        with gr.Column(visible=False) as ramp:
            with gr.Row():
                start = gr.Number(label="Shift from", value=0.5, minimum=0, maximum=24, step=0.01, interactive=True, elem_id=f"{prefix}_krea_shift_from")
                end = gr.Number(label="Shift to", value=1.15, minimum=0, maximum=24, step=0.01, interactive=True, elem_id=f"{prefix}_krea_shift_to")
            curve = gr.Dropdown(CURVES, value="Linear", label="Transition", interactive=True, elem_id=f"{prefix}_krea_shift_curve")
            switch = gr.Slider(0, 100, value=50, step=1, label="Switch at (%)", visible=False, interactive=True,
                              elem_id=f"{prefix}_krea_shift_switch",
                              info="Hold the starting Shift, then switch to the ending Shift at this point in sampling.")
            hires = gr.Checkbox(label="Apply ramp to Hires. fix too", value=False, visible=not is_img2img, interactive=True,
                               info="Starts a fresh ramp over the refinement pass. Otherwise the native Hires Shift is unchanged.")
            gr.Markdown("**One image, changing Shift.** Blends step spacing from the starting Shift toward the ending Shift. Either direction works. "
                        "Try your composition Shift first and texture Shift last. Experimental—not a guaranteed separation of layout and detail. "
                        "For img2img, the ramp covers the steps actually sampled. A one-step pass uses From only.")
        gr.Markdown("Krea 2 only. Fixed uses the normal Shift slider. These options do not change CFG.")
        mode.change(lambda value:(gr.update(visible=value==VALUES),gr.update(visible=value==RAMP)),
                    [mode], [values,ramp], queue=False)
        curve.change(lambda value:gr.update(visible=value=="Hold then switch"), [curve],[switch],queue=False)
    fields = [(mode, lambda data:data.get("Krea Shift mode", FIXED)),
              (values, lambda data:""),  # A saved list image restores only its own native Shift.
              (start, lambda data:float(data.get("Krea Shift from", .5))),
              (end, lambda data:float(data.get("Krea Shift to", 1.15))),
              (curve, lambda data:data.get("Krea Shift curve", "Linear")),
              (switch, lambda data:float(data.get("Krea Shift switch", 50))),
              (hires, lambda data:str(data.get("Krea Shift hires", "False")).lower()=="true")]
    return [mode,values,start,end,curve,switch,hires], fields
