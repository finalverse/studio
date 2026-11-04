# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded S2 creation loop:
Intent → Plan → Generate → Preview → Evaluate → Revise → Validate → Export.

The loop never approves anything itself. Every model plan and the final export
plan become ordinary Proposed jobs in the same store and wait for the artist's
exact approval. Evaluation is deterministic (evaluate.py). Revisions are new,
visible model proposals given the failed checks; nothing is repaired silently.
The loop stops at its revision budget, its wall budget, a cancellation, or a
completed package."""
import json
from pathlib import Path
import time
import uuid

from .protocol import SCHEMA_V2, CreationError, LOCOMOTION, canonical, digest, validate
from .store import TERMINAL

SUBJECT_OPS = ('character.spirit', 'character.humanoid', 'procedural.building', 'procedural.tree', 'mesh.primitive')
MAX_REVISIONS = 3
WALL_SECONDS = 1800


class CreationLoop:
    def __init__(self, host, provider, model, intent, archetype, name, identity=None, max_revisions=2,
                 package_path=None, initial_plan=None):
        if not 0 <= max_revisions <= MAX_REVISIONS:
            raise CreationError(f'Revision budget is 0–{MAX_REVISIONS}')
        if archetype not in LOCOMOTION:
            raise CreationError('Unknown archetype')
        self.host, self.provider, self.model = host, provider, model
        self.intent, self.archetype, self.name, self.identity = intent, archetype, name, identity
        self.max_revisions = max_revisions; self.revisions = 0
        self.id = str(uuid.uuid4()); self.started = time.monotonic()
        self.dir = host.store.root/'loops'/self.id; self.dir.mkdir(parents=True, mode=0o700)
        safe = ''.join(c if c.isalnum() else '-' for c in name.lower()).strip('-')[:40] or 'asset'
        self.package_path = package_path or f'{safe}.fvpkg'
        self.stage = 'intent'; self.job = None; self.subject = None; self.clips = {}; self.render = None
        self.bounds = None
        self.ledger = []; self.reports = []; self.finished = False; self.result = None
        self.initial_plan = initial_plan
        self.record('intent', intent=intent, archetype=archetype, name=name, provider=provider, model=model,
                    max_revisions=max_revisions)

    # --- bookkeeping -----------------------------------------------------------
    def record(self, stage, **detail):
        self.ledger.append({'t': round(time.monotonic()-self.started, 3), 'stage': stage, **detail})
        self.save()

    def save(self):
        state = {'schema_version': 'finalverse.studio-loop/v1', 'id': self.id, 'stage': self.stage,
                 'archetype': self.archetype, 'name': self.name, 'revisions': self.revisions,
                 'max_revisions': self.max_revisions, 'subject': self.subject, 'clips': self.clips,
                 'job': self.job, 'finished': self.finished, 'result': self.result, 'ledger': self.ledger}
        path = self.dir/'loop.json'; tmp = self.dir/'loop.json.tmp'
        tmp.write_text(json.dumps(state, indent=2)); tmp.replace(path)

    def finish(self, outcome, **detail):
        self.stage = outcome; self.finished = True; self.result = {'outcome': outcome, **detail}
        self.record(outcome, **detail)
        self.host.message = f'Loop {outcome}: ' + str(detail.get('reason') or detail.get('package') or '')[:60]

    # --- stages ----------------------------------------------------------------
    def plan_prompt(self):
        modes = sorted(LOCOMOTION[self.archetype] - {'none'}) or ['none']
        return (f"{self.intent}\nSubject: {self.name}, archetype {self.archetype}. Create the subject with one generator "
                f"operation, its materials, animation clips whose locomotion is one of {modes} (or none for "
                "expressions), a camera, a light rig, render.configure with transparent true and one preview.render. "
                "Keep the whole subject inside the preview frame. Do not include asset.package.")

    def start(self):
        if self.initial_plan is not None:
            # An artist-authored first draft enters the same store and approval path.
            validate(self.initial_plan)
            snapshot = self.host.refresh()
            job = self.host.store.submit(self.initial_plan, snapshot['scene_id'], snapshot['revision'],
                                         str(uuid.uuid4()), source='artist-draft')
            self.job = job['id']; self.stage = 'proposed'
            self.record('plan', request='artist draft', job=job['id'], plan_digest=job['digest'])
            return
        self.stage = 'plan'
        self.host.infer(self.provider, 'plan', self.model, self.plan_prompt(), language='v2',
                        context={'stage': 'plan', 'archetype': self.archetype, 'loop': self.id})
        self.record('plan', request='initial')

    def replan(self, failures, reason):
        """Nothing has executed yet: retry the original intent with the rejection reason (counts as a revision)."""
        if self.revisions >= self.max_revisions:
            return self.finish('failed', reason=f'revision budget ({self.max_revisions}) exhausted: {reason}',
                               failures=failures)
        self.revisions += 1; self.stage = 'plan'
        self.host.infer(self.provider, 'plan', self.model, self.plan_prompt(), language='v2',
                        context={'stage': 'plan', 'archetype': self.archetype, 'loop': self.id, 'attempt': self.revisions + 1,
                                 'previous_attempt_rejected': reason[:400],
                                 'instruction': 'Return one complete JSON object with exactly the keys schema_version, '
                                                'summary and operations, following the example format.'})
        self.record('replan', revision=self.revisions, reason=reason[:200])

    def hints(self, failures):
        """Deterministic, check-specific guidance; the model still writes the plan."""
        b = self.bounds or {}
        h = b.get('size', [1, 1, 1])[2]; c = b.get('centre', [0, 0, h/2])
        out = []
        for f in failures:
            fid = f['id']
            if fid.endswith('.loop_continuity'):
                clip = fid.split('.', 1)[1].rsplit('.', 1)[0]
                out.append(f"Re-create clip {clip!r} with action.create using the same name (it replaces the old clip); "
                           "its last key must repeat its first key exactly.")
            elif fid == 'preview.viewpoint':
                out.append(f"Add camera.configure in front of the subject (front is -Y), roughly level: location "
                           f"[{c[0]:.2f}, {c[1]-max(3, h*3.5):.2f}, {c[2]+h*.15:.2f}], look_at [{c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f}].")
            elif fid.endswith('.coverage') or fid.endswith('.framing'):
                out.append(f"Move the camera so the whole subject (about {h:.2f} m tall, centre {[round(x, 2) for x in c]}) "
                           "fills 10–60% of the frame without touching the edges.")
            elif fid.endswith('.exposure'):
                out.append("Adjust light.rig energy or the material emission so the subject is neither black nor white.")
            elif fid.startswith('clip.') and fid.endswith('.displacement'):
                out.append("Keep that clip's keys within 0.3 m of the rest position (2 m for locomotion clips).")
            elif fid == 'plan.valid':
                out.append('Return ONE JSON object with exactly the keys schema_version, summary and operations.')
        return out[:12]

    def revise(self, failures, reason):
        if self.revisions >= self.max_revisions:
            return self.finish('failed', reason=f'revision budget ({self.max_revisions}) exhausted: {reason}',
                               failures=failures)
        if time.monotonic()-self.started > WALL_SECONDS:
            return self.finish('failed', reason='wall budget exhausted', failures=failures)
        self.revisions += 1; self.stage = 'revise'
        context = {'stage': 'revise', 'archetype': self.archetype, 'revision': self.revisions,
                   'subject': self.subject, 'subject_bounds': self.bounds, 'clips': self.clips,
                   'failed_checks': failures[:24], 'reason': reason[:400], 'how_to_fix': self.hints(failures),
                   'format_example': {'schema_version': SCHEMA_V2, 'summary': 'Fix the preview camera', 'operations': [
                       {'op': 'camera.configure', 'ref': '@front_cam', 'name': 'Front Camera', 'location': [0, -4, 0.8],
                        'look_at': [0, 0, 0.6], 'lens': 50},
                       {'op': 'preview.render', 'path': 'revised-front.png', 'width': 384, 'height': 384,
                        'samples': 16, 'frame': 1}]},
                   'instruction': 'Return a small finalverse.creation/v2 plan that fixes only the failed checks. '
                                  'Modify existing objects by UUID; do not recreate the subject. If a camera '
                                  'must change, use object.transform on its UUID or add a new camera.configure. '
                                  'End with a new preview.render that uses a new file name'
                                  + (f" and the same size/samples as before ({self.render['width']}x{self.render['height']}, "
                                     f"{self.render['samples']} samples)" if self.render else ' (384x384, 16 samples)')
                                  + '; previews are limited to 60 s.'}
        self.host.infer(self.provider, 'plan', self.model,
                        f'Revise {self.name} so the failed evaluation checks pass.', language='v2', context=context)
        self.record('revise', revision=self.revisions, failures=[f['id'] for f in failures][:24], reason=reason[:200])

    def evaluate(self, job):
        from . import engine, evaluate as ev
        from .creation2 import find_action
        import bpy
        aliases = job['aliases']
        if self.subject is None:
            first = next((o for o in job['plan']['operations'] if o['op'] in SUBJECT_OPS), None)
            if first is None:
                return self.revise([{'id': 'plan.subject', 'measured': None, 'limit': 'one subject generator'}],
                                   'plan created no subject')
            self.subject = aliases[first['ref']]
        for item in job['plan']['operations']:
            if item['op'] in ('action.create', 'action.retarget'):
                self.clips[item['name']] = aliases[item['ref']]
            if item['op'] in ('preview.render', 'scene.render'):
                self.render = {k: item[k] for k in ('width', 'height', 'samples') if k in item}
                self.render['frame'] = item.get('frame', 1)
        scene = bpy.context.scene
        subject = next((o for o in scene.objects if o.get('finalverse.object_id') == self.subject), None)
        if subject is None:
            return self.finish('failed', reason='subject no longer exists')
        clips = []
        for cid in self.clips.values():
            try:
                clips.append(find_action(cid, {}))
            except CreationError:
                pass
        previews = sorted(self.host.store.directory(job['id']).glob('previews/step-*/*.png'))
        report = ev.evaluate(scene, subject, self.archetype, clips, previews)
        size = next((c['measured'] for c in report['checks'] if c['id'] == 'geometry.bounds'), None)
        if size:
            loc = list(subject.matrix_world.translation)
            self.bounds = {'size': size, 'centre': [round(loc[0], 3), round(loc[1], 3), round(loc[2] + size[2]/2, 3)]}
        index = len(self.reports); (self.dir/f'evaluation-{index:02d}.json').write_text(json.dumps(report, indent=2))
        self.reports.append(report['digest'])
        failed = [c for c in report['checks'] if c['gating'] and not c['passed']]
        self.record('evaluate', job=job['id'], passed=report['passed'], failures=[c['id'] for c in failed],
                    advisories=report['advisories'], digest=report['digest'], checks=len(report['checks']))
        if report['passed']:
            return self.propose_export()
        return self.revise([{k: c[k] for k in ('id', 'measured', 'limit')} for c in failed], 'evaluation failed')

    def propose_export(self):
        render = self.render or {'width': 384, 'height': 384, 'samples': 16, 'frame': 1}
        package = {'op': 'asset.package', 'path': self.package_path, 'archetype': self.archetype,
                   'subject': self.subject, 'name': self.name, 'clips': list(self.clips.values())[:16], 'lod1_ratio': .35}
        if self.identity:
            package['identity'] = self.identity
        plan = {'schema_version': SCHEMA_V2, 'summary': f'Validate and export {self.name} as a Genesis candidate',
                'operations': [{'op': 'preview.render', 'path': 'export-preview.png', **render}, package]}
        validate(plan)
        snapshot = self.host.refresh()
        job = self.host.store.submit(plan, snapshot['scene_id'], snapshot['revision'], str(uuid.uuid4()), source='loop-export')
        self.job = job['id']; self.stage = 'export_proposed'
        self.host.message = 'Evaluation passed; review and approve the export plan'
        self.record('validate', export_job=job['id'], plan_digest=job['digest'])

    def tick(self):
        if self.finished:
            return
        host = self.host
        if self.stage in ('plan', 'revise'):
            if host.inference:
                return
            result = host.model_result or {}
            if result.get('ok') and 'plan' in result and host.last_job_id and host.last_job_id != self.job:
                self.job = host.last_job_id; self.stage = 'proposed'
                self.record('proposed', job=self.job, receipt={k: result['receipt'].get(k) for k in
                            ('provider', 'model', 'latency_ms', 'usage', 'response_digest')})
            else:
                error = result.get('error') or 'no plan'
                self.record('plan_failed', error=error, detail=result.get('detail'))
                failure = [{'id': 'plan.valid', 'measured': str(error)[:300], 'limit': 'valid v2 plan'}]
                if self.subject is None:
                    self.replan(failure, 'previous plan was rejected: ' + str(error)[:300])
                else:
                    self.revise(failure, 'previous plan was rejected: ' + str(error)[:300])
            return
        if self.stage in ('proposed', 'export_proposed', 'executing', 'exporting'):
            job = host.store.get(self.job)
            if job['state'] in ('Approved', 'Applying', 'Rendering'):
                if self.stage in ('proposed', 'export_proposed'):
                    self.stage = 'executing' if self.stage == 'proposed' else 'exporting'
                    self.record('generate' if self.stage == 'executing' else 'export', job=self.job, approved=True)
                return
            if job['state'] == 'Proposed':
                return
            if job['state'] == 'Completed':
                if self.stage in ('exporting', 'export_proposed'):
                    result = job['results'][-1]
                    return self.finish('completed', package=result.get('path'), job=self.job,
                                       manifest_sha256=result.get('manifest_sha256'), revisions=self.revisions)
                self.stage = 'evaluating'; self.record('preview', job=self.job, results=len(job['results']))
                return self.evaluate(job)
            if job['state'] == 'Cancelled':
                return self.finish('cancelled', job=self.job)
            # Failed or Interrupted: the reason is visible and may drive one bounded revision.
            reason = job.get('error') or job['state']
            if self.stage in ('exporting', 'export_proposed'):
                return self.revise([{'id': 'export.validate', 'measured': reason[:300], 'limit': 'package validates'}],
                                   'export failed: ' + reason)
            self.record('generate_failed', job=self.job, error=reason)
            return self.revise([{'id': 'generate.execute', 'measured': reason[:300], 'limit': 'plan executes'}],
                               'execution failed: ' + reason)

    def reject(self, reason):
        """The artist declines (or cannot approve) the current proposal: visible, bounded revision."""
        if self.finished or self.stage not in ('proposed', 'export_proposed'):
            raise CreationError('No loop proposal is waiting for review')
        job = self.job; self.host.store.cancel(job)
        self.record('rejected', job=job, reason=reason[:400])
        self.revise([{'id': 'artist.review', 'measured': reason[:300], 'limit': 'artist approval'}],
                    'artist rejected the proposal: ' + reason)

    def cancel(self):
        if not self.finished:
            self.finish('cancelled', reason='artist cancelled')
