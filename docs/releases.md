# Downloads and offline use

[**v0.1.0-rc.2**](https://github.com/yeopbong/renderguard/releases/tag/v0.1.0-rc.2) fixes gate validation and simplifies the documentation. It remains a candidate release and uses the unchanged rc.1 model.

The existing model and experiment downloads remain attached to [v0.1.0-rc.1](https://github.com/yeopbong/renderguard/releases/tag/v0.1.0-rc.1). Its `artifact-index.json` lists archive sizes and SHA-256 hashes.

| Archive | Contents |
| --- | --- |
| `renderguard-model.tar.gz` | Safe weights, ONNX, manifest, calibration, training configuration, retained feedback data and model license. |
| `renderguard-scenes.tar.gz` | Generated PNG pairs, source groups and rendering manifest. |
| `renderguard-experiments.tar.gz` | Checkpoints, curves, class metrics, coverage, calibration, replay, timing and numerical diagnostics. |
| `renderguard-final-holdout-v1.tar.gz` | Frozen HTML, labels, captures, tensors and final evaluation. |
| `renderguard-first-training.tar.gz` | Historical viewport-only experiment and its superseded model. |

Check a downloaded archive with `shasum -a 256 ARCHIVE` on macOS or `sha256sum ARCHIVE` on Linux, then extract it into the repository root. To restore the shipped model from the model bundle:

```sh
.venv/bin/python scripts/verify_model.py
pnpm prepare:web
pnpm build
./scripts/start.sh
```

After setup installs dependencies and Chromium, PNG analysis, local page capture, review and export work without an external API. First-time training also downloads the pinned upstream initialization. Rendering on another operating system may produce different pixels; the original screenshots and labels remain in the archives.
