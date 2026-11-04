# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""S2 workflow acceptance in the built app: the real Host, a real local model,
the sandboxed preview worker, deterministic evaluation, bounded revision and the
validated export. The harness plays the artist: it logs each proposal it reviews
and approves it with the host's normal approve() call. This stands in for a
human click and is labelled as such in every record.
Usage: Finalverse Studio --background --factory-startup --python creation_s2_loop.py -- ROOT MODE
MODE = model (model plans from the intent) | seeded (artist draft with a framing defect; model revises)"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

args = sys.argv[sys.argv.index('--')+1:]
root = Path(args[0]).resolve(); mode = args[1]; root.mkdir(parents=True, exist_ok=False)
model = args[2] if len(args) > 2 else 'gemma4:e4b'
tests = Path(__file__).resolve().parent; sys.path.insert(0, str(tests))
import bpy
from finalverse_creation import glbcheck
from finalverse_creation.host import Host
from finalverse_creation.protocol import CreationError
import s2_fixtures as F

bpy.ops.wm.read_factory_settings(use_empty=True)
host = Host(str(root/'workspace'))
INTENT = ('Create Lumi, the floating spirit companion: a soft, rounded, luminous pale-mint body about 1.2 m tall with '
          'a rounded crown, small side fins and large dark expressive eyes. Lumi floats and never walks. Give the body '
          'a gentle glowing material and the eyes a dark glossy material. Add an idle hover loop, a slow drift loop and '
          'a short greet expression. Frame Lumi from the front in a 384x384 preview.')
spec = dict(provider='local', model=model, intent=INTENT, archetype='floating_spirit', name='Lumi',
            identity=F.LUMI_IDENTITY, max_revisions=2)
if mode == 'seeded':
    spec['initial_plan'] = F.plan('Artist draft: Lumi with the preview camera aimed away (seeded defect)',
                                  F.lumi_scene(camera=([0, -4.2, 1.0], [0, -9, 1.0])))
started = time.monotonic()
loop = host.start_loop(**spec)
reviews = []
while not loop.finished and time.monotonic() - started < 1800:
    host.tick()
    if loop.stage in ('proposed', 'export_proposed'):
        job = host.store.get(loop.job)
        if job['state'] == 'Proposed':
            review = {'job': job['id'], 'source': job['source'], 'digest': job['digest'],
                      'summary': job['plan']['summary'], 'operations': [o['op'] for o in job['plan']['operations']],
                      'reviewer': 'acceptance harness acting as artist (not a human click)', 't': round(time.monotonic()-started, 2)}
            try:
                host.approve(job['id']); review['decision'] = 'approved'
            except CreationError as error:
                review['decision'] = 'rejected: ' + str(error); loop.reject(str(error))
            reviews.append(review); print('REVIEW', json.dumps(review), flush=True)
    time.sleep(.05)
elapsed = time.monotonic() - started
result = {'schema_version': 'finalverse.studio-s2-loop/v1', 'mode': mode, 'model': model,
          'build_hash': bpy.app.build_hash.decode(), 'elapsed_s': round(elapsed, 2), 'loop': json.loads((loop.dir/'loop.json').read_text()),
          'reviews': reviews, 'approval_note': 'Approvals were issued by this harness through Host.approve; no human clicked.'}
jobs = []
for job in host.store.jobs():
    jobs.append({'id': job['id'], 'state': job['state'], 'source': job['source'], 'steps': job['step'],
                 'operations': len(job['plan']['operations']), 'error': job.get('error'),
                 'receipt': {k: (job.get('model_receipt') or {}).get(k) for k in ('model', 'latency_ms', 'usage', 'language')}})
result['jobs'] = jobs
if loop.result and loop.result.get('outcome') == 'completed':
    out = host.store.directory(loop.result['job'])/loop.result['package']
    manifest = json.loads((out/'manifest.json').read_text())
    result['package_dir'] = str(out)
    result['package'] = {
        'hashes_match': all(hashlib.sha256((out/k).read_bytes()).hexdigest() == v['sha256'] for k, v in manifest['files'].items()),
        'files': sorted(manifest['files']), 'published': manifest['published'], 'world_effects': manifest['world_effects'],
        'glb': {k: glbcheck.check((out/k).read_bytes()) for k in manifest['files'] if k.endswith('.glb')},
        'evaluation': json.loads((out/'evaluation.json').read_text()),
        'contract': json.loads((out/'contract-check.json').read_text())}
    gate = subprocess.run([sys.executable, '-I', str(tests.parent/'validate_candidate.py'), str(out)], capture_output=True, text=True)
    result['package']['s0_transport_gate'] = json.loads(gate.stdout) if gate.returncode == 0 else gate.stderr[-400:]
(root/'result.json').write_text(json.dumps(result, indent=2, default=str))
host.close()
print('LOOP', json.dumps(loop.result))
