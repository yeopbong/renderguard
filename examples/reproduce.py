"""Reproduce local capture, immutable evidence, explicit review, and offline demo reports."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.reports import report_html, report_json
from server.store import Store


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    handler = partial(QuietHandler, directory=str(ROOT / 'examples'))
    server = ThreadingHTTPServer(('127.0.0.1', 9030), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    records = []
    try:
        with tempfile.TemporaryDirectory(prefix='renderguard-demos-') as temporary:
            for name in ('main', 'intentional', 'failure'):
                destination = ROOT / 'examples' / name
                workspace = Path(temporary) / name
                result = subprocess.run([sys.executable, '-m', 'server.cli', '--capture', str(destination / 'capture.json'), '--workspace', str(workspace), '--output', str(destination / 'raw-result.json')], cwd=ROOT, text=True, capture_output=True, timeout=120)
                if result.returncode != 0:
                    raise RuntimeError(f'{name}: CLI analysis failed: {result.stderr[-300:]}')
                summary = json.loads(result.stdout.strip().splitlines()[-1])
                store = Store(workspace)
                raw = store.run(summary['runId'])
                original_predictions = raw['predictions']
                if name == 'intentional':
                    for candidate in raw['analysis']['candidates']:
                        store.review(raw['id'], candidate['id'], 'intentional_change', {'layout_displacement': True})
                    store.baseline(raw['projectId'], raw['id'], 'after')
                    store.baseline(raw['projectId'], undo=True)
                    store.baseline(raw['projectId'], raw['id'], 'after')
                if name == 'main':
                    for candidate in raw['analysis']['candidates']:
                        store.review(raw['id'], candidate['id'], 'confirm_defect')
                evidence = store.run(raw['id'])
                assert evidence['predictions'] == original_predictions, 'Review must not replace raw predictions.'
                expected_gate = {'main': 2, 'intentional': 0, 'failure': 3}[name]
                assert evidence['gate']['code'] == expected_gate, f'{name}: unexpected gate {evidence["gate"]}'
                source = workspace / 'runs' / raw['id']
                for filename in ('before.png', 'after.png', 'diff.png', 'analysis-before.png', 'analysis-after.png', 'manifest.json'):
                    file = source / filename
                    if file.exists():
                        (destination / filename).write_bytes(file.read_bytes())
                (destination / 'report.json').write_text(json.dumps(report_json(evidence, source), indent=2) + '\n')
                (destination / 'report.html').write_text(report_html(evidence, source))
                baseline_history = store.project(raw['projectId'])['baselineHistory']
                record = {'id': name, 'execution': evidence['execution'], 'gate': evidence['gate'], 'model': evidence['model'], 'inputHashes': evidence['inputHashes'], 'configSha256': sha(destination / 'capture.json'), 'sourceHashes': {side: sha(destination / f'{side}.html') for side in ('before', 'after')}, 'rawReportSha256': sha(destination / 'raw-result.json'), 'reviewedReportSha256': sha(destination / 'report.json'), 'htmlReportSha256': sha(destination / 'report.html'), 'candidateCount': len(evidence['analysis']['candidates']), 'rawPredictionsPreserved': evidence['predictions'] == original_predictions, 'baselineHistory': baseline_history, 'reproduce': 'python examples/reproduce.py', 'reviewProvenance': 'Scripted explicit example decisions based on authored scenario intent; no model threshold automatically approves changes.'}
                (destination / 'reproduction.json').write_text(json.dumps(record, indent=2) + '\n')
                records.append(record)
                print(json.dumps({'id': name, 'execution': record['execution'], 'gate': record['gate']['code'], 'candidates': record['candidateCount']}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    (ROOT / 'examples' / 'local-demo-results.json').write_text(json.dumps({'schemaVersion': '1.0', 'records': records}, indent=2) + '\n')

if __name__ == '__main__':
    main()
