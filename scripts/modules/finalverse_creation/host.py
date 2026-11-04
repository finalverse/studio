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
from . import keychain
from .providers import SECRET_ENV, default_registry, load, profile, registry, save
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
        self.key_status = {}; self.refresh_keys()
        self.inference = None; self.render = None; self.active = None
        self.expected_revision = None; self.last_snapshot = 0
        self.message = 'Session ready; proposals require approval'
        self.model_names = []; self.model_result = None; self.selected_provider = 'local'
        self.refresh()

    def refresh(self):
        index = engine.snapshot(bpy.context.scene)
        self.store.snapshot(index); self.last_snapshot = time.monotonic()
        return index

    def infer(self, provider_id, mode, model='', prompt=''):
        if self.inference or self.active:
            raise CreationError('Finish or cancel the active task first')
        self.providers = registry(self.config)
        if provider_id not in self.providers:
            raise CreationError('Unknown provider')
        p = self.providers[provider_id]
        if not p['enabled']:
            raise CreationError(p['label'] + ' is off. Turn it on before connecting.')
        secret = None
        if p['credential'] == 'keychain':
            secret = keychain.read(p['id'])
            if secret is None:
                raise CreationError('No API key stored in the Keychain for ' + p['label'])
        work = self.store.root/'inference'/str(uuid.uuid4()); work.mkdir(parents=True, mode=0o700)
        snapshot = self.refresh()
        request = {'provider': provider_id, 'mode': mode, 'model': model, 'prompt': prompt, 'snapshot': snapshot}
        (work/'input.json').write_text(canonical(request))
        env = clean_env(work)
        if secret is not None:
            # Private child environment only; never written to input/output/log files.
            env[SECRET_ENV] = secret
        log = (work/'helper.log').open('w')
        process = subprocess.Popen([str(python_path()), '-I', str(Path(__file__).with_name('provider_entry.py')),
            str(self.config), str(work/'input.json'), str(work/'output.json')],
            env=env, stdout=log, stderr=log, start_new_session=True)
        log.close()
        self.inference = {'process': process, 'work': work, 'request': request, 'started': time.monotonic()}
        self.message = (f"Testing {p['label']}…" if mode == 'models'
                        else f"Planning with {p['label']}… Studio remains responsive")
        self.selected_provider = provider_id

    # Provider registry edits come only from the artist's own Studio operators.
    def refresh_keys(self):
        self.key_status = {}
        for p in self.providers.values():
            if p['credential'] == 'keychain':
                try:
                    self.key_status[p['id']] = keychain.exists(p['id'])
                except keychain.KeychainError:
                    self.key_status[p['id']] = False

    def configure_provider(self, value, secret=None):
        if self.inference or self.active:
            raise CreationError('Finish or cancel the active task first')
        value = profile(dict(value))
        current = load(self.config)['providers']
        existing = next((p for p in current if p['id'] == value['id']), None)
        if existing and existing['preset'] != value['preset']:
            raise CreationError('A provider preset cannot be changed')
        providers = [value if p['id'] == value['id'] else p for p in current]
        if existing is None:
            if value['preset'] != 'custom':
                raise CreationError('Only custom providers can be added')
            providers.append(value)
        if value['id'] == 'local' and not value['enabled']:
            raise CreationError('Local Gemma is the default and stays on')
        save(self.config, providers)  # validates all profiles before replacing the file
        if secret:
            keychain.store(value['id'], secret)
        self.providers = registry(self.config); self.refresh_keys()
        self.message = 'Saved provider ' + value['label'] + ('; key stored in Keychain' if secret else '')

    def set_enabled(self, provider_id, enabled):
        p = dict(self.providers[provider_id]); p['enabled'] = bool(enabled)
        self.configure_provider(p)
        self.message = p['label'] + (' is on' if enabled else ' is off')

    def remove_provider(self, provider_id):
        if self.inference or self.active:
            raise CreationError('Finish or cancel the active task first')
        p = self.providers[provider_id]
        if p['preset'] != 'custom':
            raise CreationError('Built-in providers cannot be removed; turn them off instead')
        save(self.config, [q for q in load(self.config)['providers'] if q['id'] != provider_id])
        keychain.delete(provider_id)
        self.providers = registry(self.config); self.refresh_keys()
        self.message = 'Removed ' + p['label'] + ' and its Keychain key'

    def forget_key(self, provider_id):
        keychain.delete(provider_id); self.refresh_keys()
        self.message = 'Deleted the Keychain key for ' + self.providers[provider_id]['label']

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
                    detail = result.get('detail')
                    self.message = ('Failed: ' + result.get('error', 'unknown') + (f' ({detail})' if detail else '')
                                    + '; no fallback used')
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
