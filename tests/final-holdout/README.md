# New-family final holdout

This set contains three original structures—nested file inspector, expanded questions, and appointment swimlane—authored independently of the training generator. Each family has 18 rendered pairs. Six exact screenshot-pair replicates are retained as stability evidence and excluded from metric denominators, leaving 48 unique image pairs across three families.

This set was created after the earlier handwritten challenge had been inspected and a separate long-page training-capture defect was corrected. The earlier challenge remains exposed historical evidence. These new family sources, capture configuration, rendered labels, screenshot hashes, and evaluation policy were frozen before the corrected model was evaluated. The new set must not be used for training, calibration, seed selection, or further model changes while claiming final held-out results.

Labels are verified from rendered text clipping extent, sampled foreground hit testing, visible outlined-container geometry, target presence, movement, and actual pixel differences. The verifier does not consult an edit name to assign the five labels. Operation names are kept only as provenance. Invisible targets leave clipping, occlusion, and containment unknown. Intentional movements retain positive displacement labels. Some baseline text is already slightly clipped; an unchanged pre-existing sign is not a new positive.

All 54 before/after pairs were inspected in the retained family contact sheets. Additional full-resolution checks covered FAQ clipping, swimlane occlusion, and inspector boundary escape. This is an internal visual audit, not external human annotation or independent acceptance. Low-level typography, control styling, and capture utilities are shared within the holdout and are recorded rather than represented as independent real websites.

`scripts/final-holdout.ts` creates the original pages, captures them through the product capture path, independently measures labels, writes official candidates/tensors, and produces contact sheets without loading a model. It refuses to overwrite a frozen set. `freeze.json` pins the rendered annotation manifest and source files. To independently reproduce captures on another platform, use a separate checkout/output directory and preserve the original recorded screenshots; font and browser differences can change pixels.

After the final corrected model SHA is explicitly frozen, run the evaluator exactly once:

```sh
python tests/final-holdout/evaluate.py --expected-model-sha FINAL_MODEL_SHA256
```

The evaluator requires that exact model hash, verifies source and image hashes, and refuses to overwrite an existing result. Both fixed 0.5 and already-published development-selected calibrated thresholds are specified before inference. Page-level scores take the maximum over all official candidates, including misses as zero-candidate pages; no ground-truth box selects model inputs. Thresholds were originally chosen for candidate-level development scores, so page-max metrics are descriptive. With only three structure families, uncertainty remains substantial regardless of the number of variants.

To re-capture the already frozen HTML without editing any source labels, use a separate output directory:

```sh
node --import tsx scripts/reproduce-final-holdout.ts workspace/holdout-recapture
```

This verifies the frozen manifest and HTML hashes, reuses the original capture configuration, writes new official tensors, and records whether each screenshot hash matches the original. It never reads model predictions, changes labels, or overwrites the original holdout captures. It is a reproduction utility rather than a second final evaluation.

The published raw-evidence asset is `renderguard-final-holdout-v1.tar.gz`; its expected size and SHA-256 are recorded in `artifacts/final-holdout-archive.json`. It contains `final-holdout/captures/` with the original PNGs, tensors, and saved result, plus a source snapshot. Extract it for inspection after checking the recorded hash. A fresh capture reproduction goes to a separate output directory and has no evaluation file; use `--captures` to point an independent numerical reproduction at that directory while preserving the published original result.
