# Krea 2 Shift for Forge Neo

Expose Krea 2's **Shift** control in the main **txt2img**, **img2img**, and **Hires. fix** panels of [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo).

Uses Forge's existing controls and processing fields—not a second, disconnected slider. No model downloads, extra inference dependencies, or edits to Forge source files.

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

[Infinite Image Browsing](https://github.com/zanllp/sd-webui-infinite-image-browsing) is optional. **Send only prompt** intentionally does not restore generation settings. An image must still contain its original generation metadata; a screenshot cannot restore it.

### X/Y/Z example

Select **X/Y/Z plot → X type: Shift**, then enter:

```text
0.5,0.65,0.9,1.15,1.39,1.79
```

Use a fixed seed for comparison. Save the individual images if you want each image's own settings; a grid contains a summary, not a single reproducible Shift for every cell.

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

Share the **original generated PNG**, plus this extension link. Recipients need a compatible Forge Neo and the same model, VAE, encoder, LoRAs, and generation settings. The extension restores Shift through native PNG Info and IIB—not through a private metadata format.

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
