# Krea 2 Shift for Forge Neo

Expose Krea 2's **Shift** control in the main **txt2img**, **img2img**, and **Hires. fix** panels of [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo).

Uses Forge's existing controls and processing fields—not a second, disconnected slider. No model downloads, extra inference dependencies, or edits to Forge source files.

**0.2.0 adds separate Shift comparisons and experimental within-image Shift ramps.** Open **Krea Shift options** in txt2img or img2img. The normal Shift slider remains the control for fixed Shift.

## Install

1. In Forge Neo, open **Extensions → Install from URL**.
2. Paste `https://github.com/tranquil222/sd-forge-neo-krea-shift` and install.
3. **Fully restart Forge**, then select the **krea** UI preset.

Alternatively, run this from your Forge folder:

```sh
git clone https://github.com/tranquil222/sd-forge-neo-krea-shift extensions/sd-forge-neo-krea-shift
```

Requires a recent **Neo branch with native Krea 2 support and `PredictionFlux`**. This is not a Krea loader for original Forge or AUTOMATIC1111. Tested upstream revisions and test scope are in [TESTING.md](TESTING.md).

## What works

| Feature | Behavior |
| --- | --- |
| txt2img / img2img | Shift changes Krea's actual sampling schedule. |
| Hires. fix | Uses the separate native Hires Shift value. |
| PNG metadata | Forge writes `Shift` and, when applicable, `Hires Shift`. |
| PNG Info → Send to txt2img / img2img | Restores saved values, including zero and decimals. |
| Stock Infinite Image Browsing | Its ordinary **Send to txt2img** and **Send to img2img** metadata paths use the same native fields. No IIB modification required. |
| X/Y/Z plot | Use the existing **Shift** axis. Each cell changes the actual schedule and saves its own value. |
| Preset changes | Manual selection still applies preset defaults. A metadata-driven preset change does not overwrite the pasted settings afterward. |
| Comma-separated Shift list | One run per value, preserving order and using the same starting seed. Works alongside a prompt X/Y/Z plot. |
| Within-image ramp | From → To over the steps actually sampled, in either direction, with seven transition choices. |

