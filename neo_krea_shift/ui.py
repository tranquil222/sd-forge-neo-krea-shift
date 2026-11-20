"""Self-contained controls; leave the selectable Script slot free for XYZ."""
from .runtime import DEFAULT_SHIFT, SHIFT_INFO
from .schedules import RAMP, CURVES


def controls(gr, is_img2img=False):
    from modules.ui_components import InputAccordion

    prefix = "img2img" if is_img2img else "txt2img"
    with InputAccordion(False, label="Krea2 Shift", elem_id=f"{prefix}_krea_shift_options") as enabled:
        fixed = gr.Number(label="Fixed Shift", value=DEFAULT_SHIFT, minimum=0, maximum=24,
                          step=.01, interactive=False, info=SHIFT_INFO, elem_id=f"{prefix}_krea_shift_fixed",
                          elem_classes=["krea-shift-value"])
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
                                  elem_classes=["krea-shift-value"],
                                  info="Run Multiple uses each listed value instead of this starting value.")
                swap = gr.Button("⇄", size="sm", scale=0, min_width=44,
                                 elem_id=f"{prefix}_krea_shift_swap", elem_classes=["krea-shift-swap"])
                end = gr.Number(label="Shift to", value=1.15, minimum=0, maximum=24, step=0.01, interactive=True, elem_id=f"{prefix}_krea_shift_to")
            swap.click(lambda first,last:(last,first), [start,end], [start,end], queue=False)
            curve = gr.Dropdown(CURVES, value="Linear", label="Transition", interactive=True,
                                elem_id=f"{prefix}_krea_shift_curve",
                                info="Exponential starts slowly, then speeds up. Reverse exponential starts quickly, then eases toward Shift to. Both work in either direction.")
            switch = gr.Slider(0, 100, value=50, step=1, label="Switch at (%)", visible=False, interactive=True,
                              elem_id=f"{prefix}_krea_shift_switch",
                              info="Hold the starting Shift, then switch to the ending Shift at this point in sampling.")
        with gr.Accordion("Hires. fix & details" if not is_img2img else "Details", open=False,
                          elem_id=f"{prefix}_krea_shift_details"):
            hires = gr.Checkbox(label="Apply ramp to Hires. fix too", value=False, visible=not is_img2img, interactive=False,
                               elem_id=f"{prefix}_krea_shift_hires",
                               info="Starts a fresh ramp over the refinement pass instead of using Hires. fix Shift below.")
            hr_fixed = gr.Number(label="Hires. fix Shift", value=DEFAULT_SHIFT, minimum=0, maximum=24,
                step=.01, interactive=False, visible=not is_img2img, elem_id=f"{prefix}_krea_shift_hr_fixed",
                elem_classes=["krea-shift-value"],
                info="Used for Hires. fix unless Apply ramp to Hires. fix too is enabled.")
            gr.Markdown("**One image, changing Shift.** Blends step spacing from the starting Shift toward the ending Shift. Either direction works. "
                        "Try your composition Shift first and texture Shift last. Experimental—not a guaranteed separation of layout and detail. "
                        "For img2img, the ramp covers the steps actually sampled. A one-step pass uses From only.")
            gr.Markdown("Krea 2 only. Enable the panel checkbox to apply these settings. "
                        "When disabled, Forge's native Shift and X/Y/Z settings are left alone. "
                        "With Run Multiple and Change during sampling off, Fixed Shift is used. These controls do not change CFG.")

        def layout(active, run_multiple, change, apply_hr):
            return (gr.update(visible=run_multiple, label="Shift from values" if change else "Shift values",
                              placeholder="Enter comma-separated starting Shift values, e.g. 0.5, 0.65, 1.15" if change else
                                          "Enter comma-separated Shift values, e.g. 0.5, 0.65, 1.15"),
                    gr.update(visible=change),
                    gr.update(interactive=active and not (run_multiple or change)),
                    gr.update(interactive=active and not run_multiple),
                    gr.update(interactive=active and not (change and apply_hr)),
                    gr.update(interactive=active and not run_multiple),
                    gr.update(interactive=active and change))
        for control in (enabled, multiple, changing, hires):
            control.change(layout, [enabled,multiple,changing,hires], [values,ramp,fixed,start,hr_fixed,swap,hires], queue=False)
        curve.change(lambda value:gr.update(visible=value=="Hold then switch"), [curve],[switch],queue=False)
    fields = [(fixed, "Distilled CFG Scale"),
              (multiple, lambda data:False),  # Restore the selected image, not its entire sweep.
              (values, lambda data:data.get("Krea Shift list", "")),
              (changing, lambda data:data.get("Krea Shift mode") == RAMP),
              (start, lambda data:float(data.get("Krea Shift from", .5))),
              (end, lambda data:float(data.get("Krea Shift to", 1.15))),
              (curve, lambda data:data.get("Krea Shift curve", "Linear")),
              (switch, lambda data:float(data.get("Krea Shift switch", 50))),
              (hires, lambda data:str(data.get("Krea Shift hires", "False")).lower()=="true"),
              (hr_fixed, lambda data:float(data.get("Krea Shift hires fixed", data.get("Hires Distilled CFG Scale", DEFAULT_SHIFT)))),
              (enabled, restore_enabled)]
    return [fixed,multiple,values,changing,start,end,curve,switch,hires,hr_fixed,enabled], fields


def restore_enabled(data):
    """Old Krea PNGs activate the adapter; unrelated images turn it off."""
    if "Krea Shift enabled" in data:
        return str(data["Krea Shift enabled"]).lower() == "true"
    return ("Krea Shift mode" in data or
            (data.get("UI preset") == "krea" and "Distilled CFG Scale" in data))
