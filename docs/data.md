# Data and supervision

The release uses original, re-renderable synthetic pages. It does not contain reproduced production incidents or establish production defect-detection accuracy. Fixture code is under the repository code license; authored content and generated scene images are CC0-1.0. The ImageNet source used by the generic upstream initialization is separate and is not redistributed as part of the scene corpus.

`artifacts/groups.json` fixes 24 source families before rendering their variants. Fourteen families belong to training, four to development, three to calibration, and three to test. A family includes every theme, viewport, text, target-position, and operation variant. Low-level CSS primitives are shared and disclosed. Different families are different authored layouts and target structures; they are not independent real websites.

The 1,728 screenshot pairs cover tables, profiles, timetables, boards, invoices, mail, catalogs, settings, articles, checkout, galleries, dashboards, forums, timelines, navigation, dialogs, pricing, directories, media controls, calendars, search, multistep forms, code, and maps. Observed targets differ by family: a subtotal grid, serif biography, appointment, task card, payment total, signature, product figure, input-like field, paragraph, address, artwork, bar chart, reply, milestone, navigation links, dialog action, price list, contact, playback controls, calendar entry, search result, radio group, source block, and map legend. Each has two tracked instances. Target choice, severity, theme, and viewport vary within its family.

Generation uses actual Chromium screenshots at DPR 1 and CSS screenshot scale. Width stays at the configured 390 or 900 CSS pixels; the captured height is the page's measured scroll height. Horizontal overflow outside the viewport is not captured. This reflects the configured browser viewport and is recorded in the capture geometry; images are never resized to make them comparable. Fonts are awaited, locale and timezone are fixed, and all page data are authored constants. Only examples containing translated text actually test another writing system; these are not a comprehensive multilingual benchmark.

`ml/scenes.mjs` applies requested changes and retains those requests as provenance. `ml/verify.mjs` receives only rendered element observations and pixel evidence. It does not inspect operation names. It measures new clipping using descendant range rectangles and a clipping ancestor, visible border crossing, visibility changes, displacement, and opaque foreign elements sampled with `elementFromPoint`. Transparent pointer-inert rectangles and operations that have no visible effect supply counterexamples. A requested operation does not itself establish a positive label. Null values are unknown, and the training loss masks them. Overlap measurements outside the captured viewport, geometry without a visibly bordered container, and positive geometric claims without changed raster pixels can remain unknown.

This verifier has limits. Grid sampling can miss small occlusion; rectangles approximate rendered text and shape boundaries; visibility styles do not establish clickability. The sample audit records which images the executor actually inspected. It is an internal visual audit, not external human annotation. Labels describe new observable phenomena, not user intent or defects. The intentional-move cases retain displacement labels. No-op pages produce no candidates; absence of reviewer feedback is never training supervision.

The formal candidate generator in `core/index.ts` supplies every training and evaluation candidate. Ground-truth regions are used only afterward to match the measured labels. An observation matches a candidate when at least 10% of its region or 10% of the candidate intersects. This loose evidence association is not a claim of tight object localization. `artifacts/candidate-evaluation.json` preserves every positive observation, including observations with no matching candidate, and reports coverage and candidate tightness separately. Candidate counts include zero-candidate pages.

The data manifest records source, split, configuration, image SHA-256, source HTML SHA-256, necessary observed geometry, measurements, and rendering conditions. Repeated and intentional-move inputs can be exact duplicates within a family; they never cross a split. Tests check source and exact-raster leakage. Perceptual duplicates beyond this authored source grouping are not ruled out by an independent similarity model.

Reproduce from the repository root:

```sh
node ml/generate.mjs
python -m ml.prepare
python -m ml.publish_examples
```

`data/` holds large regeneration caches and is excluded from source control. Published example PNGs, source manifests, grouping, generator source, and their hashes are retained. The independently authored challenge fixtures are defined outside this generator and are evaluated only after model selection is frozen.
