# Visual observation model

The model has five sigmoid outputs: `clipping`, `overlap_or_occlusion`, `out_of_container`, `element_disappearance` and `layout_displacement`. They estimate visual observations; contracts and reviewer decisions remain separate.

## Weights and inputs

The shared encoder starts from [timm/mobilenetv3_small_100.lamb_in1k](https://huggingface.co/timm/mobilenetv3_small_100.lamb_in1k/tree/1824797e7887cbec1990e4adbd6675960a36c589), licensed Apache-2.0. Its source revision is `1824797e7887cbec1990e4adbd6675960a36c589` and `model.safetensors` SHA-256 is `46d2c063b18125884c48937afa4c49e18128869e52e8db96df48bf0a4d7ff697`. Downloads are checked before loading. The paired head and fine-tuned weights modify this initialization; [MODEL-LICENSE](../artifacts/MODEL-LICENSE) accompanies them. Upstream ImageNet training images are not distributed here.

Four shared MobileNetV3-Small encoder calls process local and context crops before/after the change. Each returns 576 channels. The head combines before, after, absolute difference and product features with 12 image-derived geometry values, then a 128-unit ReLU layer, dropout 0.15 and five logits. Inputs exclude DOM rules, operation names, source IDs, labels and review decisions.

Shared TypeScript preprocessing produces RGB NCHW float32 crops at 96 × 96. Alpha composites onto white; bilinear letterboxing retains the whole crop with ImageNet normalization. Local padding is at least 8 pixels or 8% of the candidate's larger dimension; context padding is at least 40 pixels or 65%. Large regions can lose fine detail at this resolution. The preprocessing version is `rgba-diff-rle-letterbox-v1`.

ONNX opset 17 inputs are `local_before`, `local_after`, `context_before`, `context_after` (`N×3×96×96`) and `geometry` (`N×12`); output is `logits` (`N×5`). The browser runs ONNX Runtime Web WASM in a Worker. Missing or mismatched assets produce an error.

## Training and calibration

Masked binary cross-entropy ignores unknown labels. Positive weights come from training labels and are capped at 10. Two head-warmup epochs precede four epochs updating the head and last three encoder stages with AdamW. BatchNorm statistics remain frozen. Fixed-feature comparisons freeze the encoder entirely.

Each primary configuration uses seeds 17, 29 and 43. Development macro PR-AUC selects the released local + context seed. Calibration/test results do not select it. The manifest records source, upstream/data/split/weight hashes and preprocessing version. Curves and seed-level results remain in [experiments](experiments.md).

Classes with at least 15 known positives and 15 known negatives receive temperature-and-bias calibration on separate families; the rest stay uncalibrated. Any model or preprocessing change invalidates calibration.

## Reproduce or use feedback

Run `python -m ml.train --epochs 6 --device cpu`, or choose `--device mps` on supported macOS hardware. Initial training downloads the verified generic weights; prepared inference works offline.

Explicit feedback training uses:

```sh
python -m ml.feedback --feedback feedback.json --output candidate-model
```

Only corrected observation labels train the frozen-encoder head, mixed with retained training examples. A separate retained development subset compares the candidate with the current model; eligibility permits at most a 0.03 macro PR-AUC decrease. Activation is manual, calibration is invalidated, and the previous version remains available for rollback.
