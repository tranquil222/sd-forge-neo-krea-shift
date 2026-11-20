# Validation

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

Use a Python environment with `torch`, `numpy`, `Pillow` and `gradio==4.40.0` (for example, a compatible Neo venv). Run from this repository:

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