[Infinite Image Browsing](https://github.com/zanllp/sd-webui-infinite-image-browsing) is optional. **Send only prompt** intentionally does not restore generation settings. An image must still contain its original generation metadata; a screenshot cannot restore it.

### X/Y/Z example

Select **X/Y/Z plot → X type: Shift**, then enter:

```text
0.5,0.65,0.9,1.15,1.39,1.79
```

Use a fixed seed for comparison. Save the individual images if you want each image's own settings; a grid contains a summary, not a single reproducible Shift for every cell.

## Shift comparisons without occupying X/Y/Z

Under **Krea Shift options**, select **One image per value**, then enter `0.5, 0.65, 1.15` in **Shift values**. The list multiplies the existing batch count/size; with both set to 1, it produces one image per value. A random starting seed is resolved once and reused across values for comparison.

You can still select **X/Y/Z plot** and use its axes for prompts or other settings. Each Shift gets a **complete plot**, with its own saved individual images. Do not also use the native Shift axis in that plot: that axis overrides the list's Shift. The native Hires Shift remains separate. Interrupt keeps completed results; progress is shown per run/plot, not as one combined job.

An individual list image saves its actual native `Shift`, plus the list as provenance. PNG Info/IIB restores that image in **Fixed** mode, not the whole comparison list.

## Change Shift within one image

Select **Change during sampling**, then set **Shift from**, **Shift to**, and **Transition**:

- **Linear**: even transition.
- **Smooth ease in/out**: slower near both ends.
- **Ease in / Ease out**: transition later / earlier.
- **Logarithmic / Exponential**: stronger early / late transition; both allow a zero endpoint.
- **Hold then switch**: hold From, then switch toward To at **Switch at (%)**.

For example, From `0.5`, To `1.15`, 8 steps combines step spacing from those Shifts in that direction **within one generated image**. Reverse the endpoints to reverse the transition. The first interval's Shift contribution is From and the last is To; a one-step pass uses From only. Try the Shift whose composition you like first and the Shift whose texture you like last, but those characteristics are not independent or guaranteed to transfer.

This is an **experimental noise-schedule blend**, not CFG scheduling, a model change, or an image blend. Krea Shift determines the noise grid before sampling. Directly splicing grids can make noise increase at a transition. This extension instead takes each interval width from the native grid for that step's Shift, then normalizes those widths across the pass. Noise remains descending and finishes at the native endpoint. The normalization means the ramp is **not identical to part of either fixed-Shift run**. Equal From/To reproduces the native fixed-Shift schedule exactly.

For **img2img**, the ramp spans only the intervals actually sampled and preserves the native starting noise for From. **Apply ramp to Hires. fix too** restarts the ramp over the refinement pass; when unchecked, refinement keeps the separate native Hires Shift. This does not add sampling steps.

Use a sigma-based sampler, such as **Euler**, with **Simple** or **Beta** for the tested paths. DDIM/PLMS, adaptive samplers that ignore the full sigma grid, and another custom noise-schedule override cannot use the ramp. Fixed Shift and list mode retain the native sampler behavior.

PNG metadata records the mode, endpoints, transition, switch point, Hires option, per-step contributions and `interval-v1` algorithm. **PNG Info and ordinary IIB Send** restore these through the extension's paste fields. Recipients need **version 0.2.0 or later** to reproduce a ramp. Pasting an older/fixed image turns off a previously selected ramp.

## Shift scale

This control is Krea's **mu / logarithmic shift**, not CFG. Its native default is **1.15**. The UI accepts **0–24** in 0.01 increments; zero is genuinely unshifted. The upper range is not a quality recommendation.

ComfyUI nodes do not all use the same scale. If a workflow uses an **AuraFlow-style multiplicative shift**, convert with `mu = ln(shift)`:

| AuraFlow-style shift | This extension's Shift (mu) |
| ---: | ---: |
| 1 | 0 |
| 4 | 1.3863 (about 1.39) |
| 6 | 1.7918 (about 1.79) |
| 8 | 2.0794 (about 2.08) |

If a node already uses mu, do **not** convert it again. This mathematical conversion does not guarantee identical images across different scheduler implementations, checkpoints, LoRAs, or random-number generators. Lower or higher Shift is not universally better.

The equations used here can be inspected in [Neo's predictor](https://github.com/Haoming02/sd-webui-forge-classic/blob/db117cb2ac33f6a11ec281ff71ffd4cd02b2f05a/backend/modules/k_prediction.py).

## Sharing images

Share the **original generated PNG**, plus this extension link. Recipients need a compatible Forge Neo and the same model, VAE, encoder, LoRAs, and generation settings. The extension restores Shift through native PNG Info and IIB. Ramp settings additionally use named `Krea Shift ...` infotext fields.

Civitai may not display every custom metadata field, and transformed/downloaded images may lose metadata. This extension cannot control Civitai's metadata processing. Verify that the downloaded original still shows `Shift: ...` in PNG Info. You can also list the Shift and this extension link in your post.

For native Neo Krea images marked `UI preset: krea` and `Version: neo-2.28` or later that lack Shift, the adapter restores the old fixed **1.15** default. It does not guess a Shift from checkpoint filenames, older predictors, or ComfyUI workflow data. Explicit saved values always win; Forge's metadata skip settings remain respected.

## Compatibility and removal

- No separate X/Y/Z entry is installed, and IIB itself is not patched.
- Does not change the predictor class globally or alter other models' sampling behavior.
- Avoid combining with extensions that replace Krea's predictor with a legacy implementation. This extension reports an explicit error for an incompatible predictor instead of silently ignoring Shift.
- Existing Neo customizations that already split preset layout updates from default application are detected; their event wiring is left alone.
- Disable/uninstall through Extensions and **fully restart Forge**. Do not rely on a browser refresh to remove runtime patches from an already loaded model.

## Development

[Testing instructions and results](TESTING.md). Licensed under [AGPL-3.0](LICENSE); see [NOTICE](NOTICE).
