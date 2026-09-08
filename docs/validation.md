# Validation evidence and limits

The local processing and review workflow passed the checks below with the corrected trained release model. A fresh final holdout demonstrates useful overlap and displacement recognition across three new structures, while clipping and container-boundary recognition still fail substantially. The earlier exposed challenge is retained as historical evidence. Successful capture, valid evidence, and preserved review state do not mean the model recognizes every visible problem. This release is a research review assistant, and unreviewed changes remain blocking regardless of their model scores.

These are development and release self-checks. Independent external acceptance has not been performed.

## Tested environment

The recorded local checks ran on macOS 26.5.2, arm64, Node.js 24.19.0, Python 3.12.14, PyTorch 2.8.0, and Playwright 1.55.0 Chromium 140.0.7339.16. Model inference in the API checks used ONNX Runtime CPU. This record does not claim complete local application testing on Windows or Linux. Remote CI and deployed browser checks have their own release evidence and do not establish those platform claims.

The model under test is `0.1.0-rc.1`, ONNX SHA-256 `63c196fbe44b338082465cbff353f00a4e085e0fd0cdaa5a324782224d62cc3f`, preprocessing version `rgba-diff-rle-letterbox-v1`. Full training, three-seed comparisons, calibration, and PyTorch/ONNX numerical measurements are described in [the model documentation](model.md) and retained experiment artifacts.

## Shared image and capture checks

The following command passed all 20 tests together in 4.5 seconds, including the full-document capture regression:

```sh
node --import tsx --test tests/core*.test.ts
```

Separated translated regions can also receive an explicitly heuristic image-similarity association. Its regression verifies that candidate boxes, statistics, and tensor inputs are unchanged and that a differently colored unrelated region is not linked. These links do not establish movement direction or causality.

The tests cover exact repeated images; a one-level one-pixel change; eight-connected components and multiscale merging; preservation of changed-pixel counts; declared mask provenance and masked tensor consistency; unequal-height valid regions including blank new tails; tiled long pages, seams, tails, and candidate uniqueness; explicit resource rejection; alpha compositing; deterministic bilinear letterboxing; and PNG corruption rejection.

A dedicated regression in `tests/core.fullpage.test.ts` reproduces the historical generator defect: a document-height clip without `fullPage` yields a 600-pixel image, while `fullPage: true` with the same clip preserves the actual scroll height and the colored footer pixels. That before/fixed regression passed in real Chromium.

Real Chromium tests cover DPR 2 with CSS-scale screenshots, long-page capture, measured CSS-coordinate contracts, equivalent pixels and tensors when only contracts change, repeated-capture stability, declared dynamic masks, blocked external redirects and subresources, and visibility after ancestor overflow clipping. Nonrectangular CSS masks or clip paths return inconclusive for required visibility. Axis-aligned contract checks do not prove actual occlusion or clickability.

A separate real browser golden check compares shared decoding against an independent PNG decoder for nine inputs: grayscale, grayscale-alpha, RGB, and RGBA at 8 and 16 bits, plus a 2-bit indexed palette with transparency. Decoded pixels match exactly. Browser and Node candidate metadata, all four image tensor branches, and geometry match exactly. The canonical decoder avoids Canvas premultiplication and color-conversion round trips. These exact preprocessing results are distinct from the floating-point tolerances used for model output parity.

## Real application integration

The combined Python state, learning, full-page rendering, real API integration, and feedback-update suite passed 15 tests with the corrected model. The feedback integration performs actual head training, evaluates against retained development examples, verifies explicit activation and rollback, and confirms that old evidence and review decisions remain unchanged.

The production browser and local-UI suite passed six tests without skipped cases. It covers real PNG upload and ONNX/WASM inference, exact difference pixels, multiple-region priority sorting, a stable 1,507-pixel page, cancellation during model download, review and undo, baseline history, refresh, and standalone HTML exports. `artifacts/browser-parity.json` records a maximum browser/reference logit error of 0.00001431, score error of 0.000000306, zero published-threshold differences, and exact decoded pixels, candidates, and tensors. The original 0.0001 browser tolerance remains unchanged.

The following command passed both integration tests with the trained release model in 9.6 seconds on the final targeted rerun with the corrected model:

```sh
python -m pytest tests/test_e2e.py -q
```

The first test performs actual Chromium capture, the official TypeScript candidate and tensor pipeline, real ONNX inference, and explicit required-visible, inside-container, and non-overlap checks. Changing only the constraints leaves input hashes, candidate evidence, and model logits unchanged while the contract result changes. Intentional-change decisions retain the original observation predictions; undo restores the review state. Corrected observation labels are exported separately as feedback, baseline changes preserve history, and a recreated service reopens the same project with its saved decisions and model evidence.

The exported HTML is opened by a real browser directly from a local file. Both embedded evidence images are present and the page makes zero HTTP requests. The report remains a snapshot rather than a live project editor.

