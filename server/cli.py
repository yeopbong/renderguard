"""Analyze inputs and write a report; use the separate gate command for policy."""
import argparse
import base64
import json
import tempfile
import threading
from pathlib import Path
from .analysis import run_analysis
from .reports import report_html, report_json
from .store import Store, atomic


def main():
    parser = argparse.ArgumentParser(description='Analyze a PNG pair or a local capture configuration')
    parser.add_argument('--before', type=Path)
    parser.add_argument('--after', type=Path)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--masks', type=Path)
    parser.add_argument('--workspace', type=Path, default=Path('workspace'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.capture:
        config = json.loads(args.capture.read_text())
        kind = 'capture'
    elif args.before and args.after:
        config = {side: 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode() for side, path in [('before', args.before), ('after', args.after)]}
        config['masks'] = json.loads(args.masks.read_text()) if args.masks else []
        kind = 'import'
    else:
        parser.error('Supply --before and --after, or --capture')
    store = Store(args.workspace)
    project = store.create_project('Command-line analysis')
    job = store.create_job(project['id'], kind)
    run_analysis(store, job, config, threading.Event())
    job = store.job(job['id'])
    evidence = store.run(job['runId'])
    folder = store.root / 'runs' / evidence['id']
    result = report_html(evidence, folder) if args.output.suffix == '.html' else json.dumps(report_json(evidence, folder), indent=2)
    atomic(args.output, result.encode())
    print(json.dumps({'execution': evidence['execution'], 'gate': evidence['gate'], 'report': args.output.name, 'runId': evidence['id']}))
    raise SystemExit(0 if evidence['execution'] == 'complete' else 3)

if __name__ == '__main__':
    main()
