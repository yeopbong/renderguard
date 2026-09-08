# RenderGuard

Review webpage visual changes with screenshot differences, a visual observation model, layout contracts and per-region review decisions.

[Open the browser demo](https://yeopbong.github.io/renderguard/) · [Candidate release](https://github.com/yeopbong/renderguard/releases/tag/v0.1.0-rc.2)

![The RenderGuard comparison workbench](docs/screenshots/workbench.png)

## Review a change

1. Create a project and save a baseline screenshot.
2. Import a changed PNG, or capture a local page with the local application.
3. Inspect the differences and model observations. Mark each region **Confirm defect**, **Intentional change** or **Uncertain**.
4. Export a JSON or self-contained HTML report. Updating the baseline is a separate, reversible action.

The browser demo supports PNGs, examples, persistent reviews and offline reports. Images stay in your browser; the ONNX model runs locally in a Worker. URL capture, DOM contracts and explicit feedback training are available in the local application.

Results assist review and can miss visual symptoms, especially clipping; boundary-crossing false positives also occur. Scores are observation estimates, not bug probabilities. Unreviewed changes remain pending even at low scores. Same-width pages may differ in height; width mismatches are rejected. PNG imports have unverified capture conditions.

## Start locally

Requires **Python 3.12**, **Node.js 22.12 or later** and **pnpm 11.19.0**. Setup downloads pinned dependencies and Chromium; the inference model is included in the repository.

```sh
git clone https://github.com/yeopbong/renderguard.git
cd renderguard
./scripts/setup.sh
./scripts/start.sh
```

Open **http://127.0.0.1:8765**. Projects are saved in `workspace/`; keep it private. To choose another location, run `./scripts/start.sh --workspace /path/to/private/reviews`.

Local use has been tested on macOS arm64. Linux also needs Chromium system libraries: run `pnpm exec playwright install-deps chromium` after installing Node dependencies; this may require administrator privileges.

## Run the included case

Start the example pages in one terminal:

```sh
.venv/bin/python examples/serve.py
```

Then capture and check the main case:

```sh
.venv/bin/python -m server.cli --capture examples/main/capture.json --output workspace/main-report.json
.venv/bin/python -m server.gate workspace/main-report.json
```

The main case exits 2 because a declared contract is violated. `examples/intentional/capture.json` stays at 1 until reviewed; `examples/failure/capture.json` exits 3 for a missing required selector.

Gate codes are **0** no blocking items, **1** unreviewed or uncertain change, **2** confirmed defect or contract violation, and **3** invalid input, failed execution or incomplete evidence. Errors take priority. See [architecture](docs/architecture.md) for report semantics and input limits.

## Development

```sh
pnpm prepare:web
pnpm build
node --import tsx --test tests/core*.test.ts
.venv/bin/python -m pytest -q
node --import tsx --test tests/browser*.test.ts
```

See [experiments](docs/experiments.md) for saved results and reproduction commands, [data](docs/data.md) for the scene corpus, [model](docs/model.md) for training and feedback updates, and [downloads](docs/releases.md) for offline assets. Full training is separate from routine tests.

Application code is [MIT](LICENSE); authored scene content and images are CC0-1.0. The model derives from Apache-2.0 MobileNetV3 weights. [Model license](artifacts/MODEL-LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)
