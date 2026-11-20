# Validation

## Release 0.4.2

**44 CPU checks passed locally**, including the optional custom IIB and real Neo Queue checks. Added coverage confirms that separate queue clicks preserve all Shift controls independently after subsequent UI changes and a disk reload, including fixed, combined list/ramp, descending ramp, Hires, and disabled-panel settings. Interrupting the current list retains its completed image and makes the next queued job eligible to run.

Reverse exponential is checked for a fast start and gradual finish in both directions, endpoint preservation, and time symmetry with Exponential. The existing native Simple/Beta schedule checks now cover all eight transitions, and the native metadata round-trip check includes the new curve.

Headless Chrome/Gradio browser checks passed: restored Run Multiple-before-Change layout, Reverse exponential selection and stock IIB restoration, existing PNG Info transfers to both tabs, enabled state, greyed-out overrides, dynamic labels, and From/To swap. These are CPU integration and browser checks, not GPU inference or image-quality tests. No queue source files or live Forge processes were changed by these checks.

## Release 0.4.1

**41 CPU checks passed locally**, including the optional custom IIB and real Neo Queue integration tests. Coverage includes four 14-step runs reporting 56 total steps and distinct current rows, multiple-image batches plus Hires, captured batch settings not being multiplied twice, normal Generate, disabled panels, removed rows, requeue seed patterns, native prompt XYZ counts and exact XYZ step totals. Temporary progress hooks are restored after exceptions. The 9 progress/queue checks also passed against the development copy's Queue installation; the 21 job checks passed against the main-copy source snapshot.

Browser checks verify the new control order, simplified Shift help text, greyed-out overrides, and existing PNG/IIB restoration. These checks do not run GPU inference. To enable the optional real-Queue tests, set `KREA_SHIFT_QUEUE_ROOT` to a compatible Neo Queue extension folder; all queue files created by those tests live in a temporary directory, not the user's queue.

## Release 0.4.0

Adds the native Forge header enable checkbox, collapsed Hires/details, visibly disabled overridden values, and the **Shift from values** label when multiple runs each use a ramp. Disabled panels bypass their fixed/list/ramp settings without validating inactive inputs. Metadata restores enabled/disabled state, actual Shift and Hires values, and applicable ramp settings; old Krea PNGs remain compatible.

**32 CPU checks passed locally**, including custom IIB normal/legacy transfers. The browser checks passed with the actual pinned Forge InputAccordion component and JavaScript: default-off header, nested collapsed details, disabled field styling, both list labels, combined controls, swap, and PNG/stock IIB restoration in both tabs. The 21 job checks passed against source snapshots of both local installations as well. Native XYZ Hires Shift overrides are preserved in the plugin metadata.

These are CPU integration and browser checks, not GPU image-quality tests.

## Release 0.3.0

Adds plugin-owned Fixed Shift and Hires. fix Shift fields, independent Run Multiple / Change during sampling checkboxes, and the **Krea2 Shift** panel name. The main-row Krea controls are hidden without changing other models' controls or editing Forge core.

The CPU suite additionally checks that the plugin field overrides an unrelated hidden-row value, every multiple-run item can have its own ramp, the combined mode works through stock prompt XYZ, native Shift XYZ axes still override the starting value, and a selected sweep image restores only its own settings through PNG Info/IIB. The browser harness checks the panel name, hidden native controls, fixed field, both checkboxes enabled together, and metadata restoration.

**29 CPU checks passed locally**, including custom IIB, plus the browser checks and bidirectional From/To swap. The 18 job/schedule checks also passed against source snapshots of both local Forge installations (the customized main-copy test harness additionally supplies its existing inpaint metadata helper and XYZ images-only flag).

No GPU image-quality comparison is implied by these integration checks.

## Release 0.2.0

The same pinned Neo/IIB source revisions below are used. Tests execute the actual native sigma scheduler, txt2img/img2img sampler plumbing, ScriptRunner, XYZ cell/grid loop, and PNG parser/paste code on CPU. Heavyweight model inference is replaced by a small stub that captures the schedule delivered to the sampler.

Additional checks cover:

- Ascending/descending ramps for every curve, including zero and extreme endpoints, using native Simple and Beta schedules.
- Descending finite sigma grids ending at zero; equal endpoints exactly reproduce native fixed Shift.
- Real img2img suffix selection, one-step passes, penultimate-sigma removal and separate Hires behavior.
- Comma-list expansion with matching seeds, saved per-image Shift, interruption preserving completed results, and all Shift × prompt combinations through the stock XYZ path.
- No ramp/list expansion for non-Krea engines; explicit errors for incompatible ramp sampler/override paths; request fields restored after failures.
- Ramp settings round-trip through the native infotext writer/parser and always-on paste fields; fixed metadata clears a previous ramp.
- The optional custom IIB normal and legacy handlers restore ramp settings too.

