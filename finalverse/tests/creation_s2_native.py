# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""S2 native tool coverage with fixture plans (no model). Run inside the built app:
Finalverse Studio --background --factory-startup --python creation_s2_native.py -- ROOT [--source-modules]
Previews are rendered in-process here; the sandboxed worker path is exercised by
the model workflow harness."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

args = sys.argv[sys.argv.index('--')+1:]
root = Path(args[0]).resolve(); root.mkdir(parents=True, exist_ok=False)
tests = Path(__file__).resolve().parent
if '--source-modules' in args:
    sys.path.insert(0, str(tests.parents[1]/'scripts/modules'))
    for name in [m for m in sys.modules if m.startswith('finalverse_creation')]:
        del sys.modules[name]
sys.path.insert(0, str(tests))
import bpy
from finalverse_creation import engine, glbcheck
from finalverse_creation.protocol import CreationError, RENDER_OPS, digest, validate
import s2_fixtures as F

results = {'schema_version': 'finalverse.studio-s2-native/v1', 'build_hash': bpy.app.build_hash.decode(),
           'modules': engine.__file__, 'runs': {}, 'negative': {}, 'determinism': {}}


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    return scene


def render(scene, item, directory):
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = item['width']; scene.render.resolution_y = item['height']
    scene.render.resolution_percentage = 100; scene.eevee.taa_render_samples = item['samples']
    scene.render.image_settings.file_format = 'PNG'
    directory.mkdir(parents=True); scene.frame_set(item.get('frame', 1))
    scene.render.filepath = str(directory/item['path']); bpy.ops.render.render(write_still=True)
    return {'path': str((directory/item['path']).relative_to(directory.parents[1]))}


def run(name, plan):
    scene = fresh()
    job = {'id': str(uuid.uuid4()), 'digest': digest(plan), 'plan': plan, 'source': 'fixture'}
    directory = root/name; directory.mkdir()
    started = time.monotonic(); engine.preflight(scene, plan)
    aliases, steps = {}, []
    for step, item in enumerate(plan['operations']):
        t = time.monotonic()
        if item['op'] in RENDER_OPS:
            result = render(scene, item, directory/'previews'/f'step-{step:03d}')
        else:
            result = engine.apply(scene, item, aliases, directory, job)
        steps.append({'op': item['op'], 'ms': round((time.monotonic()-t)*1000, 2),
                      'result': {k: v for k, v in result.items() if k not in ('assets',)}})
    record = {'operations': len(plan['operations']), 'seconds': round(time.monotonic()-started, 3), 'steps': steps,
              'snapshot_revision': engine.snapshot(scene)['revision']}
    results['runs'][name] = record
    return scene, aliases, directory, record


def verify_package(directory, path):
    out = directory/path
    manifest = json.loads((out/'manifest.json').read_text())
    import hashlib
    hashes = all(hashlib.sha256((out/k).read_bytes()).hexdigest() == v['sha256'] for k, v in manifest['files'].items())
    glbs = {k: glbcheck.check((out/k).read_bytes()) for k in manifest['files'] if k.endswith('.glb')}
    gate = subprocess.run([sys.executable, '-I', str(tests.parent/'validate_candidate.py'), str(out)],
                          capture_output=True, text=True)
    return {'files': sorted(manifest['files']), 'hashes_match': hashes, 'published': manifest['published'],
            'world_effects': manifest['world_effects'], 'clips': [c['name'] for c in manifest['clips']],
            'glb': {k: {'animations': v['animations'], 'skins': v['skins'], 'joints': v['joints'],
                        'triangles': v['triangles']} for k, v in glbs.items()},
            's0_transport_gate': json.loads(gate.stdout) if gate.returncode == 0 else gate.stderr[-400:],
            'evaluation': json.loads((out/'evaluation.json').read_text())['passed'],
            'contract': json.loads((out/'contract-check.json').read_text()) if (out/'contract-check.json').exists() else None}


# 1. Floating spirit (Lumi) — no skeleton, hover/drift/greet object clips.
lumi = F.plan('Fixture: Lumi floating spirit candidate', [*F.lumi_scene(), F.LUMI_PACKAGE])
scene, aliases, directory, _ = run('lumi', lumi)
results['runs']['lumi']['package'] = verify_package(directory, 'lumi.fvpkg')

