# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Main-thread authoring scheduler with explicit approval and bounded child jobs."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

import bpy

from . import engine
from .protocol import CreationError, canonical, parse
from .providers import default_registry, registry
from .store import HostAuthority, Store, TERMINAL


def app_path():
    return Path(bpy.app.binary_path).parents[2]


def python_path():
    return app_path()/'Contents/Resources/5.4/python/bin/python3.13'


def clean_env(work):
    return {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'TMPDIR': str(work), 'PYTHONDONTWRITEBYTECODE': '1'}


def stop(process):
    # A failed supervisor may already have exited while its child remains alive.
    if process:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process:
        process.wait(timeout=2)


class Host:
    def __init__(self, directory):
        self.store = Store(directory)
        self.authority = HostAuthority(self.store)
        self.config = self.store.root/'providers.json'; default_registry(self.config)
        self.providers = registry(self.config)
        self.inference = None; self.render = None; self.active = None
        self.expected_revision = None; self.last_snapshot = 0
        self.message = 'Session ready; proposals require approval'
        self.model_names = []; self.model_result = None
        self.refresh()

    def refresh(self):
        index = engine.snapshot(bpy.context.scene)
        self.store.snapshot(index); self.last_snapshot = time.monotonic()
        return index

    def infer(self, provider_id, mode, model='', prompt=''):
        if self.inference or self.active:
            raise CreationError('Finish or cancel the active task first')
        self.providers = registry(self.config)
        p = self.providers[provider_id]
        work = self.store.root/'inference'/str(uuid.uuid4()); work.mkdir(parents=True, mode=0o700)
        snapshot = self.refresh()
        request = {'provider': provider_id, 'mode': mode, 'model': model, 'prompt': prompt, 'snapshot': snapshot}
        (work/'input.json').write_text(canonical(request))
        env = clean_env(work)
        if p['token_env'] and p['token_env'] in os.environ:
            env[p['token_env']] = os.environ[p['token_env']]
        log = (work/'helper.log').open('w')
        process = subprocess.Popen([str(python_path()), '-I', str(Path(__file__).with_name('provider_entry.py')),
            str(self.config), str(work/'input.json'), str(work/'output.json')],
            env=env, stdout=log, stderr=log, start_new_session=True)
        log.close()
        self.inference = {'process': process, 'work': work, 'request': request, 'started': time.monotonic()}
        self.message = 'Testing provider…' if mode == 'models' else 'Planning… Studio remains responsive'

    def approve(self, job_id):
        if self.active or self.inference:
            raise CreationError('Another task is active')
        job = self.store.get(job_id)
        engine.preflight(bpy.context.scene, job['plan'])
        self.authority.approve(job_id, self.refresh())
        self.message = 'Approved exact proposal; execution queued'

    def cancel(self, job_id=None):
        if self.inference:
            stop(self.inference['process'])
            (self.inference['work']/'cancelled.json').write_text(canonical({'state': 'Cancelled', 'time': time.time()}))
            self.inference = None
        if job_id:
            self.store.cancel(job_id)
        if self.active and (job_id is None or self.active == job_id):
            self.store.cancel(self.active)
            self._stop_render(); self.active = None
        self.message = 'Cancelled; completed authoring steps remain inspectable'

    def _stop_render(self):
        if self.render:
            stop(self.render['process']); self.render = None

    def _checkpoint(self, job):
        self._quota(128*1024*1024)
        path = self.store.directory(job['id'])/f"checkpoint-{job['step']:03d}.blend"
        if path.exists():
            raise CreationError('Checkpoint exists; uncertain step will not replay')
        bpy.ops.wm.save_as_mainfile(filepath=str(path), copy=True)
        if path.stat().st_size > 128*1024*1024:
            raise CreationError('Checkpoint exceeds 128 MiB')
        return path

    def _quota(self, reserve=0):
        used = sum(p.stat().st_size for p in self.store.root.rglob('*') if p.is_file())
        if used + reserve > 512*1024*1024:
            raise CreationError('Workspace storage budget reached; archive completed jobs locally')

    def _begin(self, job):
        self.authority.verify(job)
        index = self.refresh()
        if index['scene_id'] != job['scene_id'] or index['revision'] != job['base_revision']:
            raise CreationError('Scene changed after proposal')
        engine.preflight(bpy.context.scene, job['plan'])
        self._quota(256*1024*1024)
        self._checkpoint(job)
        self.expected_revision = index['revision']
        self.store.update(job['id'], {'Approved'}, state='Applying')
        self.active = job['id']

    def _advance(self, job, result):
        index = self.refresh(); self.expected_revision = index['revision']
        updated = self.store.update(job['id'], {'Applying', 'Rendering'}, state='Applying',
            step=job['step']+1, aliases=job['aliases'], results=job['results']+[result])
        self._checkpoint(updated)

    def tick(self):
        """At most one bounded scene operation per tick; no network wait here."""
        if self.inference:
            pending = self.inference; process = pending['process']
            if time.monotonic()-pending['started'] > 122:
                stop(process); self.inference = None; self.message = 'Provider timed out; no fallback used'
            elif process.poll() is not None:
                self.inference = None
                output = pending['work']/'output.json'
                result = parse(output.read_text(), 128*1024) if output.exists() else {'ok': False, 'error': 'helper_failed'}
                self.model_result = result
                if result.get('ok') and 'models' in result:
                    self.model_names = result['models']; self.message = f"Connected: {len(self.model_names)} models"
                elif result.get('ok') and 'plan' in result:
                    baseline = pending['request']['snapshot']
                    job = self.store.submit(result['plan'], baseline['scene_id'], baseline['revision'], str(uuid.uuid4()),
                                            source='model', model_receipt=result['receipt'])
                    self.message = 'Plan ready for review: ' + job['id']; self.refresh()
                else:
                    self.message = 'Inference failed: ' + result.get('error', 'unknown') + '; no fallback used'
            return
        if not self.active:
            for job in reversed(self.store.jobs()):
                if job['state'] == 'Approved':
                    try:
                        self._begin(job)
                    except Exception as error:
                        self.store.update(job['id'], {'Approved'}, state='Failed', error=str(error))
                        self.message = str(error)
                    return
            if time.monotonic()-self.last_snapshot > 2:
                self.refresh()
            return
        job = self.store.get(self.active)
        if job['state'] in TERMINAL:
            self._stop_render(); self.active = None; return
        try:
            self.authority.verify(job)
            if self.refresh()['revision'] != self.expected_revision:
                raise CreationError('Concurrent scene edit detected; remaining steps stopped')
            if self.render:
                process = self.render['process']
                if time.monotonic()-self.render['started'] > 62:
                    raise CreationError('Render worker wall limit')
                if process.poll() is None:
                    return
                stop(process)
                self.render = None
                directory = self.render_directory(job)
                if process.returncode != 0 or not (directory/'render-result.json').exists():
                    raise CreationError('Render worker failed; inspect its local log')
                result = parse((directory/'render-result.json').read_text())
                if result['path'] != job['plan']['operations'][job['step']]['path']:
                    raise CreationError('Render result does not match the approved output')
                result['path'] = str(directory.relative_to(self.store.directory(job['id']))/result['path'])
                result['metrics'] = parse((directory/'render-metrics.json').read_text())
                self._advance(job, result); return
            if job['step'] >= len(job['plan']['operations']):
                self.store.update(job['id'], {'Applying'}, state='Completed', approval=None)
                self.message = 'Completed ' + job['id']; self.active = None; return
            item = job['plan']['operations'][job['step']]
            self._quota(256*1024*1024)
            self.message = f"Executing {job['step']+1}/{len(job['plan']['operations'])}: {item['op']}"
            directory = self.store.directory(job['id'])
            if item['op'] == 'scene.render':
                directory = self.render_directory(job)
                directory.mkdir(parents=True, exist_ok=False)
                if (directory/item['path']).exists():
                    raise CreationError('Existing preview refused')
                (directory/'render-request.json').write_text(canonical(item))
                project = self.store.directory(job['id'])/f"checkpoint-{job['step']:03d}.blend"
                log = (directory/'render.log').open('w')
                process = subprocess.Popen([str(python_path()), '-I', str(Path(__file__).with_name('supervisor.py')),
                    str(app_path()), str(directory), str(project)], env=clean_env(directory), stdout=log, stderr=log,
                    start_new_session=True)
                log.close(); self.render = {'process': process, 'started': time.monotonic()}
                self.store.update(job['id'], {'Applying'}, state='Rendering')
            else:
                result = engine.apply(bpy.context.scene, item, job['aliases'], directory, job)
                self._advance(job, result)
        except Exception as error:
            self._stop_render()
            current = self.store.get(job['id'])
            if current['state'] not in TERMINAL:
                self.store.update(job['id'], {current['state']}, state='Failed', error=str(error), approval=None)
            self.message = str(error); self.active = None

    def render_directory(self, job):
        return self.store.directory(job['id'])/'previews'/f"step-{job['step']:03d}"

    def close(self):
        self.cancel(self.active)
        self.authority.close(); self.store.db.close()
