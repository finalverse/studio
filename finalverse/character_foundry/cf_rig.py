"""Character Foundry rig helpers: world-axis posing, rest-pose application."""
import math

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector


def pose_world_rotate(rig, bone, q_world):
    """Rotate a pose bone by a world-space quaternion about its head."""
    pb = rig.pose.bones[bone]
    bpy.context.view_layer.update()
    M = pb.matrix.copy()
    loc = M.to_translation()
    R = q_world.to_matrix().to_4x4()
    newM = Matrix.Translation(loc) @ R @ Matrix.Translation(-loc) @ M
    pb.matrix = newM
    bpy.context.view_layer.update()


def aim_bone(rig, bone, target_dir):
    pb = rig.pose.bones[bone]
    bpy.context.view_layer.update()
    cur = (pb.tail - pb.head).normalized()
    q = cur.rotation_difference(Vector(target_dir).normalized())
    pose_world_rotate(rig, bone, q)


def apply_pose_as_rest(rig, meshes):
    """Bake current pose into meshes (armature modifier) and make it the rest pose."""
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in meshes:
        ev = ob.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        old = ob.data
        # keep shape: new_from_object drops vertex groups? (they live on the object)
        ob.data = me
        bpy.data.meshes.remove(old)
    bpy.context.view_layer.objects.active = rig
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode='OBJECT')


def bind(ob, rig, groups_from=None):
    ob.parent = rig
    m = ob.modifiers.get('Armature') or ob.modifiers.new('Armature', 'ARMATURE')
    m.object = rig
    return m


def transfer_weights(src, dst, mapping='POLYINTERP_NEAREST', blur=0, restrict=None):
    """Copy skin weights from src (body) to dst (garment) by nearest surface."""
    for vg in src.vertex_groups:
        if restrict and vg.name not in restrict:
            continue
        if vg.name not in dst.vertex_groups:
            dst.vertex_groups.new(name=vg.name)
    m = dst.modifiers.new('wt', 'DATA_TRANSFER')
    m.object = src
    m.use_vert_data = True
    m.data_types_verts = {'VGROUP_WEIGHTS'}
    m.vert_mapping = mapping
    m.layers_vgroup_select_src = 'ALL'
    m.layers_vgroup_select_dst = 'NAME'
    # move it first, then apply
    with bpy.context.temp_override(object=dst, active_object=dst):
        bpy.ops.object.modifier_move_to_index(modifier=m.name, index=0)
        bpy.ops.object.modifier_apply(modifier=m.name)
    if blur:
        smooth_weights(dst, blur)
    normalize_weights(dst, limit=4)


def weights_array(ob):
    """V x G dense weight matrix."""
    me = ob.data
    G = len(ob.vertex_groups)
    A = np.zeros((len(me.vertices), G), np.float32)
    for v in me.vertices:
        for g in v.groups:
            A[v.index, g.group] = g.weight
    return A


def set_weights_array(ob, A, eps=1e-3):
    for gi, vg in enumerate(ob.vertex_groups):
        col = A[:, gi]
        vg.remove(list(range(len(col))))
        nz = np.nonzero(col > eps)[0]
        for i in nz:
            vg.add([int(i)], float(col[i]), 'REPLACE')


def smooth_weights(ob, iterations, factor=.5):
    me = ob.data
    A = weights_array(ob)
    e = np.zeros(len(me.edges) * 2, np.int64); me.edges.foreach_get('vertices', e); e = e.reshape(-1, 2)
    for _ in range(iterations):
        acc = np.zeros_like(A); cnt = np.zeros(len(A), np.float32)
        np.add.at(acc, e[:, 0], A[e[:, 1]]); np.add.at(acc, e[:, 1], A[e[:, 0]])
        np.add.at(cnt, e[:, 0], 1); np.add.at(cnt, e[:, 1], 1)
        A = A * (1 - factor) + factor * acc / np.maximum(cnt, 1)[:, None]
    set_weights_array(ob, A)


def normalize_weights(ob, limit=4):
    A = weights_array(ob)
    if limit:
        idx = np.argsort(-A, axis=1)[:, limit:]
        np.put_along_axis(A, idx, 0, axis=1)
    s = A.sum(1, keepdims=True)
    A = np.where(s > 0, A / np.maximum(s, 1e-8), A)
    set_weights_array(ob, A)


def rigid_bind(ob, rig, bone):
    for vg in list(ob.vertex_groups):
        ob.vertex_groups.remove(vg)
    vg = ob.vertex_groups.new(name=bone)
    vg.add(list(range(len(ob.data.vertices))), 1.0, 'REPLACE')
    bind(ob, rig)
