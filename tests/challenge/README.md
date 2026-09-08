# Handwritten challenge

Twelve literal HTML/CSS scene pairs use fixtures separate from the training generator. Their frozen expectations and inspection notes are in `manifest.json`. The saved evaluation belongs to the historical viewport-only model.

Capture with `node --import tsx scripts/challenge.ts`, then evaluate explicitly with `python tests/challenge/evaluate.py --captures artifacts/challenge --model web/public/models`. Capture verifies fixture hashes and writes PNGs, candidates, tensors and a contact sheet.

Labels are page-level observations; null is unknown. Intentional relocation still has a positive displacement label. Missing selectors are inconclusive, and the changed-width pair is incomparable and excluded from visual metrics.

The evaluator refuses to overwrite a result. `--development-rerun` allows a marked development run. The original cutoff is 0.5; `python tests/challenge/published_thresholds.py` reads saved scores with the release thresholds without rerunning inference. Those thresholds were selected on candidate scores, while this small challenge uses page-max scores.
