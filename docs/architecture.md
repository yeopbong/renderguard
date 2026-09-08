# Architecture

RenderGuard keeps image observations, declared layout contracts and reviewer decisions separately. Accepting an intentional change preserves its screenshot and predictions.

## Components

| Directory | Role |
| --- | --- |
| `core/` | Shared TypeScript differences, candidates, masks, coordinates and model tensors. |
| `capture/` | Playwright capture, PNG decoding and DOM contracts. |
| `ml/` | Scene generation, rendered labels, training and evaluation. |
| `server/` | FastAPI, background jobs, ONNX CPU inference and SQLite review events. |
| `web/` | React workbench and browser-local ONNX inference in a Worker. |

One local Python process serves the built frontend and API. Local preprocessing calls the same TypeScript functions as the browser and supplies their float32 tensors to Python inference.

## Reports and reviews

Original PNGs and predictions are immutable. Reviews append events with previous/new values, model version and input hashes; Undo appends an inverse event. Baseline updates retain an undoable history. New captures and model runs create new analyses.

SQLite transactions commit metadata and review events; files use atomic replacement. Jobs interrupted by a restart require an explicit retry. Model, input and configuration hashes identify the run.

`python -m server.cli` generates a report. `python -m server.gate report.json` checks it with this precedence:

| Exit code | Meaning |
| --- | --- |
| 3 | Invalid input; failed, cancelled or incomparable execution; missing required evidence. |
| 2 | Confirmed defect or declared-contract violation. |
| 1 | Unreviewed or uncertain visual change. |
| 0 | Valid, complete report with no blocking items. |

Model scores never approve candidates. Marking a visual change intentional does not clear a contract violation; change the contract in a new capture to evaluate a different requirement. A report with no declared contracts needs no contract results. PNG imports have no DOM conclusions.

## Images and resource limits

Report coordinates are original image pixels. Capture uses Playwright `scale: css`, producing one pixel per CSS pixel even at DPR 2. Same-width pages can have different heights; each keeps its valid rectangle and a common origin. Width mismatches are rejected.

All paths accept at most 4096 px width and 32768 px height, with these additional limits:

| Input | PNG bytes per image | Pixels per image | Masks |
| --- | --- | --- | --- |
| Shared Node decoder | 40 MiB | 33,554,432 | 256 |
| Browser | 24 MiB | 24,000,000 | 256 |
| Local API | 18 MiB | 32,000,000 | 64 |

The local workbench also limits combined PNG bytes to 36 MiB; the API limits JSON requests to 50 MiB. Inputs over these limits are rejected. Excessive connected regions use 512 px review tiles; more than 256 candidates requires splitting the input.

Masks are recorded and excluded from differences and crops. The viewer marks them with gray hatching and height-only areas with magenta. PNG samples use sRGB values without separate ICC/gamma transforms. The shared decoder supports palette, gray/gray-alpha and RGB/RGBA formats, including supported 16-bit input; interlaced PNGs are rejected.

## Review order

Candidates sort by the maximum observation score multiplied by its severity weight, plus `0.05 × min(1, changed pixels / comparison canvas pixels)`. Weights are Low (0.5), Normal (1) and High (2), initially Normal. Changed-pixel count breaks ties. Uncalibrated classes use sigmoid(logit) for sorting and show their raw logit/status in the evidence panel.

The observation filter selects logits at least zero. Other changed regions remain visible as unclassified changes. Sorting and filters leave review decisions and the gate unchanged. DOM contracts measure rectangular geometry; they do not establish clickability or arbitrary occlusion.
