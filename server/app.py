"""Loopback-only application with explicit write authorization."""
from __future__ import annotations
import concurrent.futures
import json
import os
import secrets
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .analysis import ROOT, LABELS, Cancelled, command, model_assets, run_analysis
from .reports import report_html, report_json
from .store import Store, digest, uid, write_json


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class ProjectInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)

class ImportInput(StrictModel):
    before: str
    after: str
    masks: list[dict] = Field(default_factory=list, max_length=64)
    name: str = Field(default='', max_length=120)

class CaptureInput(StrictModel):
    beforeUrl: str = Field(max_length=2048)
    afterUrl: str = Field(max_length=2048)
    viewport: dict = Field(default_factory=lambda: {'width': 1280, 'height': 800})
    deviceScaleFactor: float = 1
    readySelector: str | None = Field(default=None, max_length=500)
    masks: list[dict] = Field(default_factory=list, max_length=64)
    contracts: list[dict] = Field(default_factory=list, max_length=64)
    state: dict = Field(default_factory=dict)
    timeoutMs: int = Field(default=30000, ge=1000, le=60000)

class ReviewInput(StrictModel):
    candidateId: str
    decision: str
    observation: dict[str, bool | None] | None = None

class BaselineInput(StrictModel):
    runId: str
    side: str = 'after'

class TrainInput(StrictModel):
    projectId: str

class ActivateInput(StrictModel):
    version: str


