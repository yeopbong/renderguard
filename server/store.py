"""Transactional metadata and append-only evidence event storage."""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic(path: Path, value: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path, value):
    atomic(Path(path), json.dumps(value, ensure_ascii=True, allow_nan=False).encode())


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.database = root / 'reviews.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, project TEXT, kind TEXT NOT NULL, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, project TEXT NOT NULL, evidence TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, project TEXT NOT NULL, run TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')
            for row in db.execute('SELECT id,state FROM jobs').fetchall():
                state = json.loads(row['state'])
                if state['status'] in ('queued', 'running'):
                    state.update(status='interrupted', stage='retry_required', error='Service stopped before this job completed. Completed files are retained; retry explicitly.')
                    db.execute('UPDATE jobs SET state=? WHERE id=?', (json.dumps(state), row['id']))

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def projects(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,name,created AS createdAt FROM projects ORDER BY created DESC')]

    def create_project(self, name):
        item = {'id': uid(), 'name': name, 'createdAt': now()}
        with self.connect() as db:
            db.execute('INSERT INTO projects VALUES(?,?,?)', tuple(item.values()))
        return item

    def project(self, project):
        with self.connect() as db:
            row = db.execute('SELECT id,name,created AS createdAt FROM projects WHERE id=?', (project,)).fetchone()
            if not row:
                raise KeyError('Project not found')
            result = dict(row)
            result['runs'] = [dict(r) for r in db.execute('SELECT id,created AS createdAt FROM runs WHERE project=? ORDER BY created DESC', (project,))]
            events = self.events(db, project=project)
            result['baselineHistory'] = [e for e in events if e['kind'] == 'baseline']
            result['baseline'] = result['baselineHistory'][-1]['new'] if result['baselineHistory'] else None
            return result

    def create_job(self, project, kind):
        item = {'id': uid(), 'projectId': project, 'kind': kind, 'status': 'queued', 'stage': 'queued', 'completed': 0, 'total': 0, 'createdAt': now()}
        with self.connect() as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?)', (item['id'], project, kind, json.dumps(item)))
        return item

    def job(self, id):
        with self.connect() as db:
            row = db.execute('SELECT state FROM jobs WHERE id=?', (id,)).fetchone()
            if not row:
                raise KeyError('Job not found')
            return json.loads(row['state'])

    def update_job(self, id, **updates):
        with self.connect() as db:
            row = db.execute('SELECT state FROM jobs WHERE id=?', (id,)).fetchone()
            state = json.loads(row['state'])
            state.update(updates, updatedAt=now())
            db.execute('UPDATE jobs SET state=? WHERE id=?', (json.dumps(state), id))
        return state

    def save_run(self, evidence):
        with self.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?,?,?)', (evidence['id'], evidence['projectId'], json.dumps(evidence), evidence['createdAt']))

    @staticmethod
    def events(db, project=None, run=None):
        field, value = ('run', run) if run is not None else ('project', project)
        rows = db.execute(f'SELECT * FROM events WHERE {field}=? ORDER BY sequence', (value,))
        return [{'id': r['id'], 'sequence': r['sequence'], 'kind': r['kind'], 'createdAt': r['created'], **json.loads(r['payload'])} for r in rows]

    def run(self, id):
        from .gate import evaluate_gate
        with self.connect() as db:
            row = db.execute('SELECT evidence FROM runs WHERE id=?', (id,)).fetchone()
            if not row:
                raise KeyError('Run not found')
            result = json.loads(row['evidence'])
            result['events'] = self.events(db, run=id)
        result['decisions'] = {}
        for e in result['events']:
            if e['kind'] == 'review':
                result['decisions'][e['candidateId']] = e['new']
        result['gate'] = evaluate_gate(result)
        return result

    def review(self, run_id, candidate, decision, observation=None, undo=False):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT evidence,project FROM runs WHERE id=?', (run_id,)).fetchone()
            if not row:
                raise KeyError('Run not found')
            evidence = json.loads(row['evidence'])
            ids = {c['id'] for c in evidence.get('analysis', {}).get('candidates', [])}
            ids.update(c['id'] for c in evidence.get('contracts', []))
            events = self.events(db, run=run_id)
            if undo:
                reverted = {e.get('undoOf') for e in events}
                original = next((e for e in reversed(events) if e['kind'] == 'review' and not e.get('undoOf') and e['id'] not in reverted), None)
                if not original:
                    raise ValueError('No review to undo')
                candidate = original['candidateId']
                new = original['old']
            else:
                original = None
                if candidate not in ids:
                    raise ValueError('Candidate does not belong to this immutable run')
                new = {'decision': decision}
                if observation is not None:
                    new['observation'] = observation
            old = next((e['new'] for e in reversed(events) if e['kind'] == 'review' and e['candidateId'] == candidate), {'decision': 'unreviewed'})
            if not undo and observation is None and 'observation' in old:
                new['observation'] = old['observation']
            payload = {'candidateId': candidate, 'old': old, 'new': new, 'runId': run_id, 'modelVersion': evidence.get('model', {}).get('version'), 'inputHashes': evidence.get('inputHashes')}
            if original:
                payload['undoOf'] = original['id']
            db.execute('INSERT INTO events(id,project,run,kind,payload,created) VALUES(?,?,?,?,?,?)', (uid(), row['project'], run_id, 'review', json.dumps(payload), now()))
        return self.run(run_id)

    def baseline(self, project, run_id=None, side=None, undo=False):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT id FROM projects WHERE id=?', (project,)).fetchone():
                raise KeyError('Project not found')
            events = [e for e in self.events(db, project=project) if e['kind'] == 'baseline']
            old = events[-1]['new'] if events else None
            payload = {'old': old}
            if undo:
                reverted = {e.get('undoOf') for e in events}
                e = next((e for e in reversed(events) if not e.get('undoOf') and e['id'] not in reverted), None)
                if not e:
                    raise ValueError('No baseline update to undo')
                payload.update(new=e['old'], undoOf=e['id'])
            else:
                row = db.execute('SELECT evidence FROM runs WHERE id=? AND project=?', (run_id, project)).fetchone()
                if not row:
                    raise ValueError('Run does not belong to this project')
                evidence = json.loads(row['evidence'])
                if evidence['execution'] != 'complete':
                    raise ValueError('Only a complete run can supply a baseline')
                payload['new'] = {'runId': run_id, 'side': side, 'sha256': evidence['inputHashes'][side]}
            db.execute('INSERT INTO events(id,project,run,kind,payload,created) VALUES(?,?,?,?,?,?)', (uid(), project, run_id, 'baseline', json.dumps(payload), now()))
        return self.project(project)

    def save_baseline_image(self, project, image_id, sha256):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT id FROM projects WHERE id=?', (project,)).fetchone():
                raise KeyError('Project not found')
            events = [e for e in self.events(db, project=project) if e['kind'] == 'baseline']
            old = events[-1]['new'] if events else None
            payload = {'old': old, 'new': {'imageId': image_id, 'sha256': sha256, 'environment': 'unverified', 'side': 'before'}}
            db.execute('INSERT INTO events(id,project,run,kind,payload,created) VALUES(?,?,?,?,?,?)', (uid(), project, None, 'baseline', json.dumps(payload), now()))
        return self.project(project)

    def setting(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return json.loads(row['value']) if row else default

    def set_setting(self, key, value):
        with self.connect() as db:
            db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))
