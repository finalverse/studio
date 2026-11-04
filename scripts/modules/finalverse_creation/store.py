# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded durable proposals; host-only approval, interruption without auto replay."""
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

from .protocol import CreationError, canonical, digest, parse, validate

TERMINAL = {'Completed', 'Cancelled', 'Failed', 'Interrupted', 'Rejected'}


class Store:
    def __init__(self, root):
        self.root = Path(root).absolute()
        if any(p.is_symlink() for p in [self.root, *self.root.parents]):
            raise CreationError("Workspace may not traverse symlinks")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = self.root/'studio-workspace.json'
        if not marker.exists():
            if list(self.root.iterdir()):
                raise CreationError("Choose a new or existing Studio workspace")
            marker.write_text(canonical({'schema_version': 'finalverse.studio-workspace/v1'}))
        if marker.is_symlink() or parse(marker.read_text()) != {'schema_version': 'finalverse.studio-workspace/v1'}:
            raise CreationError("Invalid workspace marker")
        os.chmod(self.root, 0o700)
        dbpath = self.root/'creation.sqlite'
        if dbpath.is_symlink():
            raise CreationError("Symlink database refused")
        self.db = sqlite3.connect(dbpath, timeout=.1)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request TEXT UNIQUE NOT NULL,
          document TEXT NOT NULL);''')
        os.chmod(dbpath, 0o600)

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def get(self, job_id):
        row = self.db.execute('SELECT document FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise CreationError("Unknown job")
        return parse(row[0], 4*1024*1024)

    def jobs(self):
        return [parse(r[0], 4*1024*1024) for r in self.db.execute('SELECT document FROM jobs ORDER BY rowid DESC LIMIT 256')]

    def _write(self, job):
        self.db.execute('UPDATE jobs SET document=? WHERE id=?', (canonical(job), job['id']))

    def snapshot(self, value=None):
        if value is not None:
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)', ('snapshot', canonical(value)))
        row = self.db.execute('SELECT value FROM kv WHERE key=?', ('snapshot',)).fetchone()
        return parse(row[0], 4*1024*1024) if row else None

    def submit(self, plan, scene_id, revision, request_id, source='mcp', model_receipt=None):
        validate(plan)
        uuid.UUID(request_id)
        uuid.UUID(scene_id)
        if not isinstance(revision, str) or len(revision) != 64:
            raise CreationError("Invalid scene revision")
        envelope = {'plan': plan, 'scene_id': scene_id, 'base_revision': revision}
        with self.transaction():
            row = self.db.execute('SELECT document FROM jobs WHERE request=?', (request_id,)).fetchone()
            if row:
                existing = parse(row[0], 4*1024*1024)
                if existing['digest'] != digest(envelope):
                    raise CreationError("Request ID reused with different input")
                return existing
            if self.db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 256:
                raise CreationError("Workspace job limit reached; archive locally before continuing")
            job = {'id': str(uuid.uuid4()), 'request_id': request_id, **envelope,
                   'digest': digest(envelope), 'source': source, 'model_receipt': model_receipt,
                   'state': 'Proposed', 'step': 0, 'created_at': time.time(), 'events': [],
                   'aliases': {}, 'results': [], 'error': None, 'approval': None}
            self.event(job, 'Proposed')
            self.db.execute('INSERT INTO jobs VALUES(?,?,?)', (job['id'], request_id, canonical(job)))
            return job

    @staticmethod
    def event(job, name, detail=None):
        job['events'].append({'event': name, 'time': time.time(), 'detail': detail})

    def update(self, job_id, expected, **changes):
        with self.transaction():
            job = self.get(job_id)
            if job['state'] not in expected:
                raise CreationError("Job state changed")
            job.update(changes)
            if 'state' in changes:
                self.event(job, changes['state'])
            self._write(job)
            return job

    def cancel(self, job_id):
        job = self.get(job_id)
        if job['state'] in TERMINAL:
            return job
        return self.update(job_id, {'Proposed', 'Approved', 'Applying', 'Rendering'}, state='Cancelled', approval=None)

    def directory(self, job_id):
        uuid.UUID(job_id)
        path = self.root/'jobs'/job_id
        if path.is_symlink() or path.parent.is_symlink():
            raise CreationError("Symlink job output refused")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path


class HostAuthority:
    """Not exposed as an MCP tool. Approval binds exact plan, scene and host lifetime."""
    def __init__(self, store):
        self.store = store
        self.lock = (store.root/'host.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.lock.close()
            raise CreationError("Another Studio host owns this workspace") from error
        self.key = secrets.token_bytes(32)
        self.session = str(uuid.uuid4())
        for job in store.jobs():
            if job['state'] in {'Applying', 'Rendering'}:
                store.update(job['id'], {job['state']}, state='Interrupted', approval=None,
                             error='Host restarted; uncertain work is never automatically replayed')
            elif job['state'] == 'Approved':
                store.update(job['id'], {'Approved'}, state='Proposed', approval=None)

    def _signature(self, job, expires):
        content = canonical([job['id'], job['digest'], self.session, expires]).encode()
        return hmac.new(self.key, content, hashlib.sha256).hexdigest()

    def approve(self, job_id, snapshot):
        job = self.store.get(job_id)
        if snapshot['scene_id'] != job['scene_id'] or snapshot['revision'] != job['base_revision']:
            raise CreationError("Scene changed; inspect and propose again")
        envelope = {k: job[k] for k in ('plan', 'scene_id', 'base_revision')}
        if digest(envelope) != job['digest']:
            raise CreationError("Proposal digest changed")
        expires = time.time() + 900
        return self.store.update(job_id, {'Proposed'}, state='Approved',
            approval={'session': self.session, 'expires': expires, 'signature': self._signature(job, expires)})

    def verify(self, job):
        approval = job.get('approval') or {}
        validate(job['plan'])
        envelope = {k: job[k] for k in ('plan', 'scene_id', 'base_revision')}
        if digest(envelope) != job['digest'] or approval.get('session') != self.session:
            raise CreationError("Missing host approval")
        expires = approval.get('expires', 0)
        if expires < time.time() or not hmac.compare_digest(approval.get('signature', ''), self._signature(job, expires)):
            raise CreationError("Expired or invalid host approval")

    def close(self):
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()
