# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Deterministic S2 evaluation of a subject: geometry, rig, animation and previews.

Every check reports a measured value and its limit. Gating checks decide whether
an asset may be packaged; advisory checks are reported but do not block. No model
is consulted here, so the same scene always yields the same report."""
import json
import math

import bpy
import numpy
from mathutils import Vector

from .protocol import LOCOMOTION, SPIRITS, digest

CHARACTERS = {'humanoid', 'synthetic_humanoid', 'floating_spirit', 'botanical_sprite', 'nature_elemental',
              'fire_elemental'}
RIGGED = {'humanoid', 'synthetic_humanoid', 'fire_elemental'}
TEMPLATE_JOINTS = {'humanoid': {'root', 'head', 'arm_l', 'arm_r', 'leg_l', 'leg_r'}}
TEMPLATE_JOINTS['synthetic_humanoid'] = TEMPLATE_JOINTS['fire_elemental'] = TEMPLATE_JOINTS['humanoid']


class Report:
    def __init__(self):
        self.checks = []

    def add(self, cid, category, passed, measured, limit, gating=True):
        self.checks.append({'id': cid, 'category': category, 'passed': bool(passed), 'measured': measured,
                            'limit': limit, 'gating': gating})


def hierarchy(subject):
    """The subject, its armature (if skinned) and its descendants."""
    blocks = [subject]
    rig = subject.parent if subject.parent and subject.parent.type == 'ARMATURE' else None
    if rig:
        blocks.insert(0, rig)
    stack = list(subject.children)
    while stack:
        child = stack.pop(); blocks.append(child); stack += list(child.children)
    return blocks, rig


def mesh_stats(block):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = block.evaluated_get(depsgraph); mesh = evaluated.to_mesh()
    try:
        matrix = block.matrix_world
        co = [matrix @ v.co for v in mesh.vertices]
        mesh.calc_loop_triangles()
        tris = len(mesh.loop_triangles)
        degenerate = sum(1 for t in mesh.loop_triangles if t.area < 1e-10)
        finite = all(math.isfinite(c) for v in co for c in v)
        edges = {}
        for p in mesh.polygons:
            for e in p.edge_keys:
                edges[e] = edges.get(e, 0) + 1
        nonmanifold = sum(1 for count in edges.values() if count != 2)
        unassigned = sum(1 for p in mesh.polygons if p.material_index >= len(block.data.materials)
                         or block.data.materials[p.material_index] is None)
        return {'co': co, 'triangles': tris, 'degenerate': degenerate, 'finite': finite,
                'nonmanifold_edges': nonmanifold, 'edges': len(edges), 'unassigned_faces': unassigned}
    finally:
        evaluated.to_mesh_clear()


def sample_clip(action, block):
    """Sample a clip's own curves (independent of NLA/mute state) at every frame."""
    from .engine import curves
    start, end = (int(round(f)) for f in action.frame_range)
    tracks = {}
    for curve in curves(action):
        tracks.setdefault(curve.data_path, {})[curve.array_index] = curve
    frames = list(range(start, end+1))
    samples = {}
    for path, channels in tracks.items():
        rest = None
        if path in ('location', 'rotation_euler', 'scale'):
            rest = list(getattr(block, path))
        default = 1.0 if path.endswith('scale') else 0.0
        rows = []
        for f in frames:
            rows.append([channels[i].evaluate(f) if i in channels else (rest[i] if rest else default) for i in range(3)])
        samples[path] = rows
    return frames, samples


def materials_ok(block):
    problems = []
    for m in block.data.materials:
        if not m or not m.use_nodes:
            problems.append('missing or nodeless material'); continue
        shader = m.node_tree.nodes.get('Principled BSDF')
        if not shader:
            problems.append(m.name + ': no Principled BSDF'); continue
        color = list(shader.inputs['Base Color'].default_value)
        rough = shader.inputs['Roughness'].default_value
        emission = [c*shader.inputs['Emission Strength'].default_value for c in shader.inputs['Emission Color'].default_value[:3]]
        if not all(0 <= c <= 1 for c in color) or not .04 <= rough <= 1 or not all(0 <= e <= 8 for e in emission):
            problems.append(m.name + ': outside E1 material bounds')
    return problems


