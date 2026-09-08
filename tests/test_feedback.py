"""A real explicit feedback update, retained evaluation, activation and rollback."""
import base64
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient
from server.app import create_app
from server.analysis import ROOT


def wait(client, job, seconds=120):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        state = client.get('/api/jobs/' + job['id']).json()
        if state['status'] not in ('queued', 'running'):
            assert state['status'] == 'complete', state
            return state
        time.sleep(.1)
    raise AssertionError('Feedback pipeline exceeded its bounded timeout')


def test_explicit_training_evaluation_activation_and_rollback(tmp_path):
    app = create_app(tmp_path)
    images = {side: 'data:image/png;base64,' + base64.b64encode((ROOT / f'web/public/examples/profile-0-cover-{side}.png').read_bytes()).decode() for side in ('before', 'after')}
    with TestClient(app, base_url='http://localhost:8765') as client:
        token = client.get('/api/session').json()['token']
        headers = {'X-RenderGuard-Token': token}
        original_model = client.get('/api/models').json()['active']
        project = client.post('/api/projects', json={'name': 'Explicit learning'}, headers=headers).json()['id']
        state = wait(client, client.post(f'/api/projects/{project}/import', json=images, headers=headers).json())
        run = client.get('/api/runs/' + state['runId']).json()
        assert len(run['analysis']['candidates']) == 1
        candidate = run['analysis']['candidates'][0]['id']
        # The original authored example has a visually audited opaque panel covering biography text.
        correction = {'clipping': False, 'overlap_or_occlusion': True, 'out_of_container': False, 'element_disappearance': False, 'layout_displacement': False}
        client.post(f'/api/runs/{run["id"]}/reviews', json={'candidateId': candidate, 'decision': 'uncertain', 'observation': correction}, headers=headers).raise_for_status()
        before = client.get('/api/runs/' + run['id']).json()
        response = client.post('/api/train', json={'projectId': project}, headers=headers)
        assert response.status_code == 200
        trained = wait(client, response.json())
        models = client.get('/api/models').json()
        assert models['active'] == original_model, 'Training must not silently activate a model'
        new = next(model for model in models['models'] if model['version'] == trained['modelVersion'])
        assert new['modelSha256'] != run['model']['sha256']
        assert new['evaluation']['encoderUnchanged']
        assert new['evaluation']['oldTrainingCandidates'] > 0
        assert new['evaluation']['devCandidates'] > 0
        assert len(new['evaluation']['curve']) == 5
        assert new['evaluationPassed'], new['evaluation']
        activated = client.post('/api/models/activate', json={'version': new['version']}, headers=headers)
        assert activated.status_code == 200, activated.text
        assert activated.json()['active'] == new['version']
        state = wait(client, client.post(f'/api/projects/{project}/import', json=images, headers=headers).json())
        new_run = client.get('/api/runs/' + state['runId']).json()
        assert new_run['id'] != run['id']
        assert new_run['model']['sha256'] == new['modelSha256']
        assert all(c['status'] == 'uncalibrated' for c in new_run['calibration']['classes'])
        assert new_run['decisions'] == {}
        assert new_run['gate']['code'] == 1
        assert client.get('/api/runs/' + run['id']).json() == before
        rollback = client.post('/api/models/activate', json={'version': original_model}, headers=headers)
        assert rollback.status_code == 200
        assert rollback.json()['active'] == original_model
        assert client.get('/api/runs/' + run['id']).json() == before
