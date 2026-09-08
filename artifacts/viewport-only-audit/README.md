# Superseded viewport-only diagnostic

These numerical records describe the first fixed-viewport corpus. A rendering check found that Playwright clipped screenshot height to the viewport when `clip` was supplied without `fullPage`. They are retained as evidence of the limitation and are not the release-model results. The corrected full-height corpus and unchanged training recipe were rerun. The original held-out results had already been read when this preprocessing correction was made, so subsequent evaluation is a rerun, not a new blind test.
