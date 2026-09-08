# Experiments and limits

The visual encoder learns useful observation signals on the authored corpus. In the untouched final structural holdout, the corrected release model missed every clipping-positive page and produced many boundary-crossing false positives; occlusion and displacement transferred better. These results support a research review assistant with explicit human review, not automatic release approval or general production defect detection. The earlier handwritten challenge evaluated the superseded viewport-only model and remains historical evidence; its overlap failures are not the final-holdout results of the corrected model.

A deterministic screenshot correction was made after the first held-family results had been read: Playwright requires `fullPage: true` with the fixed-width clip to retain the complete scroll height. The unchanged family splits, model architecture, optimization recipe, and seed-selection rule were rerun on corrected screenshots. The earlier numbers remain in `artifacts/viewport-only-audit/`. The original 24-family evaluation is therefore a corrected held-family rerun, not an untouched blind test. The separately authored final holdout is evaluated only once after the corrected model is frozen; its report is kept with the validation artifacts.


## Untouched final structural holdout

The corrected model was evaluated once on 54 newly authored pairs (48 unique image pairs) from 3 structurally independent fixture sources. The release thresholds were frozen before predictions. This is an internal withheld evaluation, not the next independent acceptance stage. No model, threshold, or label was changed using these results.

| Observation | Known pages | Positive pages | F1 | Average precision | Missed positives |
|---|---:|---:|---:|---:|---:|
| clipping | 45 | 9 | 0.000 | 0.137 | 9 |
| overlap_or_occlusion | 45 | 9 | 0.889 | 0.989 | 1 |
| out_of_container | 45 | 6 | 0.091 | 0.149 | 5 |
| element_disappearance | 48 | 3 | 0.444 | 0.333 | 1 |
| layout_displacement | 48 | 18 | 0.703 | 0.889 | 5 |

Clipping missed every positive page, and boundary crossing produced many false positives. Occlusion and displacement show transferable signals in these limited scenes. The sample is too small for a broad deployment claim, and the class failures are material. See `artifacts/final-holdout-results.json` for every score, per-family results, and both preregistered threshold policies.

## Fixed protocol

The corpus has 1,728 real Chromium PNG pairs in 24 source families: 1008 training, 288 development, 216 calibration, and 216 test. The formal TypeScript candidate generator supplies all candidate rows. No ground-truth crop or DOM result is passed to the neural model. Labels are independently measured rendered observations, with unknown supervision masked. See [Data and supervision](data.md).

The release model uses seed 29, selected by development macro PR-AUC 0.9562. Its real source commit is `fb3136c62f0d902835ac12b5292e043dcaf7fc83`. Models have two head warmup epochs and four later encoder fine-tuning epochs. AdamW is initialized afresh each epoch, as recorded in `artifacts/training-config.json`; BatchNorm statistics remain frozen. The primary comparisons use fixed seeds 17, 29, and 43, with identical source splits and candidate labels.

## Candidate classification

| Method | Held-family macro PR-AUC | Repeats |
|---|---:|---:|
| Uninformed training prior | 0.1618 | Deterministic |
| Pixel difference density | 0.2672 | Deterministic |
| Difference statistics + logistic classifier | 0.4842 | Deterministic |
| Frozen generic visual features | 0.8725 ± 0.0094 SD | 3 seeds |
| Fine-tuned local crops | 0.9284 ± 0.0191 SD | 3 seeds |
| Fine-tuned local + context | 0.9209 ± 0.0124 SD | 3 seeds |

![Comparison from saved metrics](figures/comparison.png)

The visual configurations outperform the difference-statistics baseline on these families. Local-only has a slightly higher mean than local + context in the corrected run, and the difference is small relative to between-seed variation. Context did not establish a consistent gain; the release retains the prespecified local + context architecture without claiming it won the ablation. Individual seeds and all losses remain in `artifacts/experiments.json`; a favorable test seed does not determine the released weights.

| Observation | Known candidates | Positive | Precision | Recall | F1 | PR-AUC |
|---|---:|---:|---:|---:|---:|---:|
| clipping | 293 | 36 | 0.857 | 0.667 | 0.750 | 0.915 |
| overlap_or_occlusion | 293 | 36 | 0.897 | 0.972 | 0.933 | 0.992 |
| out_of_container | 293 | 63 | 0.434 | 1.000 | 0.606 | 0.878 |
| element_disappearance | 293 | 18 | 1.000 | 0.889 | 0.941 | 0.910 |
| layout_displacement | 293 | 84 | 0.821 | 0.929 | 0.872 | 0.929 |

