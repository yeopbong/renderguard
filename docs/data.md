# Scene data

The corpus contains 1,728 original synthetic screenshot pairs from 24 authored layout families, including tables, profiles, boards, checkout, dialogs and maps. These are synthetic layouts rather than production incidents. Fixture code uses the repository license; authored content and generated PNGs are CC0-1.0.

[`artifacts/groups.json`](../artifacts/groups.json) fixes the source split: 14 families for training, four for development, three for calibration and three for test. Theme, viewport, text, target-position and operation variants remain within their family. Families share low-level CSS primitives. Exact duplicate images remain within one split.

Chromium captures use DPR 1, CSS screenshot scale, widths of 390 or 900 CSS pixels, and the full measured scroll height. Horizontal content outside the viewport is excluded. Fonts are awaited, locale/timezone are fixed, and page data are authored constants. Separately authored Japanese/Chinese probes cover only their specified scene variants.

## Labels and candidates

`ml/scenes.mjs` records requested changes. `ml/verify.mjs` derives labels from rendered geometry and pixel evidence: clipping, border crossing, visibility, displacement and sampled opaque occlusion. It does not use operation names. Null labels are unknown and masked in the training loss. Intentional movement retains a displacement label; missing feedback supplies no label.

Grid sampling can miss small occlusion, rectangles approximate text/shapes, and visibility does not establish clickability. Labels describe visible observations. The retained sample inspections are internal checks, not external annotations.

The application candidate generator supplies every training and evaluation candidate. Ground-truth regions are matched afterward: at least 10% of either the region or candidate must intersect. This associates evidence rather than measuring tight localization. [`artifacts/candidate-evaluation.json`](../artifacts/candidate-evaluation.json) records coverage, tightness, missed regions and zero-candidate pages.

Manifests retain source/split, configuration, image and HTML hashes, observed geometry and capture conditions. Tests check source grouping and exact-image leakage.

## Regenerate

```sh
node ml/generate.mjs
python -m ml.prepare
python -m ml.publish_examples
```

Large caches live in the ignored `data/` directory. Published PNG examples, manifests, groups and generator source remain in the repository. The [handwritten challenge](../tests/challenge/README.md) and [final holdout](../tests/final-holdout/README.md) use separate fixtures; original results are linked from [experiments](experiments.md).
