# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Allowlisted Blender bridge. Call only on Blender's main thread."""
import hashlib
import json
import math
import struct
import uuid

import bpy
from mathutils import Vector

from .protocol import CREATES, MATERIAL_CREATES, ACTION_CREATES, RENDER_OPS, SCHEMA_V2, CreationError, canonical, digest, validate

OBJECT_ID = 'finalverse.object_id'
MATERIAL_ID = 'finalverse.material_id'


def identity(block, key, seen):
    value = block.get(key)
    try:
        if str(uuid.UUID(value)) != value or value in seen:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        value = str(uuid.uuid4()); block[key] = value
    seen.add(value)
    return value


def curves(action):
    if not action:
        return []
    # Blender 5 uses layered actions; older action APIs remain probe-only.
    if hasattr(action, 'layers'):
        return [f for layer in action.layers for strip in layer.strips
                for bag in getattr(strip, 'channelbags', []) for f in bag.fcurves]
    return list(action.fcurves)


def actions_of(o):
    ad = o.animation_data
    if not ad:
        return []
    found = [ad.action] if ad.action else []
    for track in ad.nla_tracks:
        found += [strip.action for strip in track.strips if strip.action and strip.action not in found]
    if len(ad.nla_tracks) > 16:
        raise CreationError('At most 16 clip tracks per object')
    return found


def animation_state(o):
    ad = o.animation_data
    if not ad:
        return {'active': None, 'tracks': []}
    def keys(action):
        return [{'path': c.data_path, 'index': c.array_index, 'group': c.group.name if c.group else None,
                 'keys': [[*k.co, k.interpolation] for k in c.keyframe_points]} for c in curves(action)]
    tracks = [{'name': t.name, 'mute': t.mute, 'strips': [{'action': s.action.get('finalverse.action_id') if s.action else None,
               'name': s.action.name if s.action else None, 'start': s.frame_start, 'end': s.frame_end,
               'meta': {k: s.action.get('finalverse.' + k) for k in ('kind', 'locomotion', 'loop')} if s.action else None,
               'curves': keys(s.action) if s.action else []} for s in t.strips]} for t in ad.nla_tracks]
    return {'active': keys(ad.action) if ad.action else None, 'tracks': tracks}


def weights_hash(o):
    h = hashlib.sha256()
    for g in o.vertex_groups:
        h.update(g.name.encode() + b'\0')
    for v in o.data.vertices:
        for g in v.groups:
            h.update(struct.pack('<IIf', v.index, g.group, g.weight))
    return h.hexdigest()


def node_state(tree):
    result = []
    for node in sorted(tree.nodes, key=lambda n: n.name):
        inputs = []
        for socket in node.inputs:
            if hasattr(socket, 'default_value'):
                value = socket.default_value
                if not isinstance(value, (str, int, float, bool)):
                    try: value = list(value)
                    except TypeError: value = str(value)
                inputs.append([socket.identifier, value])
        result.append([node.name, node.type, node.mute, inputs])
    return {'nodes': result, 'links': sorted([l.from_node.name, l.from_socket.identifier,
            l.to_node.name, l.to_socket.identifier] for l in tree.links)}


