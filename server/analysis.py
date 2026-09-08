"""Canonical TypeScript preprocessing followed by bounded ONNX batches."""
from __future__ import annotations
import base64
import binascii
import io
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .store import atomic, digest, now, uid, write_json

ROOT = Path(__file__).resolve().parents[1]
LABELS = ['clipping', 'overlap_or_occlusion', 'out_of_container', 'element_disappearance', 'layout_displacement']
IMAGE_FLOATS = 3 * 96 * 96
ROW_FLOATS = IMAGE_FLOATS * 4 + 12


class Cancelled(Exception):
    pass


def decode_png(value, target):
    if not value.startswith('data:image/png;base64,'):
        raise ValueError('Only base64-encoded PNG images are accepted')
    if len(value) > 24 * 1024 * 1024:
        raise ValueError('PNG file exceeds the 18 MiB limit')
    try:
        data = base64.b64decode(value.split(',', 1)[1], validate=True)
    except (ValueError, binascii.Error) as e:
        raise ValueError('Invalid PNG encoding') from e
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG signature')
    with Image.open(io.BytesIO(data)) as im:
        if im.format != 'PNG' or getattr(im, 'n_frames', 1) != 1:
            raise ValueError('A single-frame PNG is required')
        if not (1 <= im.width <= 4096 and 1 <= im.height <= 32768 and im.width * im.height <= 32_000_000):
            raise ValueError('Image exceeds limits: 4096 px width, 32768 px height, 32 million pixels')
        im.verify()
    atomic(target, data)


def node_command(script):
    executable = os.environ.get('RENDERGUARD_NODE') or shutil.which('node')
    if not executable:
        raise RuntimeError('Node.js 22 or later is required; add node to PATH')
    return [executable, '--import', 'tsx', str(ROOT / script)]


def command(args, cwd, cancel, timeout=180, stage_callback=None):
    start = time.monotonic()
    out = cwd / ('process-' + uid() + '.log')
    with out.open('w+') as stream:
        proc = subprocess.Popen(args, cwd=ROOT, stdout=stream, stderr=stream, env=os.environ.copy())
        try:
            while proc.poll() is None:
                if cancel.is_set():
                    proc.terminate()
                    raise Cancelled('Job cancelled; completed artifacts were retained')
                if time.monotonic() - start > timeout:
                    proc.terminate()
                    raise TimeoutError('The current processing stage exceeded its time limit')
                if stage_callback:
                    stage_callback()
                time.sleep(0.1)
            if proc.returncode:
                stream.seek(0)
                # Error detail stays local; reports expose the failure stage and useful final line.
                lines = stream.read().strip().splitlines()
                raise RuntimeError(('Processing command failed: ' + (lines[-1] if lines else str(proc.returncode)))[:500])
        finally:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)


def model_assets(store):
    active = store.setting('activeModel')
    folder = store.root / 'models' / active if active else ROOT / 'web/public/models'
    manifest = json.loads((folder / 'manifest.json').read_text())
    model = folder / 'model.onnx'
    expected = manifest.get('modelSha256') or manifest.get('sha256') or manifest.get('onnx', {}).get('sha256')
    actual = digest(model)
    if expected != actual:
        raise ValueError('Model checksum does not match its manifest')
    calibration = json.loads((folder / 'calibration.json').read_text())
    if calibration.get('modelSha256') != actual or calibration.get('preprocessVersion') != manifest.get('preprocessVersion'):
        raise ValueError('Calibration is invalid for this model or preprocessing version')
    return folder, manifest, calibration