def preview(path, transparent):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        w, h = image.size
        pixels = numpy.empty(w*h*4, dtype=numpy.float32); image.pixels.foreach_get(pixels)
        pixels = pixels.reshape(h, w, 4)
    finally:
        bpy.data.images.remove(image)
    lum = (pixels[..., 0]*.2126 + pixels[..., 1]*.7152 + pixels[..., 2]*.0722)
    if not transparent:
        return {'size': [w, h], 'transparent': False, 'subject_luminance': round(float(lum.mean()), 5)}
    alpha = pixels[..., 3] > .02
    coverage = float(alpha.mean())
    border = bool(alpha[0, :].any() or alpha[-1, :].any() or alpha[:, 0].any() or alpha[:, -1].any())
    subject_lum = float(lum[alpha].mean()) if alpha.any() else 0.0
    ys, xs = numpy.nonzero(alpha)
    centre = [float(xs.mean()/w), float(ys.mean()/h)] if alpha.any() else None
    return {'size': [w, h], 'transparent': True, 'coverage': round(coverage, 5), 'touches_border': border,
            'subject_luminance': round(subject_lum, 5), 'centroid': centre}


def evaluate(scene, subject, archetype, clips, previews=(), declared_height=None):
    r = Report(); previews = list(previews)
    blocks, rig = hierarchy(subject)
    meshes = [b for b in blocks if b.type == 'MESH' and not b.hide_render]
    stats = [mesh_stats(b) for b in meshes]
    tris = sum(s['triangles'] for s in stats)
    points = [v for s in stats for v in s['co']]
    r.add('geometry.present', 'geometry', bool(points) and tris >= 12, tris, '>= 12 triangles')
    r.add('geometry.finite', 'geometry', all(s['finite'] for s in stats), all(s['finite'] for s in stats), 'all finite')
    r.add('geometry.triangle_budget', 'geometry', tris <= 100000, tris, '<= 100000 (E1)')
    degenerate = sum(s['degenerate'] for s in stats)
    r.add('geometry.degenerate_triangles', 'geometry', degenerate == 0, degenerate, '0')
    edges = sum(s['edges'] for s in stats) or 1
    nonmanifold = sum(s['nonmanifold_edges'] for s in stats)
    r.add('geometry.nonmanifold_ratio', 'geometry', nonmanifold/edges <= .02, round(nonmanifold/edges, 5), '<= 0.02',
          gating=False)
    unassigned = sum(s['unassigned_faces'] for s in stats)
    r.add('material.assigned', 'material', unassigned == 0, unassigned, '0 faces without material')
    problems = [p for b in meshes for p in materials_ok(b)]
    r.add('material.e1_bounds', 'material', not problems, problems[:8], 'color/roughness/emission within E1 bounds')
    if points:
        lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
        hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
        size = hi - lo; origin = subject.matrix_world.translation
        r.add('geometry.bounds', 'geometry', (0.1 <= size.z <= 3.5) if archetype in CHARACTERS else size.length <= 400,
              [round(size.x, 4), round(size.y, 4), round(size.z, 4)],
              'height 0.1–3.5 m (E1 specification)' if archetype in CHARACTERS else 'diagonal <= 400 m')
        if declared_height:
            r.add('geometry.declared_height', 'geometry', abs(size.z - declared_height) <= .2*declared_height,
                  round(size.z, 4), f'{declared_height} m ±20%')
        clearance = lo.z - origin.z
        if archetype in SPIRITS:
            r.add('anatomy.floating_clearance', 'rig', clearance >= .02, round(clearance, 4), '>= 0.02 m above origin')
        elif archetype in RIGGED:
            r.add('anatomy.grounded', 'rig', abs(clearance) <= .05*max(size.z, .1), round(clearance, 4), '|feet - origin| <= 5% height')
    names = [n for b in meshes for n, _ in json.loads(b.get('finalverse.parts', '[]'))] + [b.name for b in blocks]
    if archetype in SPIRITS:
        legs = [n for n in names if any(w in n.lower() for w in ('leg', 'foot', 'walking'))]
        r.add('anatomy.no_legs', 'rig', not legs, legs, 'no leg/foot/walking parts (E1 spirit)')
        skinned = rig is not None or any(b.vertex_groups for b in meshes) or any(b.type == 'ARMATURE' for b in blocks)
        r.add('rig.no_skeleton', 'rig', not skinned, skinned, 'floating spirit has no skeleton (E1)')
    if archetype in RIGGED:
        r.add('rig.present', 'rig', rig is not None, rig.name if rig else None, 'skinned to an armature')
        if rig:
            bones = {b.name for b in rig.data.bones}
            missing = sorted(TEMPLATE_JOINTS[archetype] - bones)
            r.add('rig.joints', 'rig', not missing and len(bones) <= 64, {'bones': len(bones), 'missing': missing},
                  'E1 joints present, <= 64 bones')
            weighted = [b for b in meshes if b.parent == rig]
            empty = sum(1 for b in weighted for v in b.data.vertices if sum(g.weight for g in v.groups) <= 1e-6)
            r.add('rig.weights', 'rig', bool(weighted) and empty == 0, empty, '0 unweighted vertices')
    allowed = LOCOMOTION.get(archetype, {'none'})
    for action in clips:
        owner = next((o for o in scene.objects if o.get('finalverse.object_id') == action.get('finalverse.target')), None)
        cid = 'clip.' + action.name
        if owner is None:
            r.add(cid + '.owner', 'animation', False, None, 'clip target exists'); continue
        frames, samples = sample_clip(action, owner)
        values = [x for rows in samples.values() for row in rows for x in row]
        r.add(cid + '.keys', 'animation', len(frames) >= 2 and values and all(math.isfinite(x) for x in values),
              {'frames': len(frames), 'channels': len(samples)}, '>= 2 frames, finite')
        duration = (frames[-1]-frames[0]) / scene.render.fps
        r.add(cid + '.duration', 'animation', .25 <= duration <= 20, round(duration, 4), '0.25–20 s')
        mode = action.get('finalverse.locomotion', 'none')
        r.add(cid + '.locomotion', 'animation', mode in allowed, mode, sorted(allowed))
        if action.get('finalverse.loop'):
            gap = max((abs(a-b) for rows in samples.values() for a, b in zip(rows[0], rows[-1])), default=0)
            r.add(cid + '.loop_continuity', 'animation', gap <= 1e-3, round(gap, 6), '<= 0.001 first↔last frame')
        if 'location' in samples:
            rest = Vector(owner.location)
            reach = max((Vector(row) - rest).length for row in samples['location'])
            limit = 2.0 if mode not in ('none',) else .3
            r.add(cid + '.displacement', 'animation', reach <= limit, round(reach, 4), f'<= {limit} m from rest')
        if 'scale' in samples and archetype in CHARACTERS:
            delta = max(abs(x-1) for row in samples['scale'] for x in row)
            r.add(cid + '.scale_delta', 'animation', delta <= .1, round(delta, 4), '<= 0.1 (E1 max_scale_delta)')
    if archetype in CHARACTERS:
        r.add('animation.clips_present', 'animation', len(clips) >= 1, len(clips), '>= 1 clip for a character')
    if archetype in CHARACTERS:
        camera = scene.camera
        if camera is None:
            r.add('preview.viewpoint', 'preview', False, None, 'scene camera faces the subject front')
        else:
            forward = (camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
            front = (subject.matrix_world.to_3x3() @ Vector((0, -1, 0))).normalized()
            facing = -forward.dot(front)            # 1 = looking straight at the face
            down = math.degrees(math.asin(max(-1, min(1, -forward.z))))
            r.add('preview.viewpoint', 'preview', facing >= .5 and down <= 50,
                  {'facing': round(facing, 4), 'look_down_deg': round(down, 2)},
                  'faces the subject front (≥ 0.5, i.e. within 60°) and looks down ≤ 50°')
    transparent = scene.render.film_transparent
    for path in previews:
        info = preview(path, transparent)
        pid = 'preview.' + path.name
        framed = archetype in CHARACTERS or archetype == 'prop'
        if not info['transparent']:
            r.add(pid + '.evaluable', 'preview', not framed, 'opaque film', 'transparent film for subject framing checks')
            r.add(pid + '.exposure', 'preview', .04 <= info['subject_luminance'] <= .95, info['subject_luminance'], '0.04–0.95')
            continue
        if not framed:
            r.add(pid + '.exposure', 'preview', .04 <= info['subject_luminance'] <= .95, info['subject_luminance'], '0.04–0.95')
            continue
        r.add(pid + '.coverage', 'preview', .03 <= info['coverage'] <= .85, info['coverage'], '0.03–0.85 of frame')
        r.add(pid + '.framing', 'preview', not info['touches_border'], info['touches_border'], 'subject inside frame')
        r.add(pid + '.exposure', 'preview', .04 <= info['subject_luminance'] <= .95, info['subject_luminance'], '0.04–0.95')
        if info['centroid']:
            off = max(abs(info['centroid'][0]-.5), abs(info['centroid'][1]-.5))
            r.add(pid + '.centred', 'preview', off <= .25, round(off, 4), '<= 0.25 from centre', gating=False)
    if archetype in CHARACTERS or archetype in ('environment', 'prop'):
        r.add('preview.present', 'preview', len(previews) >= 1, len(previews), '>= 1 preview')
    failures = [c['id'] for c in r.checks if c['gating'] and not c['passed']]
    from .engine import snapshot
    result = {'schema_version': 'finalverse.studio-evaluation/v1', 'subject': subject.get('finalverse.object_id'),
              'subject_name': subject.name, 'archetype': archetype, 'scene_revision': snapshot(scene)['revision'],
              'checks': r.checks, 'passed': not failures, 'failures': failures,
              'advisories': [c['id'] for c in r.checks if not c['gating'] and not c['passed']]}
    result['digest'] = digest(result)
    return result