def snapshot(scene):
    scene_materials = {m for o in scene.objects if hasattr(o.data, 'materials') for m in o.data.materials if m}
    scene_materials.update(m for m in bpy.data.materials if m.get('finalverse.provenance'))
    if len(scene.objects) > 256 or len(scene_materials) > 256:
        raise CreationError("Automation supports at most 256 objects and materials")
    total = sum(len(o.data.vertices) for o in scene.objects if o.type == 'MESH')
    if total > 100000:
        raise CreationError("Scene exceeds the 100,000 vertex automation limit")
    if sum(len(o.data.loops) for o in scene.objects if o.type == 'MESH') > 600000:
        raise CreationError('Scene exceeds the 600,000 face-corner limit')
    # S1 deliberately accepts a small authoring subset. Opaque evaluation graphs
    # are outside the revision and execution bounds of this initial bridge.
    for o in scene.objects:
        if o.type not in {'MESH', 'CAMERA', 'LIGHT', 'EMPTY', 'ARMATURE'}:
            raise CreationError('Automation supports mesh, armature, camera, light and empty objects')
        # S2 admits exactly one live modifier kind: the Armature deform created by skinning.
        if any(m.type != 'ARMATURE' or m.object is None or m.object.type != 'ARMATURE' for m in o.modifiers) \
                or len(o.modifiers) > 1 or o.constraints or (o.animation_data and o.animation_data.drivers):
            raise CreationError('Apply modifiers and remove constraints/drivers before automation')
        if o.type == 'MESH' and o.data.shape_keys:
            raise CreationError('Shape keys are outside the automation profile')
        if o.type == 'ARMATURE' and len(o.data.bones) > 64:
            raise CreationError('Armatures are limited to 64 bones')
        for action in actions_of(o):
            if sum(len(f.keyframe_points) for f in curves(action)) > 4096:
                raise CreationError('Object animation exceeds 4,096 keys')
    for m in scene_materials:
        if m.use_nodes and (len(m.node_tree.nodes) > 2 or
                any(n.type not in {'BSDF_PRINCIPLED', 'OUTPUT_MATERIAL'} for n in m.node_tree.nodes)):
            raise CreationError('S1 supports the direct Principled material preset only')
    if scene.world and scene.world.use_nodes and (len(scene.world.node_tree.nodes) > 2 or
            any(n.type not in {'BACKGROUND', 'OUTPUT_WORLD'} for n in scene.world.node_tree.nodes)):
        raise CreationError('S1 supports the direct Background world preset only')
    object_seen, material_seen = set(), set()
    for o in sorted(scene.objects, key=lambda o: o.name):
        identity(o, OBJECT_ID, object_seen)
    materials = []
    for m in sorted(scene_materials, key=lambda m: m.name):
        mid = identity(m, MATERIAL_ID, material_seen)
        shader = m.node_tree.nodes.get('Principled BSDF') if m.use_nodes else None
        materials.append({'id': mid, 'name': m.name, 'color': list(shader.inputs['Base Color'].default_value)
                          if shader else list(m.diffuse_color),
                          'roughness': shader.inputs['Roughness'].default_value if shader else m.roughness,
                          'metallic': shader.inputs['Metallic'].default_value if shader else m.metallic,
                          'creation_provenance': str(m.get('finalverse.created_by', ''))[:512],
                          'provenance': str(m.get('finalverse.provenance', ''))[:512],
                          'graph': node_state(m.node_tree) if m.use_nodes else None})
    objects = []
    for o in sorted(scene.objects, key=lambda o: o[OBJECT_ID]):
        mesh_hash = None
        if o.type == 'MESH':
            h = hashlib.sha256()
            for v in o.data.vertices:
                h.update(struct.pack('<3f', *v.co))
            for poly in o.data.polygons:
                h.update(struct.pack('<I', len(poly.vertices)))
                for i in poly.vertices:
                    h.update(struct.pack('<I', i))
            mesh_hash = h.hexdigest()
        animation = []
        action = o.animation_data.action if o.animation_data else None
        for curve in curves(action):
            animation.append({'path': curve.data_path, 'index': curve.array_index,
                'keys': [[*k.co, k.interpolation] for k in curve.keyframe_points]})
        if o.type == 'MESH':
            attr = o.data.attributes.get('fv_part')
            if attr is not None:
                h = hashlib.sha256(struct.pack(f'<{len(attr.data)}i', *[a.value for a in attr.data]))
                mesh_hash = hashlib.sha256((mesh_hash + h.hexdigest()).encode()).hexdigest()
            mesh_hash = hashlib.sha256((mesh_hash + ''.join(str(p.material_index) for p in o.data.polygons)).encode()).hexdigest()
        item = {'id': o[OBJECT_ID], 'name': o.name, 'type': o.type,
                'parent': o.parent.get(OBJECT_ID) if o.parent else None,
                'location': list(o.location), 'rotation': list(o.rotation_euler), 'scale': list(o.scale),
                'geometry': mesh_hash, 'vertices': len(o.data.vertices) if o.type == 'MESH' else 0,
                'materials': [m[MATERIAL_ID] for m in o.data.materials if m] if hasattr(o.data, 'materials') else [],
                'animations': animation, 'description': str(o.get('finalverse.description', ''))[:512],
                'creation_provenance': str(o.get('finalverse.created_by', ''))[:512],
                'provenance': str(o.get('finalverse.provenance', ''))[:512]}
        item['hidden'] = [o.hide_render, o.hide_viewport]
        item['clips'] = animation_state(o)
        if o.get('finalverse.parts'):
            item['parts'] = str(o['finalverse.parts'])[:8192]
        if o.type == 'MESH':
            item['skin'] = {'weights': weights_hash(o) if o.vertex_groups else None,
                            'modifiers': [[m.type, m.object.get(OBJECT_ID) if m.object else None] for m in o.modifiers]}
        if o.type == 'ARMATURE':
            item['bones'] = [[b.name, b.parent.name if b.parent else None, list(b.head_local), list(b.tail_local)]
                             for b in o.data.bones]
            item['pose'] = [[b.name, list(b.location), list(b.rotation_euler), list(b.scale)] for b in o.pose.bones]
        if o.type == 'LIGHT':
            item['light'] = [o.data.type, o.data.energy, list(o.data.color), getattr(o.data, 'size', None)]
        if o.type == 'CAMERA':
            item['lens'] = o.data.lens
        objects.append(item)
    sid = scene.get('finalverse.scene_id')
    try:
        uuid.UUID(sid)
    except (ValueError, TypeError, AttributeError):
        sid = str(uuid.uuid4()); scene['finalverse.scene_id'] = sid
    result = {'schema_version': 'finalverse.studio-scene/v2', 'scene_id': sid, 'objects': objects,
              'materials': materials, 'camera': scene.camera.get(OBJECT_ID) if scene.camera else None,
              'frame': scene.frame_current, 'frame_range': [scene.frame_start, scene.frame_end],
              'render': [scene.render.engine, scene.render.fps, scene.render.film_transparent,
                         scene.view_settings.view_transform],
              'world': node_state(scene.world.node_tree) if scene.world and scene.world.use_nodes else None}
    result['revision'] = digest(result)
    return result


