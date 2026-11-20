"""Self-contained controls; leave the selectable Script slot free for XYZ."""
from .runtime import DEFAULT_SHIFT, SHIFT_INFO
from .schedules import RAMP, CURVES


def controls(gr, is_img2img=False):
    prefix = "img2img" if is_img2img else "txt2img"
    with gr.Accordion("Krea2 Shift", open=False, elem_id=f"{prefix}_krea_shift_options"):
        fixed = gr.Number(label="Fixed Shift", value=DEFAULT_SHIFT, minimum=0, maximum=24,
                          step=.01, interactive=True, info=SHIFT_INFO, elem_id=f"{prefix}_krea_shift_fixed")
        multiple = gr.Checkbox(label="Run Multiple", value=False, interactive=True,
                              elem_id=f"{prefix}_krea_shift_multiple")
        values = gr.Textbox(label="Shift values", value="", visible=False, interactive=True,
            elem_id=f"{prefix}_krea_shift_values",
            placeholder="Enter comma-separated Shift values, e.g. 0.5, 0.65, 1.15",
            info="One run per value with the same starting seed. With Change during sampling enabled, each value is Shift from; every run ends at Shift to. Prompt X/Y/Z stays available.")
        changing = gr.Checkbox(label="Change during sampling", value=False, interactive=True,
                              elem_id=f"{prefix}_krea_shift_changing")
        with gr.Column(visible=False) as ramp:
            with gr.Row(elem_classes=["krea-shift-endpoints"]):
                start = gr.Number(label="Shift from", value=0.5, minimum=0, maximum=24, step=0.01, interactive=True, elem_id=f"{prefix}_krea_shift_from",
                                  info="Run Multiple uses each listed value instead of this starting value.")
                swap = gr.Button("⇄", size="sm", scale=0, min_width=44,
                                 elem_id=f"{prefix}_krea_shift_swap", elem_classes=["krea-shift-swap"])
                end = gr.Number(label="Shift to", value=1.15, minimum=0, maximum=24, step=0.01, interactive=True, elem_id=f"{prefix}_krea_shift_to")
            swap.click(lambda first,last:(last,first), [start,end], [start,end], queue=False)
            curve = gr.Dropdown(CURVES, value="Linear", label="Transition", interactive=True, elem_id=f"{prefix}_krea_shift_curve")
            switch = gr.Slider(0, 100, value=50, step=1, label="Switch at (%)", visible=False, interactive=True,
                              elem_id=f"{prefix}_krea_shift_switch",
                              info="Hold the starting Shift, then switch to the ending Shift at this point in sampling.")
            hires = gr.Checkbox(label="Apply ramp to Hires. fix too", value=False, visible=not is_img2img, interactive=True,
                               info="Starts a fresh ramp over the refinement pass instead of using Hires. fix Shift below.")
            gr.Markdown("**One image, changing Shift.** Blends step spacing from the starting Shift toward the ending Shift. Either direction works. "
                        "Try your composition Shift first and texture Shift last. Experimental—not a guaranteed separation of layout and detail. "
                        "For img2img, the ramp covers the steps actually sampled. A one-step pass uses From only.")
        hr_fixed = gr.Number(label="Hires. fix Shift", value=DEFAULT_SHIFT, minimum=0, maximum=24,
            step=.01, interactive=True, visible=not is_img2img, elem_id=f"{prefix}_krea_shift_hr_fixed",
            info="Used for Hires. fix unless Apply ramp to Hires. fix too is enabled.")
        gr.Markdown("Krea 2 only. With both checkboxes off, Fixed Shift is used. These controls do not change CFG.")

        def layout(run_multiple, change, apply_hr):
            return (gr.update(visible=run_multiple), gr.update(visible=change),
                    gr.update(interactive=not (run_multiple or change)),
                    gr.update(interactive=not run_multiple),
                    gr.update(interactive=not (change and apply_hr)),
                    gr.update(interactive=not run_multiple))
        for control in (multiple, changing, hires):
            control.change(layout, [multiple,changing,hires], [values,ramp,fixed,start,hr_fixed,swap], queue=False)
        curve.change(lambda value:gr.update(visible=value=="Hold then switch"), [curve],[switch],queue=False)
    fields = [(fixed, "Distilled CFG Scale"),
              (multiple, lambda data:False),  # Restore the selected image, not its entire sweep.
              (values, lambda data:""),
              (changing, lambda data:data.get("Krea Shift mode") == RAMP),
              (start, lambda data:float(data.get("Krea Shift from", .5))),
              (end, lambda data:float(data.get("Krea Shift to", 1.15))),
              (curve, lambda data:data.get("Krea Shift curve", "Linear")),
              (switch, lambda data:float(data.get("Krea Shift switch", 50))),
              (hires, lambda data:str(data.get("Krea Shift hires", "False")).lower()=="true"),
              (hr_fixed, "Hires Distilled CFG Scale")]
    return [fixed,multiple,values,changing,start,end,curve,switch,hires,hr_fixed], fields
