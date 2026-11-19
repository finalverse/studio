# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""V1 founders, headless (cloud continuation). Runs the reviewed V1 founder plans
through the same validate → preflight → apply → preview → package path as the
S2 native runner, using upstream bpy (Remesh/OpenSubdiv enabled) and Cycles CPU
previews because EEVEE has no headless GPU here. Previews are therefore Studio
authoring evidence, not Infinity runtime evidence.

python3 -I v1_cloud.py ROOT [founder ...]"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

tests = Path(__file__).resolve().parent
import bpy  # upstream bpy first: scripts/modules has its own bpy package
sys.path.append(str(tests.parents[1]/'scripts/modules'))
sys.path.insert(0, str(tests))
from finalverse_creation import engine, glbcheck
from finalverse_creation.protocol import RENDER_OPS, digest, validate
import v1_founders as V

args = sys.argv[1:]
root = Path(args[0]).resolve(); root.mkdir(parents=True, exist_ok=True)
names = args[1:] or list(V.FOUNDERS)
results = {'schema_version': 'finalverse.studio-v1-cloud/v1', 'bpy': bpy.app.version_string,
           'build_hash': bpy.app.build_hash.decode(), 'renderer': 'CYCLES/CPU', 'founders': {}}


def render(scene, item, directory):
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'; scene.cycles.samples = max(16, item['samples']*4)
    scene.cycles.use_denoising = True
    scene.render.resolution_x = item['width']; scene.render.resolution_y = item['height']
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    directory.mkdir(parents=True); scene.frame_set(item.get('frame', 1))
    scene.render.filepath = str(directory/item['path']); bpy.ops.render.render(write_still=True)
    return {'path': str(directory/item['path'])}


for key in names:
    started = time.monotonic()
    plan, package = V.plan(key)
    plan = {**plan, 'operations': [*plan['operations'], package]}
    record = {'identity': V.FOUNDERS[key][1], 'archetype': V.FOUNDERS[key][2]}
    try:
        validate(plan)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        job = {'id': str(uuid.uuid4()), 'digest': digest(plan), 'plan': plan, 'source': 'v1-reviewed-template'}
        directory = root/key
        directory.mkdir()
        engine.preflight(scene, plan)
        aliases, steps = {}, []
        for step, item in enumerate(plan['operations']):
            t = time.monotonic()
            if item['op'] in RENDER_OPS:
                result = render(scene, item, directory/'previews'/f'step-{step:03d}')
            else:
                result = engine.apply(scene, item, aliases, directory, job)
            steps.append({'op': item['op'], 'ms': round((time.monotonic()-t)*1000, 1)})
        out = directory/package['path']
        manifest = json.loads((out/'manifest.json').read_text())
        hashes = all(hashlib.sha256((out/k).read_bytes()).hexdigest() == v['sha256'] for k, v in manifest['files'].items())
        glbs = {k: glbcheck.check((out/k).read_bytes()) for k in manifest['files'] if k.endswith('.glb')}
        gate = subprocess.run([sys.executable, '-I', str(tests.parent/'validate_candidate.py'), str(out)],
                              capture_output=True, text=True)
        record.update({
            'ok': True, 'seconds': round(time.monotonic()-started, 1), 'steps': steps,
            'manifest_sha256': hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest(),
            'hashes_match': hashes, 'published': manifest['published'], 'world_effects': manifest['world_effects'],
            'clips': [c['name'] for c in manifest['clips']],
            'glb': {k: {'triangles': v['triangles'], 'joints': v['joints'], 'skins': v['skins'],
                        'animations': v['animations']} for k, v in glbs.items()},
            'gate': json.loads(gate.stdout) if gate.returncode == 0 else ('FAILED: ' + gate.stderr[-600:]),
            'evaluation_passed': json.loads((out/'evaluation.json').read_text())['passed'],
            'contract': json.loads((out/'contract-check.json').read_text()) if (out/'contract-check.json').exists() else None})
    except Exception as e:  # recorded, never hidden
        record.update({'ok': False, 'seconds': round(time.monotonic()-started, 1), 'error': f'{type(e).__name__}: {e}'})
    results['founders'][key] = record
    print(key, 'OK' if record['ok'] else record['error'], record['seconds'], flush=True)
    (root/'result.json').write_text(json.dumps(results, indent=2))
