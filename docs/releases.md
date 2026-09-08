# Release artifacts and offline use

The [candidate release](https://github.com/yeopbong/renderguard/releases/tag/v0.1.0-rc.1) keeps the executable model, generated scenes, experiment records, and final verification evidence together. `artifact-index.json` gives archive sizes and SHA-256 hashes. `release-record.json` records the exact public source, CI jobs, deployment version, and retrieval checks without embedding a self-referential commit hash in source control.

| Artifact | Contents |
|---|---|
| `renderguard-model.tar.gz` | Safe weights, ONNX, preprocessing/model manifest, calibration, training configuration, retained feedback data, and model license |
| `renderguard-scenes.tar.gz` | Original generated PNG pairs and the source grouping, rendering manifest, and generation measurements |
| `renderguard-experiments.tar.gz` | Seed checkpoints, training curves, class metrics, candidate coverage, reliability, replay, timing, and numerical diagnostics |
| `renderguard-final-holdout-v1.tar.gz` | Frozen independently authored HTML, labels, captures, tensors, visual audits, and the corrected model's one-time final evaluation |
| `renderguard-first-training.tar.gz` | Superseded viewport-only experiment and its original model, retained to explain the historical challenge results |

The historical model is not used by the application. Its known capture defect and challenge exposure are recorded in `artifacts/history/capture-height-v1.json`. Exact duplicates in the final holdout remain available for stability checks but are excluded from recognition metrics.

Download the desired archive and compare its SHA-256 to the release index before extracting into the repository root. On macOS use `shasum -a 256 ARCHIVE`; on Linux use `sha256sum ARCHIVE`. Archive paths are relative to the repository. The model bundle can restore the shipped inference and feedback assets; then run:

```sh
.venv/bin/python scripts/verify_model.py
pnpm prepare:web
pnpm build
./scripts/start.sh
```

The verifier checks the ONNX, calibration, safe weights, training configuration, and retained-data checksums and runs actual CPU inference. Once setup has installed the pinned packages and Chromium, PNG analysis, local page capture, review, export, and feedback updates do not require an external API. Full corpus regeneration and first-time generic pretraining initialization have separate preparation costs; the generic upstream weights are fetched only when missing and are checked against their pinned hash.

Recorded screenshot hashes are tied to the documented browser, font environment, and platform. A fresh render on another operating system may differ. The frozen source groups and labels are retained even when rasterization differs; repeated rendering is not another untouched final model evaluation.