def run_analysis(store, job, config, cancel):
    job_id = job['id']
    run_id = uid()
    folder = store.root / 'runs' / run_id
    folder.mkdir(parents=True)
    started = time.monotonic()
    evidence = {'schemaVersion': '1.0', 'id': run_id, 'projectId': job['projectId'], 'createdAt': now(), 'execution': 'error', 'environment': 'unverified', 'analysis': {'candidates': []}, 'predictions': [], 'contracts': [], 'masks': config.get('masks', []), 'model': {}, 'beforeUrl': f'/api/runs/{run_id}/images/before', 'afterUrl': f'/api/runs/{run_id}/images/after'}
    phase = 'inputs'
    try:
        store.update_job(job_id, status='running', stage=phase, total=2, completed=0)
        if job['kind'] == 'import':
            decode_png(config['before'], folder / 'before.png')
            store.update_job(job_id, completed=1)
            decode_png(config['after'], folder / 'after.png')
        else:
            phase = 'capture'
            store.update_job(job_id, stage=phase, total=2, completed=0)
            capture_config = {**config, 'output': str(folder), 'outputDir': str(folder)}
            capture_config['deniedOrigins'] = ['http://localhost:8765', 'http://127.0.0.1:8765', 'http://[::1]:8765']
            capture_config['deniedPorts'] = [int(os.environ.get('RENDERGUARD_SERVICE_PORT', '8765'))]
            write_json(folder / 'capture-config.json', capture_config)
            command(node_command('capture/cli.ts') + [str(folder / 'capture-config.json')], folder, cancel, timeout=150)
            captured = json.loads((folder / 'manifest.json').read_text())
            evidence['capture'] = captured
            evidence['contracts'] = captured.get('contracts', [])
            evidence['environment'] = 'verified'
            if captured.get('execution') == 'incomparable':
                evidence['execution'] = 'incomparable'
                raise ValueError('Capture conditions are incomparable')
        store.update_job(job_id, completed=2)
        evidence['inputHashes'] = {side: digest(folder / f'{side}.png') for side in ('before', 'after')}
        if cancel.is_set():
            raise Cancelled()
        phase = 'candidates'
        store.update_job(job_id, stage=phase, completed=0, total=1)
        specification = {'before': str(folder / 'before.png'), 'after': str(folder / 'after.png'), 'masks': config.get('masks', []), 'output': str(folder / 'tensors'), 'saveImages': True}
        write_json(folder / 'tensor-config.json', specification)
        command(node_command('capture/tensors.ts') + [str(folder / 'tensor-config.json')], folder, cancel, timeout=180)
        metadata = json.loads((folder / 'tensors.json').read_text())
        for side in ('analysis-before', 'analysis-after', 'diff'):
            generated = folder / f'tensors-{side}.png'
            if generated.is_file():
                os.replace(generated, folder / f'{side}.png')
        analysis = metadata.get('analysis', metadata)
        analysis.pop('tensor', None)
        evidence['analysis'] = analysis
        store.update_job(job_id, completed=1)
        phase = 'model_load'
        store.update_job(job_id, stage=phase, completed=0, total=1)
        _, manifest, calibration = model_assets(store)
        model_folder, _, _ = model_assets(store)
        evidence['model'] = {'version': manifest['version'], 'sha256': digest(model_folder / 'model.onnx'), 'preprocessVersion': manifest['preprocessVersion']}
        if analysis.get('version') and analysis['version'] != manifest['preprocessVersion']:
            raise ValueError('Candidate/preprocessing version does not match the model')
        evidence['calibration'] = calibration
        evidence['cacheKey'] = __import__('hashlib').sha256(json.dumps({'inputs': evidence['inputHashes'], 'masks': evidence['masks'], 'capture': evidence.get('capture'), 'candidateVersion': analysis.get('version'), 'model': evidence['model']}, sort_keys=True).encode()).hexdigest()
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        session = ort.InferenceSession(str(model_folder / 'model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
        store.update_job(job_id, completed=1)
        candidates = analysis['candidates']
        phase = 'inference'
        store.update_job(job_id, stage=phase, completed=0, total=len(candidates))
        if candidates:
            tensors = np.memmap(folder / 'tensors.f32', dtype='<f4', mode='r', shape=(len(candidates), ROW_FLOATS))
            input_names = ['local_before', 'local_after', 'context_before', 'context_after']
            for index in range(0, len(candidates), 4):
                if cancel.is_set():
                    raise Cancelled()
                batch = tensors[index:index + 4]
                feeds = {name: np.ascontiguousarray(batch[:, n * IMAGE_FLOATS:(n + 1) * IMAGE_FLOATS].reshape(-1, 3, 96, 96)) for n, name in enumerate(input_names)}
                feeds['geometry'] = np.ascontiguousarray(batch[:, 4 * IMAGE_FLOATS:])
                logits = session.run(None, feeds)[0]
                for j, row in enumerate(logits):
                    scores = []
                    for k, value in enumerate(row):
                        cal = calibration['classes'][k]
                        z = float(value) / float(cal.get('temperature', 1)) + float(cal.get('bias', 0)) if cal['status'] == 'calibrated' else float(value)
                        scores.append(float(1 / (1 + np.exp(-np.clip(z, -60, 60)))))
                    evidence['predictions'].append({'candidateId': candidates[index + j]['id'], 'logits': row.tolist(), 'scores': scores})
                store.update_job(job_id, completed=min(index + 4, len(candidates)))
            del tensors
        if cancel.is_set():
            raise Cancelled()
        evidence['execution'] = 'complete'
        evidence['timing'] = {'totalSeconds': time.monotonic() - started, 'includesCandidatesAndModelLoad': True}
        write_json(folder / 'evidence.json', evidence)
        store.save_run(evidence)
        store.update_job(job_id, status='complete', stage='complete', runId=run_id, completed=len(candidates), total=len(candidates))
    except Exception as error:
        if isinstance(error, Cancelled):
            evidence['execution'] = 'cancelled'
            state = 'cancelled'
        else:
            state = 'error'
        evidence['error'] = {'stage': phase, 'message': str(error)[:500] or 'Cancelled'}
        write_json(folder / 'evidence.json', evidence)
        store.save_run(evidence)
        store.update_job(job_id, status=state, stage=phase, error=evidence['error']['message'], runId=run_id)
