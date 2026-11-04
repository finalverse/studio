# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""S2 Validate → Export: a local candidate package for Genesis admission.

Produces editable source, GLB, per-clip GLB/JSON, previews, an E1
universal-embodiment body (characters), a draft definition, evaluation, GLB
checks, provenance and a hashed manifest. It is a candidate only: nothing is
published, bound to a resident or written to any world/civilization store."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import uuid

import bpy

from . import glbcheck
from .creation2 import ACTION_ID, OBJECT_ID, PART_ATTR, PARTS, find, find_action
from .evaluate import CHARACTERS, evaluate, hierarchy
from .protocol import CreationError, canonical, digest

PACKAGE_SCHEMA = 'finalverse.studio-asset-package/v1'
E1 = 'finalverse.universal-embodiment/v1'
GENERATOR = 'finalverse-studio-s2/1'
MAX_FILE = 128*1024*1024
DEFAULT_MODES = {'humanoid': ['walk', 'run', 'climb'], 'synthetic_humanoid': ['walk', 'run', 'climb'],
                 'floating_spirit': ['hover', 'fly', 'drift'], 'botanical_sprite': ['fly', 'hover', 'drift'],
                 'nature_elemental': ['rooted', 'walk', 'climb'], 'fire_elemental': ['walk', 'run', 'hover']}
EXPRESSIONS = {'idle': 'idle', 'greet': 'greet', 'observe': 'observe', 'interact': 'interact', 'speak': 'speak',
               'locomote': 'locomote'}


def yup(v):
    """Blender Z-up → glTF/E1 Y-up (right-handed): (x, y, z) → (x, z, -y)."""
    return [round(v[0], 6), round(v[2], 6), round(-v[1], 6)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select(blocks):
    bpy.ops.object.select_all(action='DESELECT')
    for b in blocks:
        b.hide_set(False); b.select_set(True)
    bpy.context.view_layer.objects.active = blocks[0]


def export_glb(path, blocks, mode):
    select(blocks)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True, export_yup=True,
                              export_animations=mode is not None, export_animation_mode=mode or 'ACTIONS',
                              export_extras=True, export_apply=False, export_force_sampling=True)
    if path.stat().st_size > MAX_FILE:
        raise CreationError(path.name + ' exceeds 128 MiB')


def owner_of(scene, action):
    owner = next((o for o in scene.objects if o.get(OBJECT_ID) == action.get('finalverse.target')), None)
    if owner is None:
        raise CreationError('Clip ' + action.name + ' has no target object')
    return owner


def export_clip(path, scene, blocks, action):
    owner = owner_of(scene, action); ad = owner.animation_data
    saved = [(t, t.mute) for t in ad.nla_tracks]
    try:
        for t, _ in saved:
            t.mute = True
        ad.action = action
        if hasattr(ad, 'action_suitable_slots') and ad.action_suitable_slots and not ad.action_slot:
            ad.action_slot = ad.action_suitable_slots[0]
        export_glb(path, blocks, 'ACTIVE_ACTIONS')
    finally:
        ad.action = None
        for t, mute in saved:
            t.mute = mute


def clip_json(scene, action):
    from .evaluate import sample_clip
    owner = owner_of(scene, action)
    frames, samples = sample_clip(action, owner)
    tracks = {}
    for path, rows in samples.items():
        if path == 'location':
            tracks[path] = [yup(r) for r in rows]
        elif path == 'rotation_euler':
            tracks[path] = [[round(r[0], 6), round(r[2], 6), round(-r[1], 6)] for r in rows]  # XYZ Euler, Y-up axes
        elif path == 'scale':
            tracks[path] = [[round(r[0], 6), round(r[2], 6), round(r[1], 6)] for r in rows]
        else:
            tracks[path] = [[round(x, 6) for x in r] for r in rows]
    return {'schema_version': 'finalverse.studio-clip/v1', 'name': action.name,
            'kind': action.get('finalverse.kind'), 'locomotion': action.get('finalverse.locomotion'),
            'loop': bool(action.get('finalverse.loop')), 'fps': scene.render.fps, 'frames': frames,
            'target': owner.get(OBJECT_ID), 'frame_convention': 'glTF Y-up, metres, XYZ Euler radians',
            'tracks': tracks}