The second test verifies that unchanged images with a missing declared selector have an inconclusive contract and gate code 3; differing capture widths retain incomparable execution; cancellation propagates to cancelled evidence with gate code 3; and corrupted PNG input produces an error rather than a no-change result. No model scores are mocked in these integration tests.

The three original local scenarios were also reproduced through `python examples/reproduce.py`: main analysis completed with three candidates and gate 2; intentional relocation completed with one explicitly accepted candidate and gate 0; unchanged images with a missing declared selector completed with zero candidates and gate 3. The raw and reviewed reports, original screenshots, capture configuration, hashes, and baseline history are retained in `examples/main`, `examples/intentional`, and `examples/failure`. This checks that successful analysis execution and gate permission remain separate facts.

## Earlier exposed handwritten challenge

The earlier model, SHA-256 `dcedb2b5413d71f4cae4a89b7ebb0ffc0d5df41c23be2698e535f9ba8f50d4e9`, was checked with twelve literal HTML/CSS scene pairs authored independently of the main scene mutation functions. They were rendered and visually inspected internally before final model evaluation. Fixture hashes, unknown labels, inspection reasons, and expected execution/contract states are retained in `tests/challenge/`. This is an internal visual audit, not a human annotation study or an independent acceptance result.

The frozen annotation manifest SHA-256 is `b7a8381522d2ea1f7ef1ee52550f703cdf025677ea04bff6470faccfce38cbe6`. That earlier model was evaluated once after its initial development selection. A subsequent audit found that the training generator used a document clip without `fullPage: true`, which truncated long-page screenshots to the viewport. The capture defect was corrected and the same training configuration was rerun. Because these challenge outcomes had already been inspected, this old set is now exposed historical evidence rather than the final holdout for the corrected model. The original fixed-0.5 result remains unchanged in `artifacts/challenge/first-frozen-run/model-evaluation.json` and its original location; its SHA-256 is `724a03498fd03c7b749e070fee2cf732874e76207a7159e98a9566b6ed8eb3a6`.

All 12 expected execution states and all 12 sets of expected explicit-contract states matched. The changed-width example is incomparable and excluded from visual metrics. The missing-selector examples remain inconclusive. Normal repetition and the declared dynamic-mask example produce zero candidates. These are state and contract successes, separate from the observation failures below.

Observation metrics use the maximum calibrated candidate score per page. Zero candidates produce a zero page score, so a missed candidate on a positive page would remain a miss. Unknown observations are excluded. The initial readout uses a prespecified score cutoff of 0.5. A secondary readout applies the already-published development-selected thresholds to the saved scores; it performs no new inference and changes neither model nor labels. Its source hash and method are recorded in `artifacts/challenge/published-thresholds.json`.

| Observation | Known / positive pages | F1 at fixed 0.5 | Published threshold | F1 at published threshold | Recall at published threshold |
| --- | ---: | ---: | ---: | ---: | ---: |
| Clipping | 11 / 2 | 0.000 | 0.30 | 0.000 | 0 / 2 |
| Overlap or occlusion | 11 / 1 | 0.000 | 0.25 | 0.000 | 0 / 1 |
| Out of container | 9 / 1 | 0.000 | 0.25 | 0.500 | 1 / 1 |
| Element disappearance | 11 / 2 | 0.800 | 0.35 | 0.800 | 2 / 2 |
| Layout displacement | 11 / 3 | 0.667 | 0.35 | 0.571 | 2 / 3 |

The clipping examples and the visible text-occlusion example are missed at both cutoffs. A normal temperature/color update receives high out-of-container and displacement scores (0.883 and 0.988). A deliberate card relocation receives only 0.165 displacement score and is missed. The displaced overlay is also incorrectly scored as element disappearance. These failures show poor transfer for several signs despite the separate synthetic-family experiment results. They remain preserved. The subsequent training rerun corrected the independently reproduced capture defect; this old set is no longer claimed to be untouched after that correction.

With only one to three positive pages per sign, these figures are descriptive and unstable. The published thresholds were selected for candidate scores on development data; applying them to a page maximum also changes the aggregation domain. Neither readout estimates production defect probabilities, validates arbitrary unseen websites, or demonstrates saved human review time.

Reproduction commands are:

```sh
node --import tsx scripts/challenge.ts artifacts/challenge
python tests/challenge/evaluate.py --captures artifacts/challenge --model web/public/models
python tests/challenge/published_thresholds.py
```

The evaluator refuses to overwrite a prior model evaluation. An explicit `--development-rerun` marks a rerun as development use, so it cannot retain a withheld claim. Existing challenge evidence should be retained when reproducing captures on another platform because font rasterization and browser versions can change screenshot hashes.

## Fresh final holdout after the capture correction

