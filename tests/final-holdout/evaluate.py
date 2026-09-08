from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[2]
IMAGE_FLOATS = 3 * 96 * 96
ROW_FLOATS = IMAGE_FLOATS * 4 + 12

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def metrics(rows, labels, cutoffs):
    out = {}
    for k, label in enumerate(labels):
        valid = [r for r in rows if r['observations'][k] is not None and not r.get('duplicateOf')]
        y = np.asarray([r['observations'][k] for r in valid], dtype=bool)
        scores = np.asarray([r['pageScores'][k] for r in valid])
        pred = scores >= cutoffs[k]
        tp, fp, fn = int((pred & y).sum()), int((pred & ~y).sum()), int((~pred & y).sum())
        order = np.argsort(-scores, kind='stable')
        positives = int(y.sum()); average_precision = None
        if positives and (~y).any():
            total, found, previous_recall, average_precision = 0, 0, 0., 0.
            for score in np.unique(scores)[::-1]:
                group = scores == score
                total += int(group.sum()); found += int(y[group].sum())
                recall = found / positives
                average_precision += (recall - previous_recall) * found / total
                previous_recall = recall
        out[label] = {'threshold': cutoffs[k], 'knownPages': len(valid), 'positivePages': positives, 'negativePages': len(valid) - positives, 'tp': tp, 'fp': fp, 'fn': fn, 'precision': tp / (tp + fp) if tp + fp else None, 'recall': tp / (tp + fn) if tp + fn else None, 'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None, 'averagePrecision': average_precision, 'positivePrevalence': positives / len(valid) if valid else None}
    return out

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--captures', type=Path, default=ROOT / 'artifacts/final-holdout')
    parser.add_argument('--model', type=Path, default=ROOT / 'web/public/models')
    parser.add_argument('--expected-model-sha', required=True)
    args = parser.parse_args()
    source = Path(__file__).parent
    output = args.captures / 'model-evaluation.json'
    if output.exists():
        raise SystemExit('The new-family holdout was already evaluated. Preserve that evidence; no automatic rerun is allowed.')
    freeze = json.loads((source / 'freeze.json').read_text())
    if digest(source / 'manifest.json') != freeze['manifestSha256']:
        raise SystemExit('Frozen annotation manifest mismatch.')
    manifest = json.loads((source / 'manifest.json').read_text())
    for file, expected in freeze['sourceHashes'].items():
        if digest(ROOT / file) != expected:
            raise SystemExit(f'Frozen source mismatch: {file}')
    model_hash = digest(args.model / 'model.onnx')
    model = json.loads((args.model / 'manifest.json').read_text())
    calibration = json.loads((args.model / 'calibration.json').read_text())
    if model_hash != args.expected_model_sha or model_hash != model['modelSha256'] or calibration['modelSha256'] != model_hash or calibration['preprocessVersion'] != model['preprocessVersion']:
        raise SystemExit('Model, expected final SHA, or calibration mismatch.')
    options = ort.SessionOptions(); options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(args.model / 'model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
    results = []
    for item in manifest['cases']:
        folder = args.captures / item['id']
        for side in ('before', 'after'):
            if digest(source / item[side]) != item['fixtureHashes'][side] or digest(folder / f'{side}.png') != item['screenshotHashes'][side]:
                raise SystemExit(f'Fixture or screenshot integrity failure: {item["id"]}/{side}')
        data = json.loads((folder / 'tensors.json').read_text())
        if data['version'] != model['preprocessVersion']:
            raise SystemExit('Tensor preprocessing mismatch.')
        count = len(data['candidates']); predictions = []
        if count:
            tensors = np.fromfile(folder / 'tensors.f32', dtype='<f4').reshape(count, ROW_FLOATS)
            for index in range(0, count, 4):
                batch = tensors[index:index + 4]
                feeds = {name: np.ascontiguousarray(batch[:, k * IMAGE_FLOATS:(k + 1) * IMAGE_FLOATS].reshape(-1, 3, 96, 96)) for k, name in enumerate(['local_before', 'local_after', 'context_before', 'context_after'])}
                feeds['geometry'] = np.ascontiguousarray(batch[:, 4 * IMAGE_FLOATS:])
                logits = session.run(None, feeds)[0]
                for offset, row in enumerate(logits):
                    transformed = [float(row[k]) / c['temperature'] + c['bias'] if c['status'] == 'calibrated' else float(row[k]) for k, c in enumerate(calibration['classes'])]
                    scores = (1 / (1 + np.exp(-np.clip(transformed, -60, 60)))).tolist()
                    predictions.append({'candidateId': data['candidates'][index + offset]['id'], 'logits': row.tolist(), 'scores': scores})
        results.append({'id': item['id'], 'family': item['family'], 'duplicateOf': item.get('duplicateOf'), 'observations': item['observations'], 'intentional': item['intentional'], 'candidateCount': count, 'changedPixels': data['changedPixels'], 'candidates': data['candidates'], 'predictions': predictions, 'pageScores': np.max([p['scores'] for p in predictions], axis=0).tolist() if predictions else [0.] * 5})
    unique = [r for r in results if not r['duplicateOf']]
    report = {'schemaVersion': '1.0', 'modelSha256': model_hash, 'modelVersion': model['version'], 'preprocessVersion': model['preprocessVersion'], 'manifestSha256': freeze['manifestSha256'], 'withheldAtEvaluation': True, 'externalAcceptance': False, 'evaluationPasses': 1, 'modelUpdatedFromHoldout': False, 'labelChangedAfterPredictions': False, 'renderedPairs': len(results), 'uniqueImagePairs': len(unique), 'familyCount': len(manifest['families']), 'thresholdPolicy': 'Both the fixed 0.5 cutoff and the already-published development-selected calibrated cutoffs were specified before this evaluation.', 'publishedThresholds': metrics(results, manifest['labels'], model['thresholds']), 'fixedHalf': metrics(results, manifest['labels'], [.5] * 5), 'families': {family: metrics([r for r in results if r['family'] == family], manifest['labels'], model['thresholds']) for family in manifest['families']}, 'meanCandidatesPerUniquePage': sum(r['candidateCount'] for r in unique) / len(unique), 'positivePagesWithoutCandidates': sum(any(v == 1 for v in r['observations']) and r['candidateCount'] == 0 for r in unique), 'cases': results, 'limitations': ['Only three authored structures; source-family uncertainty is large.', 'Shared low-level styling within this holdout is recorded; these are not independent external sites.', 'All observations describe newly appearing or worsening signs; unchanged pre-existing clipping is not a positive.', 'Page maximum aggregation differs from candidate-level calibration and threshold fitting.', 'Repeated pixel-identical captures are retained as stability evidence but excluded from metric denominators.', 'This set does not establish production defect detection or external acceptance.']}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['modelSha256', 'renderedPairs', 'uniqueImagePairs', 'familyCount', 'positivePagesWithoutCandidates', 'publishedThresholds']}, indent=2))

if __name__ == '__main__':
    main()
