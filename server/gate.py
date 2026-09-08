import argparse
import json
import math
import re
from pathlib import Path

DECISIONS = ('unreviewed', 'confirm_defect', 'intentional_change', 'uncertain')
STATUSES = ('satisfied', 'violated', 'inconclusive', 'error', 'unchecked')


def text(value):
    return isinstance(value, str) and bool(value.strip())


def number(value):
    return type(value) in (int, float) and -1.7976931348623157e308 <= value <= 1.7976931348623157e308 and math.isfinite(value)


def contract_valid(contract):
    items = [contract]
    if isinstance(contract, dict):
        items.extend(contract[k] for k in ('before', 'after') if k in contract)
    for item in items:
        if (not isinstance(item, dict) or item.get('status') not in STATUSES or
                item.get('type') not in ('required-visible', 'inside-container', 'non-overlap') or
                not text(item.get('selector')) or not isinstance(item.get('measurements'), list) or not item['measurements']):
            return False
        if item['status'] in ('satisfied', 'violated') and len(item['measurements']) != (1 if item['type'] == 'required-visible' else 2):
            return False
        for measurement in item['measurements']:
            if (not isinstance(measurement, dict) or not text(measurement.get('selector')) or
                    not number(measurement.get('matches')) or measurement['matches'] < 0 or measurement['matches'] % 1):
                return False
            if item['status'] in ('satisfied', 'violated'):
                box = measurement.get('box')
                if measurement['matches'] != 1 or not isinstance(box, dict) or any(not number(box.get(k)) for k in ('x', 'y', 'width', 'height')):
                    return False
    return 'after' not in contract or same_contract(contract, contract['after'])


def same_contract(left, right):
    return all(left.get(k) == right.get(k) for k in ('status', 'type', 'selector', 'container', 'other'))


