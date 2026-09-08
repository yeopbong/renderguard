import base64
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server.app import create_app
from server.analysis import decode_png
from server.gate import evaluate_gate
from server.reports import report_html
from server.store import Store, now


def evidence(id='run1', project='project1'):
    run = json.loads((Path(__file__).resolve().parents[1] / 'examples/intentional/report.json').read_text())
    run.update(id=id, projectId=project, createdAt=now(), decisions={}, events=[], contracts=[])
    run.pop('capture')
    run['analysis']['candidates'][0]['id'] = 'r1'
    run['predictions'][0]['candidateId'] = 'r1'
    return run


def test_gate_precedence_and_low_scores():
    run = evidence()
    assert evaluate_gate(run)['code'] == 1
    run['decisions']['r1'] = {'decision': 'intentional_change'}
    assert evaluate_gate(run)['code'] == 0
    run['contracts'] = json.loads((Path(__file__).resolve().parents[1] / 'examples/main/report.json').read_text())['contracts']
    assert evaluate_gate(run)['code'] == 2
    run['contracts'][0]['status'] = 'inconclusive'
    assert evaluate_gate(run)['code'] == 3
    run['execution'] = 'cancelled'
    assert evaluate_gate(run)['code'] == 3
    assert evaluate_gate({})['code'] == 3


def test_immutable_predictions_undo_new_run_and_baseline(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('Example')
    run = evidence(project=project['id'])
    store.save_run(run)
    review = store.review('run1', 'r1', 'intentional_change', {'layout_displacement': True})
    assert review['predictions'] == run['predictions']
    assert review['gate']['code'] == 0
    assert review['events'][0]['old'] == {'decision': 'unreviewed'}
    store.review('run1', 'r1', 'uncertain')
    assert store.run('run1')['decisions']['r1']['observation'] == {'layout_displacement': True}
    undone = store.review('run1', None, None, undo=True)
    assert undone['decisions']['r1']['decision'] == 'intentional_change'
    assert store.review('run1', None, None, undo=True)['decisions']['r1']['decision'] == 'unreviewed'
    with pytest.raises(ValueError):
        store.review('run1', None, None, undo=True)
    newer = evidence(id='run2', project=project['id'])
    store.save_run(newer)
    assert store.run('run2')['gate']['code'] == 1
    store.baseline(project['id'], 'run1', 'after')
    store.baseline(project['id'], 'run2', 'before')
    assert store.baseline(project['id'], undo=True)['baseline']['runId'] == 'run1'
    assert store.baseline(project['id'], undo=True)['baseline'] is None
    restarted = Store(tmp_path)
    assert len([event for event in restarted.run('run1')['events'] if event['kind'] == 'review']) == 4
    assert restarted.run('run1')['predictions'] == run['predictions']


def test_interrupted_jobs_are_never_completed(tmp_path):
    store = Store(tmp_path)
    job = store.create_job(None, 'train')
    store.update_job(job['id'], status='running', completed=2, total=9)
    retained = tmp_path / 'completed.bin'
    retained.write_bytes(b'evidence')
    restarted = Store(tmp_path)
    assert restarted.job(job['id'])['status'] == 'interrupted'
    assert restarted.job(job['id'])['completed'] == 2
    assert retained.read_bytes() == b'evidence'


def test_service_rejects_origin_host_and_missing_token(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://localhost:8765') as client:
        assert client.get('/api/session', headers={'Origin': 'https://evil.example'}).status_code == 403
        assert client.get('/api/session', headers={'Host': 'evil.example'}).status_code == 403
        assert client.get('/api/session', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
        assert client.post('/api/projects', json={'name': 'Test'}).status_code == 403
        token = client.get('/api/session').json()['token']
        headers = {'X-RenderGuard-Token': token, 'Origin': 'http://localhost:8765'}
        response = client.post('/api/projects', json={'name': 'Test'}, headers=headers)
        assert response.status_code == 200
        project = response.json()['id']
        assert client.get('/api/projects/' + project).json()['baseline'] is None
        assert client.post('/api/train', json={'projectId': project}, headers=headers).status_code == 400
        assert client.get('/api/missing').status_code == 404
        assert client.post('/api/projects', content=b'{}', headers={**headers, 'Content-Length': str(60 * 1024 * 1024)}).status_code == 413


def test_png_validation_and_offline_escaping(tmp_path):
    with pytest.raises(ValueError):
        decode_png('data:image/png;base64,bm90LXBuZw==', tmp_path / 'invalid.png')
    with pytest.raises(ValueError):
        decode_png('data:image/jpeg;base64,AA==', tmp_path / 'invalid.png')
    stream = io.BytesIO()
    Image.new('RGB', (12, 20), 'white').save(stream, format='PNG')
    decode_png('data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode(), tmp_path / 'before.png')
    assert (tmp_path / 'before.png').read_bytes() == stream.getvalue()
    run = evidence()
    run['analysis']['candidates'][0]['id'] = '<script>alert(1)</script>'
    run['gate'] = evaluate_gate(run)
    rendered = report_html(run, tmp_path)
    assert '<script>' not in rendered
    assert '&lt;script&gt;' in rendered
    assert 'data:image/png;base64,' in rendered
    assert '<script src=' not in rendered
