import base64
import html
import json
from pathlib import Path

from .gate import evaluate_gate, evidence_error


def report_json(run, folder):
    value = dict(run)
    value['gate'] = evaluate_gate(run)
    value['images'] = {}
    for side in ('before', 'after'):
        path = folder / f'{side}.png'
        if path.exists():
            value['images'][side] = 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode()
    value['snapshotNotice'] = 'Evidence snapshot. It cannot update a project or retrain a model.'
    return value


def report_html(run, folder):
    value = report_json(run, folder)
    if evidence_error(run):
        return '<!doctype html><html lang="en"><meta charset="utf-8"><title>RenderGuard report</title><h1>Gate: 3 · ' + html.escape(value['gate']['reason']) + '</h1><pre>' + html.escape(json.dumps(value, indent=2)) + '</pre></html>'
    images = ''.join(f'<figure><figcaption>{side.title()}</figcaption><img alt="{side}" src="{src}"></figure>' for side, src in value['images'].items())
    rows = []
    for candidate in run.get('analysis', {}).get('candidates', []):
        decision = run.get('decisions', {}).get(candidate['id'], {}).get('decision', 'unreviewed')
        prediction = next((p for p in run.get('predictions', []) if p['candidateId'] == candidate['id']), {})
        rows.append('<tr><td>' + html.escape(candidate['id']) + '</td><td>' + html.escape(json.dumps(candidate['box'])) + '</td><td>' + html.escape(decision) + '</td><td>' + html.escape(json.dumps(prediction.get('scores', []))) + '</td></tr>')
    detail = dict(value)
    detail.pop('images')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>RenderGuard evidence report</title><style>body{font:15px system-ui;margin:40px;color:#18332d}h1{font-size:32px}section{display:flex;gap:20px}figure{margin:0;width:50%}img{width:100%}table{border-collapse:collapse;width:100%;margin:24px 0}td,th{padding:10px;text-align:left;border-bottom:1px solid #ccd8d3}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f5f2;padding:20px}small{color:#546b60}</style><h1>RenderGuard / Evidence snapshot</h1><p>' + html.escape(value['snapshotNotice']) + '</p><p>Execution: ' + html.escape(run['execution']) + ' · Gate: ' + str(value['gate']['code']) + ' · ' + html.escape(value['gate']['reason']) + '</p><small>Observation scores describe visible symptoms, not defect probability. Difference images are not causal explanations.</small><section>' + images + '</section><table><thead><tr><th>Candidate</th><th>Image pixel bounds</th><th>Decision</th><th>Observation scores</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table><details><summary>Complete evidence and audit history</summary><pre>' + html.escape(json.dumps(detail, indent=2)) + '</pre></details></html>'
