# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""S2 typed creation tools. Main thread only. Every tool is a fixed Blender
implementation selected by a validated finalverse.creation/v2 operation; no
model-provided code, node graphs, bone lists or file paths are interpreted."""
import json
import math
import random
import re
import uuid

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

from .protocol import CreationError

OBJECT_ID = 'finalverse.object_id'
MATERIAL_ID = 'finalverse.material_id'
ACTION_ID = 'finalverse.action_id'
PARTS = 'finalverse.parts'          # JSON list [[name, category], ...] indexed by face attribute fv_part
PART_ATTR = 'fv_part'
MAX_OBJECT_VERTICES = 100000

# E1 joint templates (Blender Z-up, metres, as fractions of height). Names match
# the accepted E1 universal-embodiment skeletons so exported rigs stay comparable.
TEMPLATES = {
    'humanoid_basic': [('root', None, (0, 0, .48), (0, 0, .70)), ('head', 0, (0, 0, .80), (0, 0, 1.0)),
                       ('arm_l', 0, (.14, 0, .74), (.20, 0, .42)), ('arm_r', 0, (-.14, 0, .74), (-.20, 0, .42)),
                       ('leg_l', 0, (.065, 0, .48), (.065, 0, .04)), ('leg_r', 0, (-.065, 0, .48), (-.065, 0, .04))],
    'tree_basic': [('trunk', None, (0, 0, 0), (0, 0, .55)), ('branch_l', 0, (0, 0, .55), (-.25, 0, .8)),
                   ('branch_r', 0, (0, 0, .55), (.25, 0, .8)), ('canopy', 0, (0, 0, .8), (0, 0, 1.0))],
}
TEMPLATES['synthetic_basic'] = TEMPLATES['humanoid_basic']
TEMPLATES['fire_basic'] = TEMPLATES['humanoid_basic']


# --- small deterministic mesh builder --------------------------------------
class Builder:
    def __init__(self):
        self.bm = bmesh.new()
        self.layer = self.bm.faces.layers.int.new(PART_ATTR)
        self.parts = []

    def part(self, name, category):
        self.parts.append([name, category]); return len(self.parts)-1

    def _tag(self, faces, index):
        for f in faces:
            f[self.layer] = index

    def ellipsoid(self, name, category, centre, radii, segments=24, rings=12):
        index = self.part(name, category)
        geom = bmesh.ops.create_uvsphere(self.bm, u_segments=segments, v_segments=rings, radius=1)
        verts = geom['verts']
        bmesh.ops.transform(self.bm, matrix=Matrix.Translation(centre) @ Matrix.Diagonal((*radii, 1)), verts=verts)
        self._tag({f for v in verts for f in v.link_faces}, index)
        return index

    def frustum(self, name, category, a, b, r1, r2, segments=16):
        index = self.part(name, category)
        a, b = Vector(a), Vector(b); d = b-a
        if d.length < 1e-5:
            raise CreationError('Degenerate generated segment')
        geom = bmesh.ops.create_cone(self.bm, cap_ends=True, segments=segments, radius1=r1, radius2=max(r2, 1e-4),
                                     depth=d.length)
        rot = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        bmesh.ops.transform(self.bm, matrix=Matrix.Translation((a+b)/2) @ rot, verts=geom['verts'])
        self._tag({f for v in geom['verts'] for f in v.link_faces}, index)
        return index

    def box(self, name, category, centre, size):
        index = self.part(name, category)
        geom = bmesh.ops.create_cube(self.bm, size=1)
        bmesh.ops.transform(self.bm, matrix=Matrix.Translation(centre) @ Matrix.Diagonal((*size, 1)), verts=geom['verts'])
        self._tag({f for v in geom['verts'] for f in v.link_faces}, index)
        return index

    def prism(self, name, category, centre, width, depth, height):
        """Gable roof: triangular prism along Y."""
        index = self.part(name, category)
        x, y, z = centre; w, d, h = width/2, depth/2, height
        co = [(x-w, y-d, z), (x+w, y-d, z), (x, y-d, z+h), (x-w, y+d, z), (x+w, y+d, z), (x, y+d, z+h)]
        v = [self.bm.verts.new(c) for c in co]
        faces = [self.bm.faces.new(f) for f in ((v[0], v[2], v[1]), (v[3], v[4], v[5]), (v[0], v[1], v[4], v[3]),
                                                 (v[1], v[2], v[5], v[4]), (v[2], v[0], v[3], v[5]))]
        self._tag(faces, index)
        return index

    def finish(self, scene, name, location=(0, 0, 0)):
        if len(self.bm.verts) > MAX_OBJECT_VERTICES:
            self.bm.free(); raise CreationError('Generated geometry exceeds 100,000 vertices')
        # BMesh face storage order is not stable across runs, so the mesh is rebuilt
        # canonically: vertices in creation order, each face rotated to its lowest
        # vertex index (winding kept) and faces sorted by (part, vertices).
        bm = self.bm; bm.verts.index_update()
        coords = [tuple(round(c, 7) for c in v.co) for v in bm.verts]
        faces = []
        for f in bm.faces:
            ids = [v.index for v in f.verts]; k = ids.index(min(ids))
            faces.append((f[self.layer], tuple(ids[k:] + ids[:k])))
        bm.free()
        faces.sort()
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(coords, [], [f for _, f in faces]); mesh.update()
        attr = mesh.attributes.new(PART_ATTR, 'INT', 'FACE')
        attr.data.foreach_set('value', [p for p, _ in faces])
        for poly in mesh.polygons:
            poly.use_smooth = True
        block = bpy.data.objects.new(name, mesh); scene.collection.objects.link(block)
        block.location = location; block[PARTS] = json.dumps(self.parts)
        return block


def new_identity(block, key, aliases, ref):
    block[key] = str(uuid.uuid4()); aliases[ref] = block[key]


def find(scene, target, aliases, kind=None):
    target = aliases.get(target, target)
    matches = [o for o in scene.objects if o.get(OBJECT_ID) == target]
    if len(matches) != 1:
        raise CreationError('Object reference is missing or ambiguous')
    if kind and matches[0].type != kind:
        raise CreationError(f'Operation requires a {kind.lower()} object')
    return matches[0]


def find_action(target, aliases):
    target = aliases.get(target, target)
    matches = [a for a in bpy.data.actions if a.get(ACTION_ID) == target]
    if len(matches) != 1:
        raise CreationError('Action reference is missing or ambiguous')
    return matches[0]


def find_material(target, aliases):
    target = aliases.get(target, target)
    matches = [m for m in bpy.data.materials if m.get(MATERIAL_ID) == target]
    if len(matches) != 1:
        raise CreationError('Material reference is missing or ambiguous')
    return matches[0]


def activate(block):
    bpy.ops.object.select_all(action='DESELECT'); block.select_set(True)
    bpy.context.view_layer.objects.active = block


def apply_modifier(block, modifier):
    activate(block)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    if len(block.data.vertices) > MAX_OBJECT_VERTICES:
        raise CreationError('Result exceeds 100,000 vertices')


# --- generators -------------------------------------------------------------
def spirit(scene, item):
    """Floating spirit anatomy (E1 floating_spirit): continuous body, crown, fins, eyes.
    No skeleton, no legs, no feet; the silhouette floats above its origin."""
    h = item['height']; w = item.get('body_width', 1.0); crown = item.get('crown', 1.0)
    fins = item.get('fins', 1.0); eyes = item.get('eyes', 1.0)
    b = Builder()
    b.ellipsoid('continuous spirit body', 'body', (0, 0, h*.38), (h*.29*w, h*.24*w, h*.34), 32, 16)
    if crown > 0:
        b.ellipsoid('rounded spirit crown', 'crown', (0, 0, h*.72), (h*.36*w*crown**.5, h*.27*w*crown**.5, h*.27), 32, 16)
        b.frustum('tapered spirit crown', 'crown', (0, 0, h*.86), (0, 0, h*(.86+.22*crown)), h*.16*crown**.5, h*.01)
    if fins > 0:
        for sign in (1, -1):
            b.ellipsoid('soft crown fin', 'fins', (sign*h*.36*w, 0, h*.66), (h*.17*fins, h*.10*fins, h*.10*fins), 16, 8)
            b.ellipsoid('subtle side fin', 'fins', (sign*h*.29*w, 0, h*.32), (h*.05*fins, h*.045*fins, h*.10*fins), 12, 6)
    for sign in (1, -1):
        x = sign*h*.105*w; y = -h*.245*w; z = h*.60
        b.ellipsoid('eye white', 'eyes', (x, y, z), (h*.07*eyes, h*.03*eyes, h*.085*eyes), 16, 8)
        b.ellipsoid('eye pupil', 'eyes', (x, y-h*.022*eyes, z-h*.005), (h*.042*eyes, h*.02*eyes, h*.055*eyes), 12, 6)
    return b.finish(scene, item['name'], item.get('location', (0, 0, 0)))


def humanoid(scene, item):
    h = item['height']; synthetic = item['build'] == 'synthetic'
    b = Builder()
    b.ellipsoid('head', 'body', (0, 0, h*.90), (h*.075, h*.085, h*.095))
    b.ellipsoid('torso', 'body', (0, 0, h*.64), (h*.13, h*.08, h*.17))
    b.ellipsoid('pelvis', 'body', (0, 0, h*.49), (h*.115, h*.075, h*.07))
    for sign in (1, -1):
        b.frustum('upper arm', 'body', (sign*h*.15, 0, h*.75), (sign*h*.18, 0, h*.58), h*.035, h*.03)
        b.frustum('forearm', 'body', (sign*h*.18, 0, h*.58), (sign*h*.20, 0, h*.43), h*.03, h*.025)
        b.ellipsoid('hand', 'body', (sign*h*.20, 0, h*.40), (h*.025, h*.02, h*.04))
        b.frustum('thigh', 'body', (sign*h*.065, 0, h*.47), (sign*h*.065, 0, h*.26), h*.05, h*.04)
        b.frustum('shin', 'body', (sign*h*.065, 0, h*.26), (sign*h*.065, 0, h*.06), h*.04, h*.03)
        b.box('foot', 'body', (sign*h*.065, -h*.03, h*.025), (h*.06, h*.13, h*.05))
    if synthetic:
        for z in (.55, .65, .75):
            b.ellipsoid('core light', 'eyes', (0, -h*.075, h*z), (h*.02, h*.01, h*.02), 12, 6)
    else:
        for sign in (1, -1):
            b.ellipsoid('eye', 'eyes', (sign*h*.03, -h*.075, h*.915), (h*.012, h*.008, h*.012), 12, 6)
    return b.finish(scene, item['name'], item.get('location', (0, 0, 0)))


def building(scene, item):
    rng = random.Random(item['seed'])
    w, d, fh, floors = item['width'], item['depth'], item['floor_height'], item['floors']
    b = Builder(); total = fh*floors
    b.box('walls', 'walls', (0, 0, total/2), (w, d, total))
    for floor in range(floors):
        b.box('floor band', 'walls', (0, 0, floor*fh + .08), (w*1.01, d*1.01, .16))
        columns = item['window_columns']
        for c in range(columns):
            x = -w/2 + w*(c+.5)/columns
            for y, sign in ((-d/2, -1), (d/2, 1)):
                height = fh*rng.uniform(.42, .52)
                b.box('window', 'windows', (x, y + sign*.02, floor*fh + fh*.55), (w/columns*.55, .06, height))
    if item['roof'] == 'gable':
        b.prism('gable roof', 'roof', (0, 0, total), w*1.04, d*1.04, min(w, d)*.35)
    else:
        b.box('flat roof parapet', 'roof', (0, 0, total + .15), (w*1.02, d*1.02, .3 + rng.uniform(0, .2)))
    return b.finish(scene, item['name'], item['location'])


def tree(scene, item):
    rng = random.Random(item['seed']); h = item['height']; r = item['trunk_radius']; kind = item['kind']
    b = Builder()
    if kind == 'conifer':
        b.frustum('trunk', 'trunk', (0, 0, 0), (0, 0, h*.35), r, r*.7, 12)
        tiers = 3 + item['branches'] % 3
        for i in range(tiers):
            z0 = h*(.2 + .75*i/tiers); radius = h*.32*(1 - i/(tiers+1))
            b.frustum('needle tier', 'canopy', (0, 0, z0), (0, 0, z0 + h*.35), radius, h*.01, 16)
    else:
        trunk_h = h*(.55 if kind == 'broadleaf' else .2)
        b.frustum('trunk', 'trunk', (0, 0, 0), (0, 0, trunk_h), r, r*.6, 12)
        top = Vector((0, 0, trunk_h))
        for i in range(item['branches']):
            angle = i*math.tau/max(1, item['branches']) + rng.uniform(-.3, .3)
            lift = rng.uniform(.35, .75)
            tip = top + Vector((math.cos(angle)*h*.22, math.sin(angle)*h*.22, h*.18*lift))
            b.frustum('branch', 'trunk', top - Vector((0, 0, h*.05)), tip, r*.45, r*.15, 8)
            b.ellipsoid('leaf cluster', 'canopy', tip, (h*.14, h*.14, h*.11), 12, 6)
        crown_z = trunk_h + h*(.2 if kind == 'broadleaf' else .1)
        size = h*(.28 if kind == 'broadleaf' else .35)
        for i in range(3):
            offset = Vector((rng.uniform(-.1, .1)*h, rng.uniform(-.1, .1)*h, rng.uniform(0, .12)*h))
            b.ellipsoid('canopy', 'canopy', Vector((0, 0, crown_z)) + offset, (size, size, size*.8), 16, 8)
    return b.finish(scene, item['name'], item['location'])


def scatter(scene, item, aliases):
    """Geometry Nodes: Distribute Points on Faces → Instance on Points → Realize,
    built from a fixed node recipe and applied, so the result is inspectable mesh."""
    surface = find(scene, item['surface'], aliases, 'MESH'); instance = find(scene, item['instance'], aliases, 'MESH')
    if surface == instance:
        raise CreationError('Scatter surface and instance must differ')
    estimate = len(instance.data.vertices) * item['count']
    if estimate > MAX_OBJECT_VERTICES:
        raise CreationError('Scatter result would exceed 100,000 vertices')
    area = sum(p.area for p in surface.data.polygons) * max(surface.scale)**2
    if area <= 0:
        raise CreationError('Scatter surface has no area')
    mesh = bpy.data.meshes.new(item['name']); block = bpy.data.objects.new(item['name'], mesh)
    scene.collection.objects.link(block); block.matrix_world = surface.matrix_world.copy()
    tree = bpy.data.node_groups.new('Finalverse scatter ' + item['name'], 'GeometryNodeTree')
    tree.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    n = tree.nodes; link = tree.links.new
    source = n.new('GeometryNodeObjectInfo'); source.inputs['Object'].default_value = surface
    source.transform_space = 'ORIGINAL'
    points = n.new('GeometryNodeDistributePointsOnFaces'); points.distribute_method = 'RANDOM'
    points.inputs['Density'].default_value = item['count'] / area
    points.inputs['Seed'].default_value = item['seed']
    proto = n.new('GeometryNodeObjectInfo'); proto.inputs['Object'].default_value = instance
    proto.inputs['As Instance'].default_value = True
    def socket(sockets, name, kind):
        return next(s for s in sockets if s.name == name and s.type == kind)
    scale = n.new('FunctionNodeRandomValue'); scale.data_type = 'FLOAT'
    socket(scale.inputs, 'Min', 'VALUE').default_value = item['scale_min']
    socket(scale.inputs, 'Max', 'VALUE').default_value = item['scale_max']
    scale.inputs['Seed'].default_value = item['seed'] + 1
    turn = n.new('FunctionNodeRandomValue'); turn.data_type = 'FLOAT_VECTOR'
    socket(turn.inputs, 'Min', 'VECTOR').default_value = (0, 0, 0)
    socket(turn.inputs, 'Max', 'VECTOR').default_value = (0, 0, math.tau)
    turn.inputs['Seed'].default_value = item['seed'] + 2
    place = n.new('GeometryNodeInstanceOnPoints')
    realize = n.new('GeometryNodeRealizeInstances'); out = n.new('NodeGroupOutput')
    link(source.outputs['Geometry'], points.inputs['Mesh'])
    link(points.outputs['Points'], place.inputs['Points'])
    link(proto.outputs['Geometry'], place.inputs['Instance'])
    link(socket(scale.outputs, 'Value', 'VALUE'), place.inputs['Scale'])
    link(socket(turn.outputs, 'Value', 'VECTOR'), place.inputs['Rotation'])
    link(place.outputs['Instances'], realize.inputs['Geometry'])
    link(realize.outputs['Geometry'], out.inputs['Geometry'])
    modifier = block.modifiers.new('Finalverse scatter', 'NODES'); modifier.node_group = tree
    for m in instance.data.materials:
        block.data.materials.append(m)
    apply_modifier(block, modifier)
    bpy.data.node_groups.remove(tree)
    block[PARTS] = json.dumps([[item['name'], 'canopy' if '"canopy"' in instance.get(PARTS, '') else 'all']])
    # The prototype is a source, not scenery: hidden from viewport and render.
    instance.hide_render = True; instance.hide_viewport = True
    return block


def primitive(scene, item):
    shape = item['shape']; segments = item.get('segments', 24)
    ops = {'uv_sphere': lambda: bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=max(3, segments//2), radius=.5),
           'ico_sphere': lambda: bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=min(4, max(1, segments//12)), radius=.5),
           'cube': lambda: bpy.ops.mesh.primitive_cube_add(size=1),
           'cylinder': lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=segments, radius=.5, depth=1),
           'cone': lambda: bpy.ops.mesh.primitive_cone_add(vertices=segments, radius1=.5, depth=1),
           'torus': lambda: bpy.ops.mesh.primitive_torus_add(major_segments=segments, minor_segments=max(4, segments//3),
                                                             major_radius=.375, minor_radius=.125),
           'plane': lambda: bpy.ops.mesh.primitive_plane_add(size=1)}
    ops[shape]()
    block = bpy.context.object; block.name = item['name']
    block.data.transform(Matrix.Diagonal((*item.get('size', (1, 1, 1)), 1)))
    block.location = item.get('location', (0, 0, 0)); block.rotation_euler = item.get('rotation', (0, 0, 0))
    return block


# --- materials ----------------------------------------------------------------
def material_preset(item):
    block = bpy.data.materials.new(item['name']); block.use_nodes = True
    shader = block.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = item['color']
    shader.inputs['Roughness'].default_value = item.get('roughness', .5)
    shader.inputs['Metallic'].default_value = item.get('metallic', 0)
    shader.inputs['Emission Color'].default_value = (*item.get('emission', (0, 0, 0)), 1)
    shader.inputs['Emission Strength'].default_value = item.get('emission_strength', 0)
    alpha = item.get('alpha', 1); shader.inputs['Alpha'].default_value = alpha
    if alpha < 1:
        block.surface_render_method = 'BLENDED'
    block.diffuse_color = item['color']
    return block


def assign_parts(scene, item, aliases):
    block = find(scene, item['target'], aliases, 'MESH'); material = find_material(item['material'], aliases)
    mesh = block.data
    if material.name not in [m.name for m in mesh.materials if m]:
        mesh.materials.append(material)
    slot = [m.name if m else None for m in mesh.materials].index(material.name)
    if item['part'] == 'all':
        selected = range(len(mesh.polygons))
    else:
        parts = json.loads(block.get(PARTS, '[]'))
        wanted = {i for i, (_, category) in enumerate(parts) if category == item['part']}
        attr = mesh.attributes.get(PART_ATTR)
        if not wanted or attr is None:
            raise CreationError(f"Object has no {item['part']} parts")
        selected = [i for i, value in enumerate(attr.data) if value.value in wanted]
    for i in selected:
        mesh.polygons[i].material_index = slot
    return block, len(selected)


# --- rigs, skinning, actions --------------------------------------------------
def armature(scene, item):
    h = item['height']
    data = bpy.data.armatures.new(item['name']); block = bpy.data.objects.new(item['name'], data)
    scene.collection.objects.link(block); block.location = item.get('location', (0, 0, 0))
    activate(block); bpy.ops.object.mode_set(mode='EDIT')
    bones = []
    for name, parent, head, tail in TEMPLATES[item['template']]:
        bone = data.edit_bones.new(name); bone.head = Vector(head)*h; bone.tail = Vector(tail)*h
        if parent is not None:
            bone.parent = bones[parent]
        bones.append(bone)
    bpy.ops.object.mode_set(mode='OBJECT')
    block['finalverse.template'] = item['template']
    for pose_bone in block.pose.bones:
        pose_bone.rotation_mode = 'XYZ'
    return block


def skin(scene, item, aliases):
    mesh = find(scene, item['target'], aliases, 'MESH'); rig = find(scene, item['armature'], aliases, 'ARMATURE')
    if mesh.parent or mesh.modifiers:
        raise CreationError('Skin target must be an unparented mesh without modifiers')
    bpy.ops.object.select_all(action='DESELECT'); mesh.select_set(True); rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    kind = 'ARMATURE_AUTO' if item['method'] == 'automatic' else 'ARMATURE_ENVELOPE'
    bpy.ops.object.parent_set(type=kind)
    unweighted = sum(1 for v in mesh.data.vertices if not any(g.weight > 0 for g in v.groups))
    return mesh, {'method': item['method'], 'vertex_groups': len(mesh.vertex_groups), 'unweighted_vertices': unweighted}


CHANNELS = (('location', 'location'), ('rotation', 'rotation_euler'), ('scale', 'scale'))


def _rest(block):
    state = {'object': [tuple(block.location), tuple(block.rotation_euler), tuple(block.scale)]}
    if block.type == 'ARMATURE':
        state['bones'] = {b.name: [tuple(b.location), tuple(b.rotation_euler), tuple(b.scale)] for b in block.pose.bones}
    return state


def _restore(block, state):
    block.location, block.rotation_euler, block.scale = state['object']
    for name, values in state.get('bones', {}).items():
        b = block.pose.bones[name]; b.location, b.rotation_euler, b.scale = values


def _stash(block, action, item_like, name=None):
    """Each clip is its own NLA track, so several clips coexist and export separately.
    A clip name is unique per target: re-creating it replaces the previous clip."""
    ad = block.animation_data
    name = name or action.name
    for old in [t for t in ad.nla_tracks if t.name == name]:
        stale = [s.action for s in old.strips if s.action]
        ad.nla_tracks.remove(old)
        for a in stale:
            if a is not action:
                a.use_fake_user = False
                if a.users == 0:
                    bpy.data.actions.remove(a)
    action.name = name
    track = ad.nla_tracks.new(); track.name = name
    strip = track.strips.new(action.name, int(action.frame_range[0]), action)
    strip.mute = False; track.mute = True
    ad.action = None
    action.use_fake_user = True
    for key, value in item_like.items():
        action['finalverse.' + key] = value


def action_create(scene, item, aliases, rest=None):
    block = find(scene, item['target'], aliases)
    if block.type not in {'MESH', 'ARMATURE', 'CAMERA', 'LIGHT', 'EMPTY'}:
        raise CreationError('Actions target objects or armatures')
    if block.type == 'MESH' and block.parent and block.parent.type == 'ARMATURE':
        raise CreationError('Animate the armature of a skinned mesh, not the mesh itself')
    state = _rest(block)
    action = bpy.data.actions.new(item['name'])
    block.animation_data_create(); block.animation_data.action = action
    for key in item['keys']:
        holder = block
        if 'bone' in key:
            if block.type != 'ARMATURE' or key['bone'] not in block.pose.bones:
                raise CreationError('Bone key requires an existing bone of the target armature')
            holder = block.pose.bones[key['bone']]; holder.rotation_mode = 'XYZ'
        for field, attr in CHANNELS:
            if field in key:
                setattr(holder, attr, Vector(key[field]))  # object keys are absolute; bone keys are pose-local
                holder.keyframe_insert(data_path=attr, frame=key['frame'], group=key.get('bone', 'Object'))
    _restore(block, state)
    action[ACTION_ID] = str(uuid.uuid4()); aliases[item['ref']] = action[ACTION_ID]
    _stash(block, action, {'kind': item['kind'], 'locomotion': item['locomotion'], 'loop': item['loop'],
                           'target': block[OBJECT_ID]}, item['name'])
    return action, block


BONE_PATH = re.compile(r'^pose\.bones\["([^"\\]{1,48})"\]\.(location|rotation_euler|scale)$')


def action_retarget(scene, item, aliases):
    source_action = find_action(item['action'], aliases)
    source = find(scene, item['source'], aliases, 'ARMATURE'); target = find(scene, item['target'], aliases, 'ARMATURE')
    mapping = dict(item['bone_map'])
    if len(mapping) != len(item['bone_map']) or any(s not in source.pose.bones for s in mapping) or \
            any(t not in target.pose.bones for t in mapping.values()):
        raise CreationError('Bone map must name existing source and target bones once each')
    from .engine import curves
    ratio = target.data.bones[0].length / max(source.data.bones[0].length, 1e-6)
    state = _rest(target)
    action = bpy.data.actions.new(item['name'])
    target.animation_data_create(); target.animation_data.action = action
    copied = 0
    for curve in curves(source_action):
        match = BONE_PATH.match(curve.data_path)
        if not match or match.group(1) not in mapping:
            continue
        bone = target.pose.bones[mapping[match.group(1)]]; bone.rotation_mode = 'XYZ'
        prop = match.group(2)
        for point in curve.keyframe_points:
            value = point.co[1] * (ratio if prop == 'location' else 1)
            getattr(bone, prop)[curve.array_index] = value
            bone.keyframe_insert(data_path=prop, index=curve.array_index, frame=point.co[0], group=bone.name)
            copied += 1
    _restore(target, state)
    if not copied:
        target.animation_data.action = None; bpy.data.actions.remove(action)
        raise CreationError('No mapped bone channels to retarget')
    action[ACTION_ID] = str(uuid.uuid4()); aliases[item['ref']] = action[ACTION_ID]
    meta = {k: source_action.get('finalverse.' + k) for k in ('kind', 'locomotion', 'loop')}
    _stash(target, action, {**meta, 'target': target[OBJECT_ID], 'retargeted_from': source_action[ACTION_ID],
                            'length_ratio': ratio}, item['name'])
    return action, target, copied


# --- lighting and render configuration ----------------------------------------
def light_rig(scene, item, aliases):
    target = Vector(item['target']); dist = item['distance']; energy = item['energy']
    layouts = {'three_point': [('Key', (-.6, -1, .7), 1.0, 2.0), ('Fill', (.8, -.8, .3), .35, 3.0), ('Rim', (.2, 1, .9), .6, 1.0)],
               'soft_key': [('Key', (-.5, -1, .8), 1.0, 4.0), ('Fill', (1, -.4, .2), .2, 4.0)],
               'rim': [('Rim', (0, 1, .6), 1.0, 1.5)]}[item['style']]
    created = []
    for label, direction, share, size in layouts:
        data = bpy.data.lights.new(f"{item['name']} {label}", 'AREA')
        data.energy = energy*share; data.color = item['color']; data.size = size
        block = bpy.data.objects.new(data.name, data); scene.collection.objects.link(block)
        block.location = target + Vector(direction).normalized()*dist
        block.rotation_euler = (target - block.location).to_track_quat('-Z', 'Y').to_euler()
        block[OBJECT_ID] = str(uuid.uuid4()); created.append(block)
    aliases[item['ref']] = created[0][OBJECT_ID]
    return created


def render_configure(scene, item):
    scene.render.engine = 'BLENDER_EEVEE'
    scene.frame_start = item['frame_start']; scene.frame_end = item['frame_end']
    scene.render.fps = item['fps']; scene.render.film_transparent = item['transparent']
    if 'view_transform' in item:
        scene.view_settings.view_transform = item['view_transform']
    if scene.world is None:
        scene.world = bpy.data.worlds.new('World')
    world = scene.world; world.use_nodes = True
    background = world.node_tree.nodes.get('Background')
    if 'world_color' in item and background:
        background.inputs['Color'].default_value = (*item['world_color'], 1)
    if 'world_strength' in item and background:
        background.inputs['Strength'].default_value = item['world_strength']
    scene['finalverse.animation_end'] = item['frame_end']
    return {'frame_range': [scene.frame_start, scene.frame_end], 'fps': scene.render.fps,
            'transparent': scene.render.film_transparent}


# --- dispatch ---------------------------------------------------------------
def apply(scene, item, aliases, directory, job):
    """Returns (block_or_None, result_dict). Caller stamps provenance."""
    name = item['op']
    if name in {'character.spirit', 'character.humanoid', 'procedural.building', 'procedural.tree', 'mesh.primitive'}:
        block = {'character.spirit': spirit, 'character.humanoid': humanoid, 'procedural.building': building,
                 'procedural.tree': tree, 'mesh.primitive': primitive}[name](scene, item)
        new_identity(block, OBJECT_ID, aliases, item['ref'])
        return block, {'id': block[OBJECT_ID], 'vertices': len(block.data.vertices),
                       'triangles': sum(len(p.vertices)-2 for p in block.data.polygons),
                       'parts': len(json.loads(block.get(PARTS, '[]')))}
    if name == 'geonodes.scatter':
        block = scatter(scene, item, aliases); new_identity(block, OBJECT_ID, aliases, item['ref'])
        return block, {'id': block[OBJECT_ID], 'vertices': len(block.data.vertices), 'node_recipe': 'distribute-instance-realize/1'}
    if name in {'mesh.subdivide', 'mesh.deform'}:
        block = find(scene, item['target'], aliases, 'MESH')
        if block.parent and block.parent.type == 'ARMATURE':
            raise CreationError('Edit geometry before skinning')
        if name == 'mesh.subdivide':
            if len(block.data.vertices) * 4**item['levels'] > MAX_OBJECT_VERTICES:
                raise CreationError('Subdivision would exceed 100,000 vertices')
            modifier = block.modifiers.new('Finalverse subdivide', 'SUBSURF')
            modifier.levels = item['levels']; modifier.render_levels = item['levels']
        else:
            modifier = block.modifiers.new('Finalverse deform', 'SIMPLE_DEFORM')
            modifier.deform_method = item['kind'].upper(); modifier.deform_axis = item['axis']
            if item['kind'] in {'bend', 'twist'}:
                modifier.angle = item['amount']
            else:
                modifier.factor = item['amount']
        apply_modifier(block, modifier)
        return block, {'id': block[OBJECT_ID], 'vertices': len(block.data.vertices)}
    if name == 'object.parent':
        child = find(scene, item['target'], aliases); parent = find(scene, item['parent'], aliases)
        probe = parent
        while probe:
            if probe == child:
                raise CreationError('Parenting would create a cycle')
            probe = probe.parent
        matrix = child.matrix_world.copy(); child.parent = parent; child.matrix_world = matrix
        return child, {'id': child[OBJECT_ID], 'parent': parent[OBJECT_ID]}
    if name == 'material.preset':
        block = material_preset(item); new_identity(block, MATERIAL_ID, aliases, item['ref'])
        return block, {'id': block[MATERIAL_ID]}
    if name == 'material.assign_parts':
        block, faces = assign_parts(scene, item, aliases)
        return block, {'id': block[OBJECT_ID], 'faces': faces}
    if name == 'armature.create':
        block = armature(scene, item); new_identity(block, OBJECT_ID, aliases, item['ref'])
        return block, {'id': block[OBJECT_ID], 'bones': len(block.data.bones)}
    if name == 'armature.skin':
        block, info = skin(scene, item, aliases)
        return block, {'id': block[OBJECT_ID], **info}
    if name == 'action.create':
        action, block = action_create(scene, item, aliases)
        return action, {'id': action[ACTION_ID], 'target': block[OBJECT_ID], 'keys': len(item['keys'])}
    if name == 'action.retarget':
        action, block, copied = action_retarget(scene, item, aliases)
        return action, {'id': action[ACTION_ID], 'target': block[OBJECT_ID], 'copied_keys': copied}
    if name == 'light.rig':
        blocks = light_rig(scene, item, aliases)
        return blocks[0], {'id': blocks[0][OBJECT_ID], 'lights': [b[OBJECT_ID] for b in blocks]}
    if name == 'render.configure':
        return None, render_configure(scene, item)
    if name == 'asset.package':
        from .package import package
        return None, package(scene, item, aliases, directory, job)
    raise CreationError('Operation is not handled by the S2 bridge')