def material_behavior(material):
    shader = material.node_tree.nodes.get('Principled BSDF') if material and material.use_nodes else None
    if not shader:
        return {'color_rgba': [.8, .8, .8, 1], 'metallic': 0.0, 'roughness': .5, 'emissive_rgb': [0, 0, 0],
                'pulse_amplitude': 0.0}
    strength = shader.inputs['Emission Strength'].default_value
    emissive = [min(8.0, max(0.0, c*strength)) for c in shader.inputs['Emission Color'].default_value[:3]]
    return {'color_rgba': [round(min(1, max(0, c)), 6) for c in shader.inputs['Base Color'].default_value],
            'metallic': round(min(1, max(0, shader.inputs['Metallic'].default_value)), 6),
            'roughness': round(min(1, max(.04, shader.inputs['Roughness'].default_value)), 6),
            'emissive_rgb': [round(e, 6) for e in emissive], 'pulse_amplitude': .25 if any(emissive) else 0.0}


def parts_of(block, origin, joints, ratio=1.0, joint_by_name=None):
    """Split a generated mesh into E1 parts by its fv_part face attribute.
    LOD1 is a Decimate-modifier copy (face attributes and material indices carry
    over); its parts reuse the LOD0 joint of the same part name."""
    scene = bpy.context.scene
    temp = None
    if ratio < 1:
        temp = bpy.data.objects.new('fv-lod-temp', block.data.copy()); scene.collection.objects.link(temp)
        temp.matrix_world = block.matrix_world.copy()
        temp.modifiers.new('lod', 'DECIMATE').ratio = ratio
        bpy.context.view_layer.update()
        mesh = bpy.data.meshes.new_from_object(temp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    else:
        mesh = bpy.data.meshes.new_from_object(block.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    try:
        mesh.calc_loop_triangles()
        names = json.loads(block.get(PARTS, '[]')) or [[block.name, 'all']]
        attr = mesh.attributes.get(PART_ATTR)
        matrix = block.matrix_world; normal_matrix = matrix.to_3x3().inverted().transposed()
        groups = {g.index: g.name for g in block.vertex_groups}
        buckets = {}
        for tri in mesh.loop_triangles:
            index = attr.data[tri.polygon_index].value if attr else 0
            buckets.setdefault((index, tri.material_index), []).append(tri)
        parts = []
        for (index, material_index), tris in sorted(buckets.items()):
            remap, positions, normals, indices = {}, [], [], []
            for tri in tris:
                for v in tri.vertices:
                    if v not in remap:
                        remap[v] = len(positions)
                        positions.append(yup(matrix @ mesh.vertices[v].co - origin))
                        normals.append(yup((normal_matrix @ mesh.vertices[v].normal).normalized()))
                    indices.append(remap[v])
            material = block.data.materials[material_index] if material_index < len(block.data.materials) else None
            name = (names[index][0] if index < len(names) else block.name)[:80]
            joint = None
            if joint_by_name is not None:
                joint = joint_by_name.get(name)
            elif joints and groups:
                totals = {}
                for v in remap:
                    for g in block.data.vertices[v].groups:
                        totals[groups[g.group]] = totals.get(groups[g.group], 0) + g.weight
                if totals:
                    best = max(sorted(totals), key=lambda n: totals[n])
                    joint = joints.index(best) if best in joints else None
            parts.append({'name': name, 'positions': positions, 'normals': normals, 'indices': indices,
                          'material': material_behavior(material), 'joint': joint,
                          'role': 'expressive_detail' if index < len(names) and names[index][1] == 'eyes' else 'solid'})
        return parts
    finally:
        bpy.data.meshes.remove(mesh)
        if temp is not None:
            data = temp.data; bpy.data.objects.remove(temp); bpy.data.meshes.remove(data)


def skeleton_of(rig, origin):
    if rig is None:
        return None, []
    names = [b.name for b in rig.data.bones]
    joints = [{'name': b.name, 'parent': names.index(b.parent.name) if b.parent else None,
               'pivot': yup(rig.matrix_world @ b.head_local - origin)} for b in rig.data.bones]
    return {'version': GENERATOR, 'joints': joints}, names


def e1_structural(artifact, definition, body_bytes):
    """Python port of E1 Artifact::validate + EmbodimentDefinition::validate rules
    (crates/embodiment/src/universal.rs at Core 33eb4b0), excluding the generator
    header, which only E1's own reviewed Blender worker satisfies."""
    errors = []
    def need(ok, label):
        if not ok:
            errors.append(label)
    need(artifact['schema_version'] == E1 and 1 <= len(artifact['lods']) <= 3, 'universal asset header/LODs')
    sk = artifact['skeleton']
    if sk:
        need(0 < len(sk['joints']) <= 64, 'skeleton budget')
        seen = set()
        for i, j in enumerate(sk['joints']):
            need(j['name'] and len(j['name']) <= 64 and j['name'] not in seen and (j['parent'] is None or j['parent'] < i)
                 and all(math.isfinite(x) and abs(x) <= 4 for x in j['pivot']), 'skeleton topology/name/pivot')
            seen.add(j['name'])
    if artifact['archetype'] == 'floating_spirit':
        need(sk is None, 'spirit has no humanoid skeleton')
    total = 0
    for li, lod in enumerate(artifact['lods']):
        need(lod['distance_m'] >= 0 and (lod['distance_m'] == 0 if li == 0 else lod['distance_m'] > artifact['lods'][li-1]['distance_m'])
             and 0 < len(lod['parts']) <= 128, 'LOD/part bounds')
        for p in lod['parts']:
            need(p['name'] and len(p['name']) <= 80 and len(p['positions']) == len(p['normals']) and
                 0 < len(p['positions']) <= 100000 and p['indices'] and len(p['indices']) % 3 == 0 and
                 all(i < len(p['positions']) for i in p['indices']) and
                 all(math.isfinite(v) and abs(v) <= 8 for xyz in p['positions'] + p['normals'] for v in xyz), 'mesh validation')
            need(p['joint'] is None or (sk is not None and p['joint'] < len(sk['joints'])), 'mesh skeleton reference')
            m = p['material']
            need(all(0 <= v <= 1 for v in m['color_rgba']) and all(0 <= v <= 8 for v in m['emissive_rgb'])
                 and 0 <= m['metallic'] <= 1 and .04 <= m['roughness'] <= 1 and 0 <= m['pulse_amplitude'] <= 1,
                 'material behavior')
            total += len(p['indices'])//3
            if artifact['archetype'] == 'floating_spirit':
                need(not any(w in p['name'].lower() for w in ('leg', 'foot', 'walking')), 'spirit cannot acquire conventional legs')
    need(total <= 100000, 'geometry budget')
    d = definition
    need(d['artifact_sha256'] == hashlib.sha256(body_bytes).hexdigest() and d['archetype'] == artifact['archetype']
         and d['skeleton'] == artifact['skeleton'] and d['specification_sha256'] == artifact['specification_sha256'],
         'universal definition pin')
    need(0 < len(d['locomotion']['modes']) <= 8 and all(m in DEFAULT_MODES.get(d['archetype'], []) for m in d['locomotion']['modes'])
         and 0 <= d['locomotion']['max_speed_mps'] <= 8 and 0 <= d['locomotion']['max_displacement_m'] <= 20,
         'locomotion compatibility')
    need(0 < len(d['animation']['expressions']) <= 6 and d['manifestation']['max_particles'] <= 32 and
         d['manifestation']['max_triangles'] <= 100000 and 0 <= d['deformation']['max_displacement_m'] <= .3 and
         0 <= d['deformation']['max_scale_delta'] <= .1, 'animation/manifestation budget')
    need(d['manifestation']['lod_distances_m'] == [l['distance_m'] for l in artifact['lods']] and
         all(sum(len(p['indices'])//3 for p in l['parts']) <= d['manifestation']['max_triangles'] for l in artifact['lods']),
         'declared LOD and triangle budgets')
    c = d['collision']
    need((c['shape'] == 'sphere' and .05 <= c['radius_m'] <= 1) or
         (c['shape'] == 'capsule' and .05 <= c['radius_m'] <= 1 and .1 <= c['height_m'] <= 3.5), 'collision')
    return errors


def package(scene, item, aliases, directory, job):
    subject = find(scene, item['subject'], aliases)
    if subject.type != 'MESH':
        raise CreationError('Package subject must be a mesh')
    archetype = item['archetype']; clips = [find_action(c, aliases) for c in item['clips']]
    job_dir = Path(directory)
    previews = sorted(p for p in job_dir.glob('previews/step-*/*.png') if not p.is_symlink())
    blocks, rig = hierarchy(subject)
    height = None
    if scene.objects.get('fv-lod-temp'):
        raise CreationError('Stale LOD object present')
    # --- Validate: deterministic gate before anything is exported -------------
    report = evaluate(scene, subject, archetype, clips, previews)
    if not report['passed']:
        raise CreationError('Validation failed: ' + ', '.join(report['failures'][:8]))
    out = job_dir/item['path']
    if out.exists() or out.is_symlink():
        raise CreationError('Existing package refused')
    out.mkdir(); (out/'clips').mkdir(); (out/'previews').mkdir()
    files = {}
    def record(path, media):
        path = Path(path)
        if path.stat().st_size > MAX_FILE:
            raise CreationError(path.name + ' exceeds 128 MiB')
        files[str(path.relative_to(out))] = {'sha256': sha(path), 'byte_length': path.stat().st_size, 'media_type': media}
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'source.blend'), copy=True); record(out/'source.blend', 'application/x-blender')
    export_glb(out/'asset.glb', blocks, 'NLA_TRACKS' if clips else None); record(out/'asset.glb', 'model/gltf-binary')
    checks = {'asset.glb': glbcheck.check((out/'asset.glb').read_bytes())}
    clip_entries = []
    for action in clips:
        safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in action.name)[:48]
        export_clip(out/'clips'/f'{safe}.glb', scene, blocks, action); record(out/'clips'/f'{safe}.glb', 'model/gltf-binary')
        checks['clips/' + safe + '.glb'] = glbcheck.check((out/'clips'/f'{safe}.glb').read_bytes())
        data = clip_json(scene, action)
        (out/'clips'/f'{safe}.json').write_text(json.dumps(data, sort_keys=True)); record(out/'clips'/f'{safe}.json', 'application/json')
        clip_entries.append({'name': action.name, 'id': action.get(ACTION_ID), 'kind': data['kind'],
                             'locomotion': data['locomotion'], 'loop': data['loop'], 'frames': [data['frames'][0], data['frames'][-1]],
                             'fps': data['fps'], 'glb': f'clips/{safe}.glb', 'samples': f'clips/{safe}.json'})
    for p in previews:
        target = out/'previews'/(p.parent.name + '-' + p.name); shutil.copyfile(p, target); record(target, 'image/png')
    # Export consistency: one animation per clip; spirits carry no skin.
    glb = checks['asset.glb']
    consistency = {'animations_match_clips': len(glb['animations']) == len(clips),
                   'skins_match_archetype': (glb['skins'] == 0) if archetype in ('floating_spirit', 'botanical_sprite') else True,
                   'clip_files_single_animation': all(len(checks[k]['animations']) == 1 for k in checks if k.startswith('clips/'))}
    if not all(consistency.values()):
        raise CreationError('Export check failed: ' + ', '.join(k for k, v in consistency.items() if not v))
    contract = None
    origin = subject.matrix_world.translation.copy()
    if archetype in CHARACTERS:
        skeleton, joints = skeleton_of(rig, origin)
        z = [(b.matrix_world @ v.co).z for b in blocks if b.type == 'MESH' and not b.hide_render for v in b.data.vertices]
        height = round(max(z) - min(z), 4)
        identity = item.get('identity') or str(uuid.uuid4())
        specification = {'schema_version': E1, 'generator': GENERATOR, 'name': item['name'], 'identity': identity,
                         'archetype': archetype, 'revision': 1, 'height_m': height, 'seed': 0,
                         'reference_sha256': None}
        spec_bytes = canonical(specification).encode(); (out/'specification.json').write_bytes(spec_bytes)
        record(out/'specification.json', 'application/json')
        meshes = [b for b in blocks if b.type == 'MESH' and not b.hide_render]
        lod0 = [p for b in meshes for p in parts_of(b, origin, joints)]
        by_name = {}
        for p in lod0:
            by_name.setdefault(p['name'], p['joint'])
        lod1 = [p for b in meshes for p in parts_of(b, origin, joints, item.get('lod1_ratio', .35), by_name)]
        lods = [{'distance_m': 0.0, 'parts': lod0}, {'distance_m': 18.0, 'parts': lod1}]
        artifact = {'schema_version': E1, 'generator': GENERATOR, 'specification_sha256': hashlib.sha256(spec_bytes).hexdigest(),
                    'archetype': archetype, 'skeleton': skeleton, 'lods': lods,
                    'source_reference_sha256': files['source.blend']['sha256']}
        body = canonical(artifact).encode()
        if len(body) > 8*1024*1024:
            raise CreationError('E1 body exceeds 8 MiB')
        (out/'body.json').write_bytes(body); record(out/'body.json', 'application/json')
        modes = sorted({c['locomotion'] for c in clip_entries if c['locomotion'] != 'none'}) or DEFAULT_MODES[archetype]
        kinds = sorted({c['kind'] for c in clip_entries}) or ['idle']
        spirit = archetype in ('floating_spirit', 'botanical_sprite')
        definition = {'schema_version': E1, 'id': f's2:candidate:{identity}:r1', 'archetype': archetype, 'revision': 1,
            'artifact_sha256': hashlib.sha256(body).hexdigest(), 'specification_sha256': artifact['specification_sha256'],
            'skeleton': skeleton,
            'deformation': {'procedure': 'studio-clip-sampled/1', 'max_displacement_m': .2, 'max_scale_delta': .06},
            'locomotion': {'modes': modes, 'max_speed_mps': 2.0, 'max_displacement_m': 2.0},
            'animation': {'expressions': [EXPRESSIONS[k] for k in kinds][:6], 'procedure': 'studio-authored-clips/1'},
            'communication': {'modalities': ['light', 'flight_gesture'] if spirit else ['gesture', 'caption'],
                              'audio_implementation': 'none; captions only'},
            'attachments': {'slots': [], 'allowed_archetypes': []},
            'manifestation': {'id': 'studio-candidate/1', 'max_triangles': 100000,
                              'max_particles': 6 if archetype in ('floating_spirit', 'synthetic_humanoid') else 0,
                              'lod_distances_m': [0.0, 18.0], 'teleport_like': False},
            'collision': {'shape': 'sphere', 'radius_m': round(min(1.0, max(.05, height*.42)), 4)} if spirit else
                         {'shape': 'capsule', 'radius_m': .35, 'height_m': min(3.5, max(.1, height))},
            'provenance': f'Finalverse Studio S2 candidate from job {job["id"]} plan {job["digest"]}; not published or bound'}
        (out/'definition.draft.json').write_text(canonical(definition)); record(out/'definition.draft.json', 'application/json')
        contract = {'structural_errors': e1_structural(artifact, definition, body),
                    'generator_header': GENERATOR, 'e1_admits_generator': False,
                    'note': 'E1 Artifact::validate admits only generator blender-universal/1; Genesis must admit this generator'}
        if contract['structural_errors']:
            raise CreationError('E1 contract check failed: ' + ', '.join(contract['structural_errors'][:6]))
    receipts = [job.get('model_receipt')] if job.get('model_receipt') else []
    provenance = {'schema_version': 'finalverse.studio-provenance/v1', 'product': 'Finalverse Studio',
                  'blender_version': bpy.app.version_string, 'build_hash': bpy.app.build_hash.decode(),
                  'job': job['id'], 'plan_digest': job['digest'], 'plan_protocol': job['plan']['schema_version'],
                  'source': job.get('source'), 'model_receipts': receipts, 'scene_revision': report['scene_revision'],
                  'evaluation_digest': report['digest'], 'subject': subject.get(OBJECT_ID), 'archetype': archetype,
                  'license': 'user-declared; required at Genesis admission',
                  'authority': 'none: local candidate; no publication, binding or world mutation'}
    for name, value in (('evaluation.json', report), ('glb-check.json', {'files': checks, 'consistency': consistency}),
                        ('provenance.json', provenance)):
        (out/name).write_text(json.dumps(value, indent=2, sort_keys=True)); record(out/name, 'application/json')
    if contract:
        (out/'contract-check.json').write_text(json.dumps(contract, indent=2)); record(out/'contract-check.json', 'application/json')
    # S0 candidate contract (source + GLB) so the existing transport gate applies unchanged.
    candidate = {'schema_version': 'finalverse.studio-candidate/v1', 'product': 'Finalverse Studio',
                 'blender_version': bpy.app.version_string, 'state': 'candidate', 'published': False,
                 'source_license': 'user-declared; required at Genesis admission',
                 'frame': {'axes': 'glTF right-handed Y-up', 'unit': 'metre'},
                 'assets': {k: files[k] for k in ('asset.glb', 'source.blend')},
                 'publication': 'Independent Genesis validation and authorization required'}
    (out/'candidate.json').write_text(json.dumps(candidate, indent=2, sort_keys=True))
    manifest = {'schema_version': PACKAGE_SCHEMA, 'name': item['name'], 'archetype': archetype, 'state': 'candidate',
                'published': False, 'world_effects': 0, 'subject': subject.get(OBJECT_ID),
                'identity_reference': item.get('identity'), 'height_m': height,
                'frame': {'axes': 'glTF right-handed Y-up', 'unit': 'metre'},
                'files': files, 'clips': clip_entries,
                'lods': [{'distance_m': 0.0}, {'distance_m': 18.0, 'triangle_ratio': item.get('lod1_ratio', .35)}]
                        if contract else [{'distance_m': 0.0}],
                'evaluation': {'passed': report['passed'], 'digest': report['digest'], 'advisories': report['advisories']},
                'genesis': {'candidate_manifest': 'candidate.json', 'embodiment_body': 'body.json' if contract else None,
                            'definition_draft': 'definition.draft.json' if contract else None,
                            'admission': 'required', 'publication_authorized': False}}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return {'path': item['path'], 'files': len(files) + 2, 'manifest_sha256': sha(out/'manifest.json'),
            'evaluation_passed': True, 'clips': len(clip_entries), 'published': False}