def create_app(workspace: Path | None = None):
    store = Store(workspace or Path(os.environ.get('RENDERGUARD_WORKSPACE', ROOT / 'workspace')))
    app = FastAPI(title='RenderGuard', docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.token = secrets.token_urlsafe(32)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='review-worker')
    cancels: dict[str, threading.Event] = {}
    app.state.cancels = cancels

    @app.middleware('http')
    async def authorize(request: Request, call_next):
        host = request.headers.get('host', '')
        try:
            hostname = urlsplit('http://' + host).hostname
        except ValueError:
            hostname = None
        if hostname not in ('localhost', '127.0.0.1', '::1'):
            return JSONResponse({'detail': 'Host not allowed'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != f'{request.url.scheme}://{host}':
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Cross-site requests are not allowed'}, status_code=403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if not secrets.compare_digest(request.headers.get('x-renderguard-token', ''), app.state.token):
                return JSONResponse({'detail': 'A valid local session token is required'}, status_code=403)
            length = request.headers.get('content-length')
            if length and (not length.isdecimal() or int(length) > 50 * 1024 * 1024):
                return JSONResponse({'detail': 'Request body exceeds 50 MiB'}, status_code=413)
            # Count streamed bodies too; a missing Content-Length cannot bypass limits.
            chunks = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 50 * 1024 * 1024:
                    return JSONResponse({'detail': 'Request body exceeds 50 MiB'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api') else 'no-cache'
        if request.url.path.startswith('/api'):
            response.headers['Content-Security-Policy'] = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; frame-ancestors 'none'"
        return response

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({'detail': str(error)}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({'detail': str(error)}, status_code=400)

    @app.get('/api/session')
    def session():
        try:
            _, manifest, _ = model_assets(store)
            model = {'available': True, 'version': manifest['version']}
        except (OSError, ValueError, KeyError):
            model = {'available': False, 'error': 'A valid model and calibration manifest are required'}
        return {'token': app.state.token, 'mode': 'local', 'model': model}

    @app.get('/api/projects')
    def projects():
        return store.projects()

    @app.post('/api/projects')
    def create_project(body: ProjectInput):
        return store.create_project(body.name.strip() or 'Untitled project')

    @app.get('/api/projects/{project}')
    def get_project(project: str):
        return store.project(project)

    def submit(project, kind, config):
        store.project(project)
        active = sum(1 for event in cancels.values() if not event.is_set())
        if active >= 4:
            raise HTTPException(429, 'At most four jobs may be queued; finish or cancel an existing job')
        job = store.create_job(project, kind)
        cancel = threading.Event()
        cancels[job['id']] = cancel
        def execute():
            try:
                run_analysis(store, job, config, cancel)
            finally:
                cancel.set()
        executor.submit(execute)
        return job

    @app.post('/api/projects/{project}/import')
    def import_images(project: str, body: ImportInput):
        return submit(project, 'import', body.model_dump())

    @app.post('/api/projects/{project}/capture')
    def capture(project: str, body: CaptureInput):
        config = body.model_dump(exclude_none=True)
        return submit(project, 'capture', config)

    @app.get('/api/jobs/{job}')
    def get_job(job: str):
        return store.job(job)

    @app.post('/api/jobs/{job}/cancel')
    def cancel_job(job: str):
        item = store.job(job)
        if item['status'] in ('queued', 'running'):
            event = cancels.get(job)
            if event:
                event.set()
            return store.update_job(job, cancelRequested=True)
        return item

    @app.get('/api/runs/{run}')
    def get_run(run: str):
        return store.run(run)

    @app.get('/api/runs/{run}/images/{side}')
    def get_image(run: str, side: str):
        store.run(run)
        if side not in ('before', 'after', 'diff', 'analysis-before', 'analysis-after'):
            raise HTTPException(404, 'Image not found')
        file = store.root / 'runs' / run / f'{side}.png'
        if not file.is_file():
            raise HTTPException(404, 'Image not produced')
        return FileResponse(file, media_type='image/png')

    @app.post('/api/runs/{run}/reviews')
    def review(run: str, body: ReviewInput):
        if body.decision not in ('confirm_defect', 'intentional_change', 'uncertain', 'unreviewed'):
            raise ValueError('Unknown review decision')
        if body.observation is not None and any(k not in LABELS for k in body.observation):
            raise ValueError('Unknown observation label')
        return store.review(run, body.candidateId, body.decision, body.observation)

    @app.post('/api/runs/{run}/undo')
    def undo_review(run: str):
        return store.review(run, None, None, undo=True)

    @app.post('/api/projects/{project}/baseline')
    def baseline(project: str, body: BaselineInput):
        if body.side not in ('before', 'after'):
            raise ValueError('Side must be before or after')
        return store.baseline(project, body.runId, body.side)

    @app.post('/api/projects/{project}/baseline/undo')
    def undo_baseline(project: str):
        return store.baseline(project, undo=True)

    @app.get('/api/runs/{run}/export')
    def export(run: str, format: str = 'json'):
        evidence = store.run(run)
        folder = store.root / 'runs' / run
        if format == 'html':
            return HTMLResponse(report_html(evidence, folder), headers={'Content-Disposition': 'attachment; filename="renderguard-report.html"'})
        if format != 'json':
            raise ValueError('Export format must be json or html')
        return JSONResponse(report_json(evidence, folder), headers={'Content-Disposition': 'attachment; filename="renderguard-report.json"'})

    def feedback(project):
        info = store.project(project)
        pages = []
        for item in info['runs']:
            run = store.run(item['id'])
            labels = [{'candidateId': key, 'observations': value['observation']} for key, value in run['decisions'].items() if value.get('observation') and any(v is not None for v in value['observation'].values())]
            if labels:
                pages.append({'runId': run['id'], 'inputHashes': run.get('inputHashes'), 'model': run['model'], 'labels': labels, 'analysis': run['analysis'], 'images': report_json(run, store.root / 'runs' / run['id'])['images']})
        return {'schemaVersion': '1.0', 'projectId': project, 'labels': LABELS, 'pagePairs': pages, 'note': 'Only explicitly corrected observation labels are supervision. Decisions and missing feedback are never negative labels.'}

    @app.get('/api/projects/{project}/feedback')
    def export_feedback(project: str):
        return JSONResponse(feedback(project), headers={'Content-Disposition': 'attachment; filename="renderguard-feedback.json"'})

    @app.post('/api/train')
    def train(body: TrainInput):
        data = feedback(body.projectId)
        if not data['pagePairs']:
            raise ValueError('Correct at least one observation before explicit retraining')
        job = store.create_job(body.projectId, 'train')
        folder = store.root / 'training' / job['id']
        folder.mkdir(parents=True)
        write_json(folder / 'feedback.json', data)
        cancel = threading.Event()
        cancels[job['id']] = cancel
        def execute():
            try:
                store.update_job(job['id'], status='running', stage='training', completed=0, total=1)
                command([sys.executable, '-m', 'ml.feedback', '--feedback', str(folder / 'feedback.json'), '--output', str(folder / 'candidate')], folder, cancel, timeout=3600)
                candidate = folder / 'candidate'
                manifest = json.loads((candidate / 'manifest.json').read_text())
                version = manifest['version']
                if not version or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_' for ch in version):
                    raise ValueError('Invalid candidate model version')
                destination = store.root / 'models' / version
                if destination.exists():
                    raise ValueError('Candidate model version already exists')
                if digest(candidate / 'model.onnx') != manifest.get('modelSha256'):
                    raise ValueError('Candidate model checksum mismatch')
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.rename(candidate, destination)
                store.update_job(job['id'], status='complete', stage='independent_evaluation_complete', completed=1, total=1, modelVersion=version)
            except Exception as error:
                store.update_job(job['id'], status='cancelled' if isinstance(error, Cancelled) else 'error', error=str(error)[:500])
            finally:
                cancel.set()
        executor.submit(execute)
        return job

    @app.get('/api/models')
    def models():
        entries = []
        for folder in [ROOT / 'web/public/models', *sorted((store.root / 'models').glob('*'))]:
            if (folder / 'manifest.json').is_file():
                value = json.loads((folder / 'manifest.json').read_text())
                entries.append(value)
        return {'active': store.setting('activeModel') or (entries[0]['version'] if entries else None), 'models': entries}

    @app.post('/api/models/activate')
    def activate(body: ActivateInput):
        available = models()['models']
        if not any(v['version'] == body.version for v in available):
            raise ValueError('Unknown model version')
        previous = store.setting('activeModel')
        shipped = json.loads((ROOT / 'web/public/models/manifest.json').read_text())['version']
        store.set_setting('activeModel', None if shipped == body.version else body.version)
        try:
            model_assets(store)
        except Exception:
            store.set_setting('activeModel', previous)
            raise ValueError('Model validation failed; previous model remains active')
        history = store.setting('modelHistory', [])
        store.set_setting('modelHistory', history + [{'old': previous or shipped, 'new': body.version, 'time': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}])
        return models()

    @app.get('/{path:path}')
    def frontend(path: str):
        if path.startswith('api/'):
            raise HTTPException(404, 'API endpoint not found')
        # The same production build works under both localhost and Pages.
        relative = path.removeprefix('renderguard/')
        dist = (ROOT / 'dist').resolve()
        file = (dist / relative).resolve()
        if not file.is_relative_to(dist):
            raise HTTPException(404, 'File not found')
        if file.is_file():
            return FileResponse(file)
        if relative == '' or '.' not in Path(relative).name:
            if (dist / 'index.html').is_file():
                return FileResponse(dist / 'index.html')
        raise HTTPException(404, 'Build the frontend before starting the service')

    return app


def main():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description='Start the local RenderGuard workbench')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--workspace', type=Path)
    args = parser.parse_args()
    os.environ['RENDERGUARD_SERVICE_PORT'] = str(args.port)
    uvicorn.run(create_app(args.workspace), host='127.0.0.1', port=args.port, access_log=False)

if __name__ == '__main__':
    main()
