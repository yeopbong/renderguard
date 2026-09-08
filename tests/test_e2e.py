from __future__ import annotations
import base64
import hashlib
import json
import math
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.analysis import ROOT, node_command


def scene(after=False):
    left = 260 if after else 20
    clipping = 58 if after else 200
    vanished = '' if after else '<aside class="badge">Preview available</aside>'
    return f'''<!doctype html><html><meta charset="utf-8"><style>
    html,body{{margin:0;background:#f3f6fa;color:#123;font:18px Arial}}body{{padding:24px}}
    .frame{{position:relative;width:340px;height:240px;border:3px solid #345;background:white;padding:15px}}
    .move{{position:absolute;left:{left}px;top:100px;width:130px;height:45px;background:#176653;color:white;border:0}}
    .neighbor{{position:absolute;left:290px;top:110px;width:38px;height:55px;background:#be6c33}}
    .clip{{width:{clipping}px;white-space:nowrap;overflow:hidden;font-weight:bold}}
    .badge{{position:absolute;top:195px;left:20px;color:#385;}}.space{{height:1300px}}.tail{{height:70px;background:#123;color:white}}
    </style><section class="frame" data-ready><h1>Preferences</h1><p class="clip">Delivery information</p><button class="move">Save changes</button><div class="neighbor"></div>{vanished}</section><div class="space"></div><footer class="tail">Document footer</footer></html>'''


@pytest.fixture(scope='module')
def fixture_origin():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            if self.path == '/wide':
                self.wfile.write(b'<!doctype html><div data-ready style="width:900px;height:100px">Wide page</div>')
            else:
                self.wfile.write(scene(self.path == '/after').encode())

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def authenticated(client):
    response = client.get('/api/session')
    assert response.status_code == 200
    return {'X-RenderGuard-Token': response.json()['token'], 'Origin': 'http://localhost:8765'}


def wait_job(client, job, timeout=90):
    deadline = time.monotonic() + timeout
    stages = []
    while time.monotonic() < deadline:
        response = client.get('/api/jobs/' + job['id'])
        assert response.status_code == 200
        state = response.json()
        if not stages or stages[-1] != state['stage']:
            stages.append(state['stage'])
        if state['status'] not in ('queued', 'running'):
            return state, stages
        time.sleep(.05)
    pytest.fail(f'Background job exceeded {timeout}s: {state}')


def submit_capture(client, headers, project, origin, contracts=None, **updates):
    config = {'beforeUrl': origin + '/before', 'afterUrl': origin + '/after', 'viewport': {'width': 480, 'height': 640}, 'deviceScaleFactor': 2, 'readySelector': '[data-ready]', 'state': {'fixedTime': 1700000000000, 'randomSeed': 7}, 'contracts': contracts or [], **updates}
    response = client.post(f'/api/projects/{project}/capture', json=config, headers=headers)
    assert response.status_code == 200, response.text
    state, stages = wait_job(client, response.json())
    run = client.get('/api/runs/' + state['runId']).json()
    return state, run, stages