A new untouched set was authored after the capture defect was identified: nested file inspector, expanded questions, and appointment swimlane. These are three new literal HTML/CSS structures independent of the main training generator. Each family has 18 rendered pairs. Six exact screenshot-pair replicates are retained as stability evidence and excluded from metrics, leaving 48 unique image pairs, 16 per family. Full-page image heights are 1,090, 1,507, and 1,245 pixels, all exceeding the 760-pixel viewport.

The before/after labels were independently verified from rendered text clipping extent, sampled foreground hit testing, outlined-container geometry, target presence and movement, and real pixel difference. Edit names are provenance rather than label assignment. All 54 pairs were visually inspected in family contact sheets, with additional full-resolution checks. Invisible targets leave clipping, occlusion, and containment unknown. Pre-existing clipping is not labeled as a new observation when it remains unchanged. Intentional movement retains the displacement label.

The sources, labels, capture configuration, and screenshot hashes were frozen before the corrected model was evaluated. The frozen manifest SHA-256 is `a65fbf67de34660c4815639cda67ab8d3eed57dc6c4f605830657f7ab417e532`. The corrected model was evaluated exactly once after the explicit final SHA freeze, and no model, threshold, or label was updated from these results. Both fixed-0.5 and already-published development-selected thresholds were specified before this evaluation. The model training source is `fb3136c62f0d902835ac12b5292e043dcaf7fc83`.

| Observation | Known / positive unique pages | Published threshold | Precision | Recall | F1 | Average precision | Positive prevalence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Clipping | 45 / 9 | 0.30 | N/A | 0 / 9 | 0.000 | 0.137 | 0.200 |
| Overlap or occlusion | 45 / 9 | 0.55 | 0.889 | 8 / 9 | 0.889 | 0.989 | 0.200 |
| Out of container | 45 / 6 | 0.20 | 0.063 | 1 / 6 | 0.091 | 0.149 | 0.133 |
| Element disappearance | 48 / 3 | 0.55 | 0.333 | 2 / 3 | 0.444 | 0.333 | 0.063 |
| Layout displacement | 48 / 18 | 0.40 | 0.684 | 13 / 18 | 0.703 | 0.889 | 0.375 |

At fixed 0.5, the corresponding F1 values are 0.000, 0.900, 0.000, 0.500, and 0.686. These differences are reported without choosing a threshold on the holdout. Average precision is a descriptive ranking metric with ties grouped together; positive prevalence is shown as a simple uninformative-ranking reference.

All positive pages have at least one official candidate, with 1.0625 candidates per unique page on average. This page-level candidate coverage does not establish accurate lesion boundaries. Model recognition remains the limiting stage for several signs: all nine clipping examples are missed, and clipping average precision is below its 0.20 prevalence reference. Container-boundary recognition has only one true positive and 15 false positives. For example, the control moves safely within the appointment lane but receives a 0.929 out-of-container score; the visibly escaped inspector control receives only 0.043. Ordinary timestamp content updates receive false displacement scores around 0.47–0.52. These failures remain in the released machine-readable results.

Overlap and displacement show transfer across these new structures, but that does not support a claim of uniform five-class reliability. With only three source families and three unique disappearance positives, estimates are unstable. These are authored scenes sharing some typography and control styling, not independent production websites. Page-max scores differ from the candidate-level calibration domain and remain observation scores rather than defect probabilities.

A second capture-only reproduction run matched all 54 original screenshot pairs exactly on the recorded platform. It did not run inference or change labels. Compact results and reproduction evidence are retained as `artifacts/final-holdout-results.json` and `artifacts/final-holdout-reproduction.json`. The original screenshots, full capture manifests, raw official tensors, source fixtures, and contact sheets are packaged in the separate Release asset `renderguard-final-holdout-v1.tar.gz`, SHA-256 `ad143d3a7535967d5adf74eec33b2c539b8cdb9ec335cfe644334419e4644ccb` (17,879,171 bytes). Asset metadata is in `artifacts/final-holdout-archive.json`.

```sh
node --import tsx scripts/reproduce-final-holdout.ts workspace/holdout-recapture
python tests/final-holdout/evaluate.py --expected-model-sha 63c196fbe44b338082465cbff353f00a4e085e0fd0cdaa5a324782224d62cc3f
```

The evaluator verifies the pinned source, labels, images, model, and calibration, and refuses to overwrite the one-time result. These are final development self-checks, not independent external acceptance.

## Remaining scope

This document establishes the recorded local checks and challenge outcomes only. Clean-checkout installation, remote CI jobs, live Pages upload/inference, final browser score/rank parity, release retrieval, and final commit/deployment correspondence must be read from their actual release records. An unexecuted or blocked check is not implied by a local test passing. The exposed historical challenge and the fresh final holdout both remain internal evidence; the next independent acceptance stage is still required.
