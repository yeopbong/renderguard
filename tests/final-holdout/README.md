# Final structural holdout

Three separately authored structures—nested file inspector, expanded questions and appointment swimlane—each have 18 rendered pairs. Six exact pair replicates remain in the files but are excluded from metrics, leaving 48 unique pairs. This set followed the earlier handwritten challenge and the full-page capture correction; its sources, labels and evaluation policy were frozen before evaluating the corrected model.

Rendered clipping, sampled foreground hits, outlined-container geometry, presence, movement and changed pixels determine observation labels. Unknown labels are excluded; intentional movement retains its displacement label. Contact sheets and inspection notes are internal checks. Keep this set separate from training, calibration and model selection.

`scripts/final-holdout.ts` captures the fixtures and writes labels, candidates, tensors and contact sheets without loading a model. It refuses to overwrite a frozen set; `freeze.json` pins the annotation manifest and source files.

Evaluate a frozen model with:

```sh
python tests/final-holdout/evaluate.py --expected-model-sha FINAL_MODEL_SHA256
```

The evaluator checks model, source and image hashes and refuses to overwrite an existing result. Metrics use both fixed 0.5 and published development thresholds. Page scores take the maximum over all generated candidates; candidate-free pages remain in the denominator. The thresholds were chosen for candidate-level scores, and this set has only three families.

To reproduce captures in a separate directory:

```sh
node --import tsx scripts/reproduce-final-holdout.ts workspace/holdout-recapture
```

This preserves original labels/captures and records whether new screenshot hashes match. Browser and font differences may change pixels. The raw archive `renderguard-final-holdout-v1.tar.gz` contains original PNGs, tensors, saved results and source; its size/hash are in [`artifacts/final-holdout-archive.json`](../../artifacts/final-holdout-archive.json).