# 2. Humanoid rigs, automatic + envelope skinning, retargeted walk.
scene, aliases, directory, _ = run('rigs', F.humanoid_rigs())
results['runs']['rigs']['package'] = verify_package(directory, 'human.fvpkg')
src = bpy.data.actions['Human Walk']; dst = bpy.data.actions['Synthetic Walk']
src_keys = sorted((c.data_path, c.array_index, tuple(round(v, 5) for k in c.keyframe_points for v in k.co))
                  for c in engine.curves(src) if 'leg_l' in c.data_path)
dst_keys = sorted((c.data_path, c.array_index, tuple(round(v, 5) for k in c.keyframe_points for v in k.co))
                  for c in engine.curves(dst) if 'leg_l' in c.data_path)
results['runs']['rigs']['retarget_rotation_keys_equal'] = src_keys == dst_keys and bool(src_keys)
kai = next(o for o in scene.objects if o.name == 'Synthetic Study')
results['runs']['rigs']['envelope_unweighted'] = sum(1 for v in kai.data.vertices if not v.groups)

# 3. Environment: buildings, trees, geometry-nodes scatter, deform, parenting.
scene, aliases, directory, _ = run('environment', F.environment())
results['runs']['environment']['package'] = verify_package(directory, 'village.fvpkg')
results['runs']['environment']['scatter_vertices'] = len(next(o for o in scene.objects if o.name == 'Meadow Grove').data.vertices)

# Negative: E1 archetype rules refuse before approval.
bad = copy.deepcopy(lumi); bad['operations'].insert(2, {'op': 'armature.create', 'ref': '@rig', 'name': 'Spirit Rig',
                                                         'template': 'humanoid_basic', 'height': 1.2})
for label, candidate in [('spirit_skeleton', bad)]:
    try: validate(candidate); results['negative'][label] = 'ACCEPTED'
    except CreationError as e: results['negative'][label] = 'refused: ' + str(e)
walk = copy.deepcopy(lumi); walk['operations'][6]['locomotion'] = 'walk'
try: validate(walk); results['negative']['spirit_walk_clip'] = 'ACCEPTED'
except CreationError as e: results['negative']['spirit_walk_clip'] = 'refused: ' + str(e)
legs = copy.deepcopy(lumi); legs['operations'][1]['name'] = 'Lumi legs'
try: validate(legs); results['negative']['spirit_leg_name'] = 'ACCEPTED'
except CreationError as e: results['negative']['spirit_leg_name'] = 'refused: ' + str(e)
# Negative: deterministic preview evaluation blocks export of a badly framed asset.
away = F.plan('Fixture: camera looks away', [*F.lumi_scene(camera=([0, -4.2, 1.0], [0, -9, 1.0])),
                                              {**F.LUMI_PACKAGE, 'path': 'away.fvpkg'}])
try:
    run('lumi-away', away); results['negative']['badly_framed_export'] = 'ACCEPTED'
except CreationError as e:
    results['negative']['badly_framed_export'] = 'refused: ' + str(e)
    results['negative']['badly_framed_package_absent'] = not (root/'lumi-away'/'away.fvpkg').exists()

# Determinism: identical generator inputs → identical geometry hashes.
def geometry(plan_ops):
    scene = fresh(); job = {'id': 'det', 'digest': 'd', 'plan': F.plan('det', plan_ops)}
    aliases = {}
    for item in plan_ops: engine.apply(scene, item, aliases, root, job)
    return sorted(o['geometry'] for o in engine.snapshot(scene)['objects'] if o['geometry'])
spirit_op = [{'op': 'character.spirit', 'ref': '@s', 'name': 'S', 'height': 1.2}]
tree_op = lambda seed: [{'op': 'procedural.tree', 'ref': '@t', 'name': 'T', 'location': [0, 0, 0], 'kind': 'broadleaf',
                          'height': 5, 'trunk_radius': .2, 'branches': 5, 'seed': seed}]
results['determinism'] = {'spirit_repeat_equal': geometry(spirit_op) == geometry(spirit_op),
                          'tree_same_seed_equal': geometry(tree_op(3)) == geometry(tree_op(3)),
                          'tree_other_seed_differs': geometry(tree_op(3)) != geometry(tree_op(4))}
(root/'result.json').write_text(json.dumps(results, indent=2))
print(json.dumps({k: results[k] for k in ('negative', 'determinism')}, indent=2))