The selected model's macro PR-AUC is 0.9248; its 500-resample source-family percentile interval is [0.9073, 0.9704]. Only three test source families contribute, making this interval unstable and conditional on the authored scenes.

![Saved development curves](figures/training-curves.png)

## Candidate coverage and complete-system recall

There are 147 positive observation regions across 216 held-family pairs. Candidate recall is 1.000 at 10% ground-truth coverage and 0.796 at 50% coverage: respectively 0 and 30 regions are missed. Mean maximum coverage is 0.809, while mean maximum tightness is 0.735. The average candidate count is 1.356 per pair, p95 6.0, maximum 7; 58 pairs have no candidate.

These boxes are the union of before/after element extents, not pixel-exact defect annotations. A permissive 10% match can retain evidence without tightly localizing it. Large boxes are not awarded a high localization score merely for covering the whole page.

| Observation | All positive regions | Captured | Missed | Complete-system recall |
|---|---:|---:|---:|---:|
| clipping | 36 | 24 | 12 | 0.667 |
| overlap_or_occlusion | 36 | 35 | 1 | 0.972 |
| out_of_container | 54 | 54 | 0 | 1.000 |
| element_disappearance | 18 | 16 | 2 | 0.889 |
| layout_displacement | 75 | 69 | 6 | 0.920 |

## Review budgets

Rank page pairs by their maximum candidate observation score. Budgets count whole page pairs, including candidate-free inputs in the denominator. These are **observation-bearing pages**, not independently confirmed defects.

| Method | Top 10% capture | Top 25% capture | Top 50% capture |
|---|---:|---:|---:|
| local_context | 22/129 (0.171) | 54/129 (0.419) | 108/129 (0.837) |
| difference_statistics | 20/129 (0.155) | 46/129 (0.357) | 92/129 (0.713) |
| pixel_difference | 22/129 (0.171) | 45/129 (0.349) | 91/129 (0.705) |
| frozen | 22/129 (0.171) | 54/129 (0.419) | 108/129 (0.837) |
| local_only | 22/129 (0.171) | 54/129 (0.419) | 108/129 (0.837) |

DOM contracts are checked on the separate structurally supplied challenge and integration fixtures. Their measurements are not ranked against PNG-only visual classification, and rectangle rules are not called usability or causal explanations.

## Calibration

Calibration uses three separate families. A class needs at least 15 known positives and 15 known negatives; other outputs stay uncalibrated. The calibration target is observation frequency on these synthetic candidates.

| Observation | Calibration n | Positive / negative | Status | Held-family Brier | Held-family ECE |
|---|---:|---:|---|---:|---:|
| clipping | 230 | 35 / 195 | calibrated | 0.0424 | 0.0532 |
| overlap_or_occlusion | 216 | 34 / 182 | calibrated | 0.0147 | 0.0460 |
| out_of_container | 230 | 69 / 161 | calibrated | 0.0826 | 0.1307 |
| element_disappearance | 230 | 24 / 206 | calibrated | 0.0095 | 0.0101 |
| layout_displacement | 230 | 93 / 137 | calibrated | 0.0787 | 0.1421 |

![Reliability bins with real sample counts](figures/reliability.png)

Reliability is measured on the candidate population and says nothing about changes missed by candidate generation. A ten-bin ECE with few families is not a general reliability guarantee. Full bin counts are preserved in `artifacts/model-results.json`.

## Domain and type exclusions

These secondary probes use one fixed seed, 107. They are exploratory checks and never choose the release model. The domain probe trains and selects epochs only on light English variants 0 and 2. Dark English uses held families at variants 1 and 3. Japanese and Chinese text is separately authored and rendered on the held source structures; Chinese also changes the theme, so that result confounds script and theme.

| Probe domain | Macro PR-AUC | Macro F1 |
|---|---:|---:|
| light_english | 0.9053 | 0.8132 |
| dark_english | 0.5175 | 0.4165 |
| ja | 0.8245 | 0.7684 |
| zh | 0.6074 | 0.5580 |