def find_object(scene, target, aliases):
    target = aliases.get(target, target)
    matches = [o for o in scene.objects if o.get(OBJECT_ID) == target]
    if len(matches) != 1:
        raise CreationError("Object reference is missing or ambiguous")
    return matches[0]


def preflight(scene, plan):
    validate(plan)
    index = snapshot(scene)
    kinds = {o['id']: o['type'] for o in index['objects']}
    mats = {m['id'] for m in index['materials']}
    created = 0
    actions = {a.get('finalverse.action_id') for a in bpy.data.actions if a.get('finalverse.action_id')}
    needs_mesh = {'mesh.bevel', 'material.assign', 'material.assign_parts', 'mesh.subdivide', 'mesh.deform'}
    for item in plan['operations']:
        name = item['op']
        if name in CREATES:
            kinds[item['ref']] = CREATES[name]
            created += 3 if name == 'light.rig' else 1
        if name in MATERIAL_CREATES:
            mats.add(item['ref'])
        if name in ACTION_CREATES:
            actions.add(item['ref'])
        for field in ('target', 'parent', 'surface', 'instance', 'armature', 'subject', 'source'):
            if isinstance(item.get(field), str) and not (name == 'action.retarget' and field == 'action') and item[field] not in kinds:
                raise CreationError("Plan targets an unknown scene object")
        if name in needs_mesh and kinds.get(item['target']) != 'MESH':
            raise CreationError("Operation requires a mesh object")
        if name in {'geonodes.scatter'} and (kinds.get(item['surface']) != 'MESH' or kinds.get(item['instance']) != 'MESH'):
            raise CreationError("Scatter requires mesh surface and instance")
        if name == 'armature.skin' and (kinds.get(item['target']) != 'MESH' or kinds.get(item['armature']) != 'ARMATURE'):
            raise CreationError("Skinning needs a mesh and an armature")
        if name == 'action.retarget' and (item['action'] not in actions or kinds.get(item['source']) != 'ARMATURE'
                                          or kinds.get(item['target']) != 'ARMATURE'):
            raise CreationError("Retarget needs an existing action and two armatures")
        if name == 'asset.package' and any(c not in actions for c in item['clips']):
            raise CreationError("Package clips must be existing actions")
        if name == 'mesh.bevel' and not item['target'].startswith('@'):
            if len(find_object(scene, item['target'], {}).data.vertices) > 2000:
                raise CreationError("Bevel input exceeds the 2,000 vertex limit")
        if name == 'camera.configure' and (Vector(item['look_at'])-Vector(item['location'])).length < .001:
            raise CreationError("Camera must look away from its location")
        if name in {'material.assign', 'material.assign_parts'} and item['material'] not in mats:
            raise CreationError("Unknown material reference")
    if len(scene.objects) + created > 256:
        raise CreationError("Plan exceeds the object limit")


def _provenance(block, job, created=False):
    value = canonical({'job': job['id'], 'plan': job['digest'], 'protocol': job['plan']['schema_version']})
    block['finalverse.provenance'] = value
    if created:
        block['finalverse.created_by'] = value
        block['finalverse.description'] = job['plan']['summary']


V1_BRIDGE = {'scene.inspect', 'object.create', 'material.create', 'camera.configure', 'light.configure',
             'object.transform', 'animation.keyframe', 'mesh.bevel', 'material.assign', 'scene.save', 'asset.export'}