The browser harness also exercises the new controls, comma placeholder, mode visibility, PNG ramp restoration in both tabs, and complete ramp restoration through stock IIB's reader/bridge. The UI controls are explicitly interactive, including when used as paste destinations.

**25 CPU checks passed locally**, including the optional custom IIB check and extension entrypoint installation/uninstallation. All browser checks passed in headless Chrome with Gradio 4.40.0. Without the custom adapter, its one optional test is skipped.

This validates plumbing and reproducibility metadata, **not the visual quality of composition/texture blending**. No GPU quality comparison was run for the ramp feature.

## Release 0.1.0

Validated on Windows with Python 3.13.1, PyTorch 2.10.0 and Gradio 4.40.0.

| Source | Pinned revision |
| --- | --- |
| Forge Neo | [`db117cb2`](https://github.com/Haoming02/sd-webui-forge-classic/commit/db117cb2ac33f6a11ec281ff71ffd4cd02b2f05a) |
| Stock Infinite Image Browsing | [`ffb2f7cc`](https://github.com/zanllp/infinite-image-browsing/commit/ffb2f7ccb247e98d9a8d0d0f5fb5375f35595891) |

### Automated CPU integration checks

- Execute the real Neo Krea constructor with heavyweight model objects stubbed.
- Apply Shift to the real `PredictionFlux` CPU sigma schedule, including zero, decimals, and restoring the default. Non-Krea engines are unchanged.
- Exercise native preset updates without allowing programmatic changes to overwrite pasted values.
- Use Neo's actual infotext writer, save/reopen a PNG, then use its real parser and field converters to restore Shift.
- Check legacy metadata defaults, alternate native field names, and intentional skip-pasting preferences.
- Execute the stock X/Y/Z cell body and grid loop with real Shift application, checking distinct schedules and per-cell metadata. Image generation itself is stubbed.
- Check invalid inputs, incompatible predictors, already loaded model activation, and patch install/uninstall behavior.
- Optional: execute a custom IIB adapter's normal and legacy transfer handlers against stock Neo's parser with the extension installed.

**11 checks passed locally**, including the optional custom IIB check. The default reproducible suite runs ten checks and skips the optional adapter check.

### Browser checks

A real, headless Chrome browser exercises a small Gradio harness using unmodified upstream functions:

- PNG upload → metadata → native Send to txt2img and img2img.
- Stock IIB's actual PNG reader, image-update bridge, ParamBinding registration and Send buttons → native paste fields.
- Transfers after selecting another preset, plus same-preset pastes.
- Zero, 0.65, 1.39 and 4.02 remain correct after dependent UI callbacks finish.
- Hires Shift remains separate; deliberate preset selection still loads defaults.

All browser checks passed. The harness substitutes a file selector for IIB's Vue gallery/API and does not boot a full Forge instance. This is **not** an end-to-end GPU generation benchmark or a test of Civitai metadata retention. No user's running Forge session, development copy, or model files are needed for these tests.

## Reproduce

Use a Python environment with `torch`, `numpy`, `scipy`, `Pillow` and `gradio==4.40.0` (for example, a compatible Neo venv). Run from this repository:

```powershell
python tests/fetch_upstream.py upstream
$env:KREA_SHIFT_TEST_SOURCE = (Resolve-Path upstream).Path
python -m unittest discover -s tests -v
```

`tests/upstream.json` pins the downloaded revisions. Fixtures are excluded from Git and contain only small source files, not weights.

To run browser checks, launch the harness in one terminal:

```powershell
$env:KREA_SHIFT_TEST_SOURCE = (Resolve-Path upstream).Path
$env:KREA_SHIFT_TEST_ARTIFACTS = Join-Path (Get-Location) artifacts
$env:GRADIO_ANALYTICS_ENABLED = 'False'
python tests/browser_harness.py
```

In another terminal, with the same artifact environment variable:

```powershell
npm install --no-save playwright-core
$env:CHROME_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
node tests/browser_test.cjs
```

The harness listens only on `127.0.0.1:7863`. Stop it with Ctrl+C afterward. `PLAYWRIGHT_CORE` can point to an already installed `playwright-core` package. `KREA_SHIFT_CUSTOM_IIB` optionally points to a compatible custom `metadata_transfer.py` adapter; it is not needed for stock IIB tests.