The symptom-exclusion configuration removes 146 overlap-positive training page pairs before training. The excluded class has PR-AUC 0.1250, recall 0.000, and F1 0.000. Its score is uncalibrated and has no positive task supervision. This failure is retained; the system does not claim reliable recognition of unseen observation types.

## Offline label replay

The replay pool contains 702 candidate-bearing training page pairs. Each strategy begins with the same 12 labeled pages per seed and uses budgets 12, 24, 48, and 96. A selected page reveals all of its existing observation labels; candidate review counts are recorded separately. Selection sees generic pretrained features and current predictions, while the oracle reveals labels only for selected pages. All strategies use the same frozen generic encoder, fixed random projection, logistic heads, seeds, and update schedule. Candidate-free pages are outside this explicitly bounded labeling pool.

Calibration-label cost is 0; selection uses uncalibrated scores. The separate development-label cost is 198 candidate-bearing page pairs. This cost is not included in the changing pool budget. The experiment does not measure human time savings.

| Strategy | 12 pages | 24 pages | 48 pages | 96 pages |
|---|---:|---:|---:|---:|
| random | 0.3172 | 0.3661 | 0.4879 | 0.5730 |
| uncertainty | 0.3172 | 0.3723 | 0.4073 | 0.5147 |
| uncertainty_diversity | 0.3172 | 0.3934 | 0.4360 | 0.5432 |

![Offline replay results](figures/replay.png)

No strategy is declared uniformly best from this small simulation. The files retain selected page IDs and revealed candidate counts at every step.

## Runtime and numerical parity

Measured on macOS-26.5.2-arm64-arm-64bit with MPS training and CPU ONNX inference: full scene generation took 139.87 s and all nine primary neural comparisons plus associated evaluation took 102.70 s. The ONNX file is 6,184,503 bytes. Its measured cold load was 27.64 ms, first inference 7.05 ms, warm median 6.49 ms and p95 6.78 ms over 40 trials at batch 1. Each input has four 96 × 96 RGB crops plus 12 geometry values.

On 24 real candidate inputs, maximum deployment-fused PyTorch/ONNX logit error was 6.4e-05, score error 6.9e-06, with 0 threshold disagreements and ranking agreement True. The tolerance remains 1e-4. The raw, unfused float32 PyTorch comparison separately exceeded that initial logit budget (about 1.23e-4); its calibrated score difference stayed below 7.1e-6 with zero threshold differences. This failure is retained in `artifacts/numerical-batch-diagnostic.json`. The ONNX graph contains no BatchNorm nodes, and standard PyTorch Conv/BN fusion independently agrees with its exported convolution weights within float32 rounding: maximum absolute difference 7.63e-06, maximum relative difference 2.29e-07, and maximum distance 2 float32 ULPs (per-layer values and weight magnitudes are retained in the diagnostic). The deployed graph is not claimed to be bitwise identical to the unfused checkpoint arithmetic. This is a deployment-equivalence check, not a claim that raw float32 arithmetic is identical. Browser tests separately compare the exact decoded pixels, candidate boxes, tensors, graph output and final ranking.

The costs of original image generation and shared preprocessing are not hidden behind cached embeddings. `artifacts/preprocessing-timing.json` separates PNG decode, candidate generation, and tensor construction. `artifacts/end-to-end-timing.json` measures fresh Node process startup, disk transfer, and actual CPU inference from example PNGs. URL capture and UI rendering are separate operations. Peak process memory and cold/warm distinctions remain in the raw records.

## Reproduction

```sh
node ml/generate.mjs
python -m ml.prepare
python -m ml.train --device mps --epochs 6
python -m ml.replay --device mps
node --import tsx ml/stress-generate.mjs
python -m ml.stress --device mps
python -m ml.numerical
python -m ml.evaluate
node --import tsx ml/benchmark.mjs
python -m ml.benchmark
python -m ml.feedback --build-buffer
python -m ml.figures
python -m ml.report
```

Use `--device cpu` where MPS is unavailable. Browser dependencies must be installed first. Raw structured training curves, seed-level metrics, calibration bins, candidate records, challenge failures, source hashes, and replay selections are public artifacts; model and data hashes are in the manifest. The next independent acceptance review is separate from these development checks.