def test_real_capture_model_contract_review_export_restart(tmp_path, fixture_origin):
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://localhost:8765') as client:
        headers = authenticated(client)
        assert client.get('/api/session').json()['model']['available'], 'A real hash-verified ONNX model must be installed for integration tests.'
        project = client.post('/api/projects', json={'name': 'End-to-end project'}, headers=headers).json()['id']
        assert client.get(f'/api/projects/{project}').json()['baseline'] is None
        contracts = [{'type': 'required-visible', 'selector': '.move'}, {'type': 'inside-container', 'selector': '.move', 'container': '.frame'}, {'type': 'non-overlap', 'selector': '.move', 'other': '.neighbor'}]
        state, constrained, stages = submit_capture(client, headers, project, fixture_origin, contracts)
        assert state['status'] == 'complete', state
        assert constrained['execution'] == 'complete'
        assert constrained['environment'] == 'verified'
        assert constrained['gate']['code'] == 2
        assert [item['status'] for item in constrained['contracts']] == ['satisfied', 'violated', 'violated']
        assert constrained['capture']['before']['actualDevicePixelRatio'] == 2
        assert constrained['capture']['before']['cssToImageScale'] == 1
        assert constrained['capture']['before']['imageSize']['height'] > 1600
        assert len(constrained['predictions']) == len(constrained['analysis']['candidates']) > 0
        assert all(len(row['logits']) == 5 and all(math.isfinite(x) for x in row['logits']) for row in constrained['predictions'])
        assert len(constrained['model']['sha256']) == 64
        assert 'capture' in stages
        for side in ['before', 'after', 'diff', 'analysis-before', 'analysis-after']:
            image = client.get(f'/api/runs/{constrained["id"]}/images/{side}')
            assert image.status_code == 200 and image.content.startswith(b'\x89PNG\r\n\x1a\n')

        state, run, _ = submit_capture(client, headers, project, fixture_origin)
        assert state['status'] == 'complete', state
        assert run['gate']['code'] == 1
        assert run['inputHashes'] == constrained['inputHashes']
        assert run['analysis'] == constrained['analysis']
        assert run['predictions'] == constrained['predictions']
        original_predictions = json.loads(json.dumps(run['predictions']))
        original_hashes = run['inputHashes'].copy()
        assert run['decisions'] == {}
        for candidate in run['analysis']['candidates']:
            response = client.post(f'/api/runs/{run["id"]}/reviews', json={'candidateId': candidate['id'], 'decision': 'intentional_change', 'observation': {'layout_displacement': True}}, headers=headers)
            assert response.status_code == 200
        reviewed = response.json()
        assert reviewed['gate']['code'] == 0
        assert reviewed['predictions'] == original_predictions
        assert reviewed['inputHashes'] == original_hashes
        assert all(item['observation']['layout_displacement'] for item in reviewed['decisions'].values())
        assert all(event['old'] == {'decision': 'unreviewed'} and event['new']['decision'] == 'intentional_change' and event['modelVersion'] == run['model']['version'] for event in reviewed['events'])
        undone = client.post(f'/api/runs/{run["id"]}/undo', headers=headers).json()
        assert undone['gate']['code'] == 1
        assert undone['predictions'] == original_predictions
        last = run['analysis']['candidates'][-1]['id']
        reviewed = client.post(f'/api/runs/{run["id"]}/reviews', json={'candidateId': last, 'decision': 'intentional_change', 'observation': {'layout_displacement': True}}, headers=headers).json()
        baseline = client.post(f'/api/projects/{project}/baseline', json={'runId': run['id'], 'side': 'after'}, headers=headers).json()
        assert baseline['baseline']['sha256'] == original_hashes['after']
        assert client.post(f'/api/projects/{project}/baseline/undo', headers=headers).json()['baseline'] is None
        client.post(f'/api/projects/{project}/baseline', json={'runId': run['id'], 'side': 'after'}, headers=headers)
        feedback = client.get(f'/api/projects/{project}/feedback').json()
        assert len(feedback['pagePairs']) == 1
        assert feedback['pagePairs'][0]['runId'] == run['id']
        assert all(item['observations'] == {'layout_displacement': True} for item in feedback['pagePairs'][0]['labels'])
        exported = client.get(f'/api/runs/{run["id"]}/export?format=json').json()
        assert exported['predictions'] == original_predictions
        assert exported['decisions'] == reviewed['decisions']
        html = client.get(f'/api/runs/{run["id"]}/export?format=html').text
        assert 'data:image/png;base64,' in html and '<script src=' not in html
        report = tmp_path / 'offline-report.html'
        report.write_text(html)
        script = '''import {chromium} from 'playwright'; import {pathToFileURL} from 'node:url'; const browser=await chromium.launch({headless:true}); try {const page=await browser.newPage(); const network=[]; page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url())}); await page.goto(pathToFileURL(process.argv[1]).href); await page.locator('img').first().waitFor(); if(network.length)throw new Error('Offline report made network requests'); if(await page.locator('img').count()<2)throw new Error('Evidence images missing'); if(!await page.locator('body').innerText())throw new Error('Report body missing');} finally {await browser.close()}'''
        command = node_command('capture/cli.ts')[:3] + ['--input-type=module', '-e', script, str(report)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, result.stderr
        run_id = run['id']
    with TestClient(create_app(tmp_path), base_url='http://localhost:8765') as restarted:
        reopened = restarted.get(f'/api/runs/{run_id}').json()
        assert reopened['predictions'] == original_predictions
        assert reopened['decisions'] == reviewed['decisions']
        assert reopened['gate']['code'] == 0
        assert restarted.get(f'/api/projects/{project}').json()['baseline']['runId'] == run_id
        assert reopened['events'][-1]['kind'] in ('review', 'baseline')


def test_real_failure_cancel_and_unchecked_contract_never_pass(tmp_path, fixture_origin):
    with TestClient(create_app(tmp_path), base_url='http://localhost:8765') as client:
        headers = authenticated(client)
        project = client.post('/api/projects', json={'name': 'Failure semantics'}, headers=headers).json()['id']
        state, unchanged, _ = submit_capture(client, headers, project, fixture_origin, [{'type': 'required-visible', 'selector': '#absent'}], afterUrl=fixture_origin + '/before')
        assert state['status'] == 'complete', state
        assert unchanged['analysis']['changedPixels'] == 0
        assert unchanged['contracts'][0]['status'] == 'inconclusive'
        assert unchanged['gate']['code'] == 3
        state, wide, _ = submit_capture(client, headers, project, fixture_origin, afterUrl=fixture_origin + '/wide')
        assert state['status'] == 'error'
        assert wide['execution'] == 'incomparable'
        assert wide['gate']['code'] == 3
        response = client.post(f'/api/projects/{project}/capture', headers=headers, json={'beforeUrl': fixture_origin + '/before', 'afterUrl': fixture_origin + '/after', 'viewport': {'width': 480, 'height': 640}, 'readySelector': '#never-ready', 'timeoutMs': 60000})
        job = response.json()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and client.get('/api/jobs/' + job['id']).json()['status'] == 'queued':
            time.sleep(.03)
        assert client.post('/api/jobs/' + job['id'] + '/cancel', headers=headers).status_code == 200
        cancelled, _ = wait_job(client, job, timeout=15)
        assert cancelled['status'] == 'cancelled'
        failed = client.get('/api/runs/' + cancelled['runId']).json()
        assert failed['execution'] == 'cancelled'
        assert failed['gate']['code'] == 3
        response = client.post(f'/api/projects/{project}/import', headers=headers, json={'before': 'data:image/png;base64,AAAA', 'after': 'data:image/png;base64,AAAA'})
        bad, _ = wait_job(client, response.json())
        assert bad['status'] == 'error'
        assert client.get('/api/runs/' + bad['runId']).json()['gate']['code'] == 3
