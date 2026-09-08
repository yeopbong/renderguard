"""Gate status is separate from successful report generation."""
import argparse
import json
from pathlib import Path


def evaluate_gate(run):
    if run.get('execution') != 'complete':
        return {'code': 3, 'reason': 'Execution or comparison evidence is incomplete'}
    if any(c.get('status') in ('inconclusive', 'error', 'unchecked') for c in run.get('contracts', [])):
        return {'code': 3, 'reason': 'A declared requirement could not be checked'}
    decisions = run.get('decisions', {})
    if any(c.get('status') == 'violated' for c in run.get('contracts', [])) or any(d.get('decision') == 'confirm_defect' for d in decisions.values()):
        return {'code': 2, 'reason': 'Confirmed defect or declared contract violation'}
    ids = [c['id'] for c in run.get('analysis', {}).get('candidates', [])]
    if any(decisions.get(i, {}).get('decision') != 'intentional_change' for i in ids):
        return {'code': 1, 'reason': 'Visual changes remain unreviewed or uncertain'}
    return {'code': 0, 'reason': 'No blocking items under the declared review policy; this is not a production safety guarantee'}


def main():
    parser = argparse.ArgumentParser(description='Evaluate a saved RenderGuard JSON report')
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    try:
        result = evaluate_gate(json.loads(args.report.read_text()))
    except (ValueError, OSError, TypeError):
        result = {'code': 3, 'reason': 'Report cannot be read'}
    print(json.dumps(result))
    raise SystemExit(result['code'])

if __name__ == '__main__':
    main()
