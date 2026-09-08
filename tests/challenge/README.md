# Handwritten final challenge

These 12 scene pairs use independent literal HTML and CSS rather than the training generator or its mutation functions. Their fixture hashes and observation expectations were frozen before final model evaluation. The rendered pairs were visually inspected internally; the inspection reasons are in `manifest.json`. This is not independent external acceptance or a human annotation study.

Capture with `node --import tsx scripts/challenge.ts`. This verifies fixture hashes, saves original PNGs and capture manifests, runs the official candidate/tensor pipeline, and creates a contact sheet. Capture does not evaluate a model. Run the explicit evaluation command only after model selection is final: `python tests/challenge/evaluate.py --captures artifacts/challenge --model web/public/models`.

Observation labels are page-level expectations used only for final page-level scoring. They are never copied to all candidates or supplied to model inference. Null labels are unknown and excluded. The deliberate relocation has a positive displacement observation and a negative defect conclusion. Missing selectors remain inconclusive. The changed-width pair is incomparable and excluded from visual metrics while still checked for execution semantics.

The evaluator refuses to overwrite an earlier model evaluation. A deliberate rerun requires `--development-rerun` and is marked as development use, invalidating its withheld status. Because each scene contributes only one pair, statistical estimates from this small challenge are descriptive.

The original evaluation uses a prespecified 0.5 cutoff. `python tests/challenge/published_thresholds.py` provides a secondary descriptive readout using the existing release manifest thresholds and saved scores, without rerunning inference or changing the primary artifact. Published thresholds were selected on development candidate scores; page-max aggregation is a separate domain.
