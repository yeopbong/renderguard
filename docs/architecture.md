# Architecture and result semantics

RenderGuard is a local research workbench for reviewing visible changes. A difference is evidence that pixels changed. An observation is a visual symptom; a contract is a previously declared requirement; a decision is a reviewer conclusion. These are stored separately. Accepting an intentional move does not remove the displacement prediction.

## Modules

- `core/`: browser-safe TypeScript candidate detection, masks, image coordinates, local/context letterbox tensors and resource bounds.
- `capture/`: pinned Playwright Chromium capture, image decoding, shared tensor generation and explicit DOM constraints.
- `ml/`: original scene generation, independent rendered-evidence validation, grouped datasets, supervised training and evaluation.
- `server/`: FastAPI, bounded background work, ONNX CPU inference and SQLite append-only review events.
- `web/`: React workbench and a single-thread WebAssembly Worker for browser-local inference.

The production build is served by one local Python process. TypeScript preprocessing runs as a subprocess for local inference. Python consumes its float32 tensors directly; it has no separate image-crop implementation. The browser uses the same TypeScript candidate and tensor functions.

## Evidence and lifecycle

Original PNG files and run predictions are immutable. The database stores run evidence once and records subsequent review actions as events containing old/new values, timestamp, model version and input hashes. Undo appends an inverse event. A new screenshot or model run creates a new analysis; approvals are never silently reused. A baseline update points to an immutable original image and retains an undoable history.

SQLite transactions commit metadata and review events; file output uses an atomic replacement. On startup, queued/running jobs become interrupted and require explicit retry; completed artifacts remain. Candidate/model/inputs/configuration hashes form the cache identity. No automatic cross-run reuse currently skips computation.

## Gate policy

The command `python -m server.cli` returns successful analysis separately from the gate embedded in its report. `python -m server.gate report.json` exits with:

| Code | Meaning |
| --- | --- |
| 3 | Missing, failed, cancelled, incomparable or incomplete required evidence |
| 2 | A confirmed defect or a measured declared-contract violation |
| 1 | Any visual change remains unreviewed or uncertain |
| 0 | No blocking items under this declared policy |

Precedence follows table order. Scores never automatically approve a candidate. A contract violation remains a violation even if a reviewer calls the visual change intentional; revise the contract in a new capture to evaluate a different requirement. Projects without declared contracts do not have a constraint execution error. Imported PNGs have unverified capture conditions and no invented DOM conclusions.

## Coordinates and limits

Coordinates in reports are original image pixels. Capture uses Playwright `scale: css`, so even a DPR 2 browser produces one image pixel per CSS pixel; both DPR and scale are recorded. Same-width pages of different heights retain a common origin and their own valid rectangles. Added/removed page height is explicit evidence, not white page content. Width mismatches are rejected, never stretched.

The shared pipeline accepts at most 4096 px width, 32768 px height and 33,554,432 pixels per image. Input paths apply these additional bounds:

| Input path | PNG bytes per image | Pixels per image | Declared masks |
| --- | --- | --- | --- |
| Shared Node decoder | 40 MiB | 33,554,432 | 256 |
| Browser PNG workbench | 24 MiB | 24,000,000 | 256 |
| Local API PNG import | 18 MiB | 32,000,000 | 64 |

The local workbench accepts at most 36 MiB of combined PNG bytes before base64 encoding. The API also enforces a 50 MiB total JSON request bound. These are rejection limits, not automatic image resizing. The interface displays the limits for its current mode.

If connected regions become excessive, analysis switches to explicit 512 px review tiles with contextual overlap in model crops. At most 256 candidates are accepted, with an explicit partition request instead of silently dropping the remainder. Masks require a source, are visible in reports, and exclude the same pixels in differences and all model crops. Raw PNGs remain available. The difference viewer uses the shared decoder and raw-difference function in a separate Worker; gray/hatching marks excluded masks and magenta distinguishes height-only areas.

## Review priority

A priority is a triage aid, not defect probability. The workbench lets a reviewer set each observation's severity weight to Low (0.5), Normal (1), or High (2). All weights start at 1. Candidates are sorted by:

```text
priority = max(observation score × severity weight)
           + 0.05 × min(1, changed pixels / comparison canvas pixels)
```

An exact tie is resolved by changed-pixel count. Calibrated classes use the released calibrated score; uncalibrated classes use sigmoid(logit) for sorting while the evidence panel displays the raw logit and its uncalibrated status. The observation filter includes a region when the selected class's logit is at least zero. A region whose logits are all below zero remains visible as an unclassified visual change. Neither this filter nor the sorting score is a defect threshold.

Priority preferences are saved for each project in the current browser and included in workbench-generated exported snapshots. Changing them does not change original predictions, observation labels, review decisions or the gate. Contract violations and incomplete required contracts remain independent blockers and are presented separately. Every unreviewed candidate remains in the gate even at a low score. Five observation outputs may co-occur. Unknown labels are masked during training. DOM geometry cannot establish user intent, reliable clickability or arbitrary true occlusion.

PNG decoding uses the same `fast-png` path in Node and the browser. Encoded RGB samples are treated as sRGB channel values; embedded ICC and gamma profiles do not trigger separate color-management transforms. Palette transparency, gray/gray-alpha, RGB/RGBA and supported 16-bit inputs are converted by the documented shared decoder. Interlaced images are explicitly rejected. The golden suite verifies independent reference decoding and browser/Node equality.
