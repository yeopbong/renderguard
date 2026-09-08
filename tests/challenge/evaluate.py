from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[2]
IMAGE_FLOATS = 3 * 96 * 96
ROW_FLOATS = 4 * IMAGE_FLOATS + 12


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--captures', type=Path, default=ROOT / 'artifacts/challenge')
    parser.add_argument('--model', type=Path, default=ROOT / 'web/public/models')
    parser.add_argument('--development-rerun', action='store_true')
    args = parser.parse_args()
    output = args.captures / 'model-evaluation.json'
    if output.exists() and not args.development_rerun:
        raise SystemExit('Challenge already evaluated. An explicit development rerun invalidates withheld status.')
    source = Path(__file__).parent
    manifest_bytes = (source / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    freeze = json.loads((source / 'freeze.json').read_text())
    if hashlib.sha256(manifest_bytes).hexdigest() != freeze['manifestSha256']:
        raise SystemExit('Frozen challenge manifest changed.')
    model_bytes = (args.model / 'model.onnx').read_bytes()
    model_hash = hashlib.sha256(model_bytes).hexdigest()
    model_manifest = json.loads((args.model / 'manifest.json').read_text())
    expected_hash = model_manifest.get('modelSha256') or model_manifest.get('sha256')
    if expected_hash != model_hash:
        raise SystemExit('Model integrity check failed.')
    calibration = json.loads((args.model / 'calibration.json').read_text())
    if calibration['modelSha256'] != model_hash or calibration['preprocessVersion'] != model_manifest['preprocessVersion']:
        raise SystemExit('Calibration does not match the model and preprocessing.')
    session = ort.InferenceSession(model_bytes, providers=['CPUExecutionProvider'])
    results = []
    for case in manifest['cases']:
        folder = args.captures / case['id']
        capture = json.loads((folder / 'manifest.json').read_text())
        statuses = [c['status'] for c in capture['contracts']]
        result = {'id': case['id'], 'execution': capture['execution'], 'executionMatchesExpectation': capture['execution'] == case['expectedExecution'], 'contractStatuses': statuses, 'contractsMatchExpectation': statuses == case['expectedContractStatuses'], 'expectedObservations': case['observations'], 'independentDefectConclusion': case['independentDefectConclusion']}
        for side in ('before', 'after'):
            if hashlib.sha256((folder / f'{side}.png').read_bytes()).hexdigest() != capture[side]['sha256']:
                raise SystemExit(f'Captured screenshot hash mismatch: {case["id"]}/{side}')
        if capture['execution'] == 'complete':
            metadata = json.loads((folder / 'tensors.json').read_text())
            if metadata['version'] != model_manifest['preprocessVersion']:
                raise SystemExit('Challenge preprocessing does not match the released model.')
            count = len(metadata['candidates'])
            scores, logits_all = [], []
            if count:
                tensors = np.fromfile(folder / 'tensors.f32', dtype='<f4').reshape(count, ROW_FLOATS)
                for index in range(0, count, 4):
                    batch = tensors[index:index + 4]
                    feeds = {name: np.ascontiguousarray(batch[:, slot * IMAGE_FLOATS:(slot + 1) * IMAGE_FLOATS].reshape(-1, 3, 96, 96)) for slot, name in enumerate(['local_before', 'local_after', 'context_before', 'context_after'])}
                    feeds['geometry'] = np.ascontiguousarray(batch[:, 4 * IMAGE_FLOATS:])
                    logits = session.run(None, feeds)[0]
                    logits_all.extend(logits.tolist())
                    calibrated = logits.copy()
                    for k, item in enumerate(calibration['classes']):
                        if item['status'] == 'calibrated':
                            calibrated[:, k] = calibrated[:, k] / item['temperature'] + item['bias']
                    scores.extend((1 / (1 + np.exp(-np.clip(calibrated, -60, 60)))).tolist())
            result.update(candidateCount=count, changedPixels=metadata['changedPixels'], heightDelta=metadata['heightDelta'], candidates=metadata['candidates'], candidateLogits=logits_all, candidateScores=scores, pageObservationScores=np.max(scores, axis=0).tolist() if scores else [0.0] * 5)
        results.append(result)
    metrics = {}
    for k, label in enumerate(manifest['labels']):
        valid = [r for r in results if r['execution'] == 'complete' and r['expectedObservations'][k] is not None]
        positives = [r for r in valid if r['expectedObservations'][k] == 1]
        tp = sum(r['pageObservationScores'][k] >= .5 for r in positives)
        fp = sum(r['pageObservationScores'][k] >= .5 for r in valid if r['expectedObservations'][k] == 0)
        fn = len(positives) - tp
        metrics[label] = {'validPages': len(valid), 'positivePages': len(positives), 'precisionAtFixedHalf': tp / (tp + fp) if tp + fp else None, 'recallAtFixedHalf': tp / (tp + fn) if tp + fn else None, 'f1AtFixedHalf': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None, 'note': 'Descriptive max-candidate page observation score; fixed 0.5 threshold, not a defect probability or acceptance gate.'}
    report = {'schemaVersion': '1.0', 'manifestSha256': freeze['manifestSha256'], 'modelSha256': model_hash, 'modelVersion': model_manifest['version'], 'preprocessVersion': model_manifest['preprocessVersion'], 'withheldAtEvaluation': not args.development_rerun, 'externalAcceptance': False, 'thresholdSelectedOnChallenge': False, 'metrics': metrics, 'cases': results, 'limitations': ['Twelve authored synthetic page pairs; no production accuracy claim.', 'Observation labels score page-level signs, not defect intent.', 'A zero-candidate positive remains a missed page-level observation.', 'No model selection or calibration is permitted from this evaluation while retaining withheld status.']}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'modelSha256': model_hash, 'cases': len(results), 'executionChecks': all(r['executionMatchesExpectation'] for r in results), 'contractChecks': all(r['contractsMatchExpectation'] for r in results)}))

if __name__ == '__main__':
    main()
