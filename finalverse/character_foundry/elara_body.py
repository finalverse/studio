"""CF1 Elara: body stage (MakeHuman CC0 base, targets, skeleton, relaxed rest pose)."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

import cf_rig as RG
from cf_mh import MHBase

TARGETS = [
    ('caucasian-female-young', 1.0),
    ('female-young-averagemuscle-averageweight-idealproportions', 0.6),
    ('universal-female-young-averagemuscle-minweight', 0.3),
]
HEIGHT = 1.72          # canon height_mm 1720
SOLE = 0.014           # boot sole thickness; body is lifted by this much


def stylize(mh):
    """Small, deliberate stylisation: eyes 8% larger, slightly fuller lips region kept."""
    co = mh.co
    for side in ('l', 'r'):
        c = mh.joint(f'helper-{side}-eye')
        d = co - c
        r = np.linalg.norm(d, axis=1)
        w = np.clip(1 - r / 0.030, 0, 1) ** 2
        co += d * (0.08 * w)[:, None]


def build_body(scene):
    mh = MHBase(TARGETS)
    mh.fit_height(HEIGHT)
    stylize(mh)
    mh.co[:, 2] += SOLE
    mh.co[:, 1] -= 0.5 * (mh.joint('joint-l-ankle')[1] + mh.joint('joint-r-ankle')[1])
    # one full mesh (body + helpers) so helpers follow the rest-pose change
    allg = tuple(sorted(set(mh.groups)))
    me, used, remap = mh.body_mesh('mh-full', allg)
    full = bpy.data.objects.new('mh-full', me); scene.collection.objects.link(full)
    rig = mh.build_armature(scene)
    mh.apply_weights(full, remap)
    RG.bind(full, rig)
    relaxed_pose(rig)
    RG.apply_pose_as_rest(rig, [full])
    co = np.zeros(len(full.data.vertices) * 3); full.data.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    for v, k in remap.items():
        mh.co[v] = co[k]
    bpy.data.objects.remove(full)
    # final body mesh
    bme, bused, bremap = mh.body_mesh('Elara_Body', ('body',))
    body = bpy.data.objects.new('Elara_Body', bme); scene.collection.objects.link(body)
    mh.apply_weights(body, bremap)
    RG.normalize_weights(body, limit=4)
    RG.bind(body, rig)
    rig.name = 'Elara_Rig'; rig.data.name = 'Elara_Rig'
    mh.body_remap = bremap
    return mh, rig, body


def relaxed_pose(rig):
    """Arms down ~14 deg from the body, slight elbow bend: the authoring rest pose.
    Garments are built and cloth-simulated in this pose."""
    for s, sx in (('L', 1), ('R', -1)):
        RG.aim_bone(rig, f'upperarm01.{s}', (sx * math.sin(math.radians(14)), 0.03, -1))
        RG.aim_bone(rig, f'lowerarm01.{s}', (sx * math.sin(math.radians(9)), -0.16, -1))
        # palms toward the thighs
        pb = rig.pose.bones[f'lowerarm01.{s}']
        axis = (pb.tail - pb.head).normalized()
        RG.pose_world_rotate(rig, f'lowerarm01.{s}', Quaternion(axis, math.radians(-12 * sx)))
        RG.aim_bone(rig, f'wrist.{s}', (sx * 0.05, -0.12, -1))
