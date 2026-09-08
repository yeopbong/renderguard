from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluation', type=Path, default=Path('artifacts/challenge/model-evaluation.json'))
    parser.add_argument('--manifest', type=Path, default=Path('web/public/models/manifest.json'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/challenge/published-thresholds.json'))
    args = parser.parse_args()
    evaluation_bytes = args.evaluation.read_bytes()
    evaluation, model = json.loads(evaluation_bytes), json.loads(args.manifest.read_text())
    if evaluation['modelSha256'] != model['modelSha256']:
        raise SystemExit('Saved scores belong to a different model.')
    thresholds = model['thresholds']
    metrics = {}
    for k, label in enumerate(model['labels']):
        rows = [r for r in evaluation['cases'] if r['execution'] == 'complete' and r['expectedObservations'][k] is not None]
        truth = [r['expectedObservations'][k] == 1 for r in rows]
        pred = [r['pageObservationScores'][k] >= thresholds[k] for r in rows]
        tp = sum(y and p for y, p in zip(truth, pred))
        fp = sum(not y and p for y, p in zip(truth, pred))
        fn = sum(y and not p for y, p in zip(truth, pred))
        metrics[label] = {'threshold': thresholds[k], 'validPages': len(rows), 'positivePages': sum(truth), 'tp': tp, 'fp': fp, 'fn': fn, 'precision': tp / (tp + fp) if tp + fp else None, 'recall': tp / (tp + fn) if tp + fn else None, 'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}
    report = {'schemaVersion': '1.0', 'sourceEvaluationSha256': hashlib.sha256(evaluation_bytes).hexdigest(), 'modelSha256': evaluation['modelSha256'], 'inferenceRerun': False, 'modelChanged': False, 'labelChanged': False, 'primaryEvaluationUnchanged': True, 'thresholdSource': 'Published model manifest; thresholds selected on development calibrated candidate scores before the challenge was evaluated.', 'aggregation': 'Maximum calibrated candidate score per page; missing candidates retain zero page score. Page aggregation differs from the candidate threshold selection domain.', 'readoutStatus': 'Secondary descriptive analysis requested after the prespecified fixed-0.5 readout; no tuning on challenge outcomes.', 'metrics': metrics, 'executionAndContractChecks': {'cases': len(evaluation['cases']), 'executionMatches': sum(r['executionMatchesExpectation'] for r in evaluation['cases']), 'contractMatches': sum(r['contractsMatchExpectation'] for r in evaluation['cases'])}}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