def apply(scene, item, aliases, directory, job):
    name = item['op']
    if job['plan'].get('schema_version') == SCHEMA_V2 and name not in V1_BRIDGE:
        from . import creation2
        block, result = creation2.apply(scene, item, aliases, directory, job)
        stamps = [block] if block is not None else []
        if name == 'light.rig':
            stamps = [o for o in scene.objects if o.get(OBJECT_ID) in result['lights']]
        for b in stamps:
            _provenance(b, job, name not in {'mesh.subdivide', 'mesh.deform', 'object.parent', 'material.assign_parts',
                                             'armature.skin'})
        bpy.context.view_layer.update()
        return {'operation': name, **result}
    if name == 'scene.inspect':
        index = snapshot(scene)
        return {'scene_id': index['scene_id'], 'revision': index['revision'],
                'objects': len(index['objects']), 'materials': len(index['materials'])}
    if name == 'object.create':
        creators = {'cube': lambda: bpy.ops.mesh.primitive_cube_add(size=2),
                    'sphere': lambda: bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12),
                    'cylinder': lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=24),
                    'plane': lambda: bpy.ops.mesh.primitive_plane_add(size=2)}
        creators[item['primitive']]()
        block = bpy.context.object; block.name = item['name']
        block[OBJECT_ID] = str(uuid.uuid4()); aliases[item['ref']] = block[OBJECT_ID]
    elif name == 'material.create':
        block = bpy.data.materials.new(item['name']); block.use_nodes = True
        block[MATERIAL_ID] = str(uuid.uuid4()); aliases[item['ref']] = block[MATERIAL_ID]
        shader = block.node_tree.nodes.get('Principled BSDF')
        for key, value in [('Base Color', item['color']), ('Roughness', item['roughness']), ('Metallic', item['metallic'])]:
            shader.inputs[key].default_value = value
        block.diffuse_color = item['color']
    elif name in {'camera.configure', 'light.configure'}:
        if name == 'camera.configure':
            data = bpy.data.cameras.new(item['name']); data.lens = item['lens']
        else:
            data = bpy.data.lights.new(item['name'], item['kind']); data.energy = item['energy']; data.color = item['color']
        block = bpy.data.objects.new(item['name'], data); scene.collection.objects.link(block)
        block.location = item['location']; block[OBJECT_ID] = str(uuid.uuid4()); aliases[item['ref']] = block[OBJECT_ID]
        if name == 'camera.configure':
            direction = Vector(item['look_at']) - block.location
            if direction.length < .001:
                raise CreationError("Camera must look away from its location")
            block.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler(); scene.camera = block
    elif name in {'object.transform', 'animation.keyframe'}:
        block = find_object(scene, item['target'], aliases)
        if name == 'animation.keyframe':
            scene.frame_set(item['frame'])
        for field, attr in [('location', 'location'), ('rotation', 'rotation_euler'), ('scale', 'scale')]:
            if field in item:
                setattr(block, attr, item[field])
                if name == 'animation.keyframe':
                    block.keyframe_insert(data_path=attr, frame=item['frame'])
        if name == 'animation.keyframe':
            scene.frame_end = max(item['frame'], int(scene.get('finalverse.animation_end', 1)))
            scene['finalverse.animation_end'] = scene.frame_end
            for curve in curves(block.animation_data.action):
                for key in curve.keyframe_points:
                    key.interpolation = 'LINEAR'
    elif name == 'mesh.bevel':
        block = find_object(scene, item['target'], aliases)
        if len(block.data.vertices) > 2000 or len(block.data.polygons) > 4000:
            raise CreationError('Bevel input exceeds its per-operation geometry budget')
        bpy.ops.object.select_all(action='DESELECT'); block.select_set(True); bpy.context.view_layer.objects.active = block
        modifier = block.modifiers.new('Finalverse bounded bevel', 'BEVEL')
        modifier.width = item['width']; modifier.segments = item['segments']
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    elif name == 'material.assign':
        block = find_object(scene, item['target'], aliases)
        mid = aliases.get(item['material'], item['material'])
        matches = [m for m in bpy.data.materials if m.get(MATERIAL_ID) == mid]
        if len(matches) != 1:
            raise CreationError("Material reference is missing or ambiguous")
        block.data.materials.clear(); block.data.materials.append(matches[0])
    elif name == 'scene.save':
        path = directory/item['path']
        if path.exists() or path.is_symlink():
            raise CreationError("Existing output refused")
        bpy.ops.wm.save_as_mainfile(filepath=str(path), copy=True)
        return {'path': path.name, 'bytes': path.stat().st_size}
    elif name == 'asset.export':
        from bl_ui.finalverse_studio import export_candidate
        result = export_candidate(directory/item['path'], scene)
        return {'path': item['path'], 'assets': result['assets'], 'published': False}
    else:
        raise CreationError("Operation is not handled by the main-thread bridge")
    _provenance(block, job, name in {'object.create', 'material.create', 'camera.configure', 'light.configure'})
    bpy.context.view_layer.update()
    return {'id': block.get(OBJECT_ID) or block.get(MATERIAL_ID), 'operation': name}