def evidence_error(run):
    if not isinstance(run, dict):
        return 'Report must be a JSON object'
    if (('schemaVersion' in run and run['schemaVersion'] != '1.0') or
            ('reportSchema' in run and run['reportSchema'] != 'renderguard-report/1') or
            not ('schemaVersion' in run or 'reportSchema' in run or run.get('source') == 'browser PNG import')):
        return 'Unsupported report format'
    if run.get('execution') != 'complete':
        return 'Execution or comparison evidence is incomplete'
    if not text(run.get('id')):
        return 'Report identity is missing'
    analysis = run.get('analysis')
    if not isinstance(analysis, dict) or not isinstance(analysis.get('candidates'), list):
        return 'Analysis evidence is incomplete'
    if (any(not number(analysis.get(k)) or analysis[k] <= 0 for k in ('width', 'height')) or
            not number(analysis.get('heightDelta')) or not number(analysis.get('changedPixels')) or
            analysis['changedPixels'] < 0 or analysis.get('mode') not in ('regions', 'tiles') or not text(analysis.get('version'))):
        return 'Analysis evidence is incomplete'
    ids = set()
    for candidate in analysis['candidates']:
        if not isinstance(candidate, dict) or not text(candidate.get('id')) or candidate['id'] in ids:
            return 'Candidate identities are invalid'
        if not number(candidate.get('changedPixels')) or candidate['changedPixels'] < 0:
            return 'Candidate pixel count is invalid'
        box = candidate.get('box')
        if not isinstance(box, dict) or any(not number(box.get(k)) or box[k] < (1 if k in ('width', 'height') else 0) for k in ('x', 'y', 'width', 'height')):
            return 'Candidate geometry is invalid'
        ids.add(candidate['id'])
    if analysis['changedPixels'] > 0 and not ids:
        return 'Candidate evidence is incomplete'
    model = run.get('model')
    if (not isinstance(model, dict) or not text(model.get('version')) or not isinstance(model.get('sha256'), str) or
            re.fullmatch('[a-fA-F0-9]{64}', model['sha256']) is None or model.get('preprocessVersion') != analysis['version']):
        return 'Model evidence is incomplete'
    predictions = run.get('predictions')
    if not isinstance(predictions, list):
        return 'Model results are incomplete'
    predicted = set()
    for prediction in predictions:
        if (not isinstance(prediction, dict) or not text(prediction.get('candidateId')) or
                prediction['candidateId'] not in ids or prediction['candidateId'] in predicted):
            return 'Prediction associations are invalid'
        for key in ('logits', 'scores'):
            values = prediction.get(key)
            if not isinstance(values, list) or len(values) != 5 or any(not number(v) or (key == 'scores' and not 0 <= v <= 1) for v in values):
                return 'Model results are invalid'
        predicted.add(prediction['candidateId'])
    if predicted != ids:
        return 'Model results are incomplete'
    contracts = run.get('contracts', [])
    if not isinstance(contracts, list):
        return 'Contract evidence is invalid'
    targets = set(ids)
    for contract in contracts:
        if not contract_valid(contract) or not text(contract.get('id')) or contract['id'] in targets:
            return 'Contract evidence is invalid'
        targets.add(contract['id'])
    if 'capture' in run:
        capture = run['capture']
        if not isinstance(capture, dict) or capture.get('execution') != 'complete' or not isinstance(capture.get('contracts'), list):
            return 'Capture evidence is incomplete'
        declared = capture['contracts']
        if len(declared) != len(contracts) or any(not contract_valid(c) or c.get('id') != contracts[i]['id'] or not same_contract(c, contracts[i]) for i, c in enumerate(declared)):
            return 'Declared contract results are incomplete'
        for side in ('before', 'after'):
            captured = capture.get(side)
            if not isinstance(captured, dict) or not isinstance(captured.get('contracts'), list) or len(captured['contracts']) != len(contracts):
                return 'Declared contract results are incomplete'
            for i, contract in enumerate(captured['contracts']):
                expected = contracts[i].get(side)
                if not contract_valid(contract) or not isinstance(expected, dict) or not same_contract(contract, expected):
                    return 'Declared contract results are incomplete'
    decisions = run.get('decisions')
    if not isinstance(decisions, dict):
        return 'Review evidence is incomplete'
    for candidate_id, review in decisions.items():
        if candidate_id not in targets or not isinstance(review, dict) or review.get('decision') not in DECISIONS:
            return 'Review associations or decisions are invalid'
    if 'events' in run:
        if not isinstance(run['events'], list):
            return 'Review history is invalid'
        for event in run['events']:
            if not isinstance(event, dict):
                return 'Review history is invalid'
            if event.get('kind') in ('review', 'undo'):
                if not text(event.get('candidateId')) or event['candidateId'] not in targets or event.get('runId') != run['id']:
                    return 'Review history associations are invalid'
    return None


def evaluate_gate(run):
    error = evidence_error(run)
    if error:
        return {'code': 3, 'reason': error}
    contracts = run.get('contracts', [])
    if any(c['status'] in ('inconclusive', 'error', 'unchecked') for c in contracts):
        return {'code': 3, 'reason': 'A declared requirement could not be checked'}
    decisions = run['decisions']
    if any(c['status'] == 'violated' for c in contracts) or any(d['decision'] == 'confirm_defect' for d in decisions.values()):
        return {'code': 2, 'reason': 'Confirmed defect or declared contract violation'}
    ids = [c['id'] for c in run['analysis']['candidates']]
    if any(decisions.get(i, {}).get('decision') != 'intentional_change' for i in ids):
        return {'code': 1, 'reason': 'Visual changes remain unreviewed or uncertain'}
    return {'code': 0, 'reason': 'No blocking items under the declared review policy'}


def main():
    parser = argparse.ArgumentParser(description='Evaluate a saved RenderGuard JSON report')
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    try:
        run = json.loads(args.report.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError, OSError):
        result = {'code': 3, 'reason': 'Report cannot be read as JSON'}
    else:
        result = evaluate_gate(run)
    print(json.dumps(result))
    raise SystemExit(result['code'])


if __name__ == '__main__':
    main()
