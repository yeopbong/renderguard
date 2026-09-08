#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
training_device="${RENDERGUARD_DEVICE:-cpu}"
node ml/generate.mjs
.venv/bin/python -m ml.prepare
.venv/bin/python -m ml.train --device "$training_device" --epochs 6 --seeds 17,29,43
.venv/bin/python -m ml.publish_examples
.venv/bin/python -m ml.feedback --build-buffer
.venv/bin/python -m ml.finalize
.venv/bin/python -m ml.replay --device "$training_device"
node --import tsx ml/stress-generate.mjs
.venv/bin/python -m ml.stress --device "$training_device"
.venv/bin/python -m ml.numerical
.venv/bin/python -m ml.evaluate
node --import tsx ml/benchmark.mjs
.venv/bin/python -m ml.benchmark
.venv/bin/python -m ml.figures
.venv/bin/python -m ml.identity
.venv/bin/python -m ml.report
