"""CF1 Elara: animation library (idle, walk, wave) and facial expressions.

Body motion is authored as analytic FK curves (rotations about rest-pose
armature axes, so they compose naturally down the chain) sampled every frame,
with the root height solved per frame so the lowest foot touches the ground.
Facial expressions blend the MakeHuman CC0 face pose units (60 FACS-like
units in face-poseunits.bvh) onto the face bones; blinks use the lid units.
"""
import math

import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

from cf_mh import MH

FPS = 30
C = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))     # MH (Y-up) -> Blender (Z-up)


# ------------------------------------------------------------- BVH units ----
def load_poseunits():
    import json
    names = json.load(open(f'{MH}/face-poseunits.json'))['framemapping']
    lines = open(f'{MH}/face-poseunits.bvh').read().split('\n')
    joints = []           # (name, channels)
    i = 0
    while not lines[i].strip().startswith('MOTION'):
        t = lines[i].split()
        if t and t[0] in ('ROOT', 'JOINT'):
            name = t[1]
            j = i + 1
            while not lines[j].strip().startswith('CHANNELS'):
                j += 1
            ch = lines[j].split()
            joints.append((name, ch[2:]))
        i += 1
    frames = [list(map(float, l.split())) for l in lines[i + 3:] if l.strip()]
    units = {}
    for fi, uname in enumerate(names):
        vals = frames[fi]; k = 0; rots = {}
        for name, ch in joints:
            v = vals[k:k + len(ch)]; k += len(ch)
            r = {c: x for c, x in zip(ch, v)}
            if not any(c.endswith('rotation') for c in ch):
                continue
            order = ''.join(c[0] for c in ch if c.endswith('rotation'))   # e.g. 'XYZ'
            eul = [math.radians(r[f'{a}rotation']) for a in order]
            M3 = Matrix.Identity(3)
            for a, ang in zip(order, eul):
                M3 = M3 @ Matrix.Rotation(ang, 3, a)
            if abs(M3.to_quaternion().angle) > 1e-4:
                rots[name] = (C @ M3 @ C.inverted()).to_quaternion()
        units[uname] = rots
    return units


EXPRESSIONS = {
    'neutral': {},
    'smile': {'MouthLeftPullUp': .85, 'MouthRightPullUp': .85, 'LeftCheekUp': .55, 'RightCheekUp': .55,
              'LeftLowerLidUp': .25, 'RightLowerLidUp': .25, 'LeftOuterBrowUp': .15, 'RightOuterBrowUp': .15},
    'warm_smile': {'MouthLeftPullUp': .55, 'MouthRightPullUp': .55, 'LeftCheekUp': .35, 'RightCheekUp': .35,
                   'LeftLowerLidUp': .2, 'RightLowerLidUp': .2},
    'curious': {'LeftInnerBrowUp': .5, 'RightInnerBrowUp': .5, 'LeftOuterBrowUp': .6, 'RightOuterBrowUp': .3,
                'LeftUpperLidOpen': .3, 'RightUpperLidOpen': .3, 'JawDrop': .08},
    'blink': {'LeftUpperLidClosed': 1.0, 'RightUpperLidClosed': 1.0, 'LeftLowerLidUp': .3, 'RightLowerLidUp': .3},
}


def expression_quats(units, weights):
    out = {}
    for u, w in weights.items():
        for bone, q in units.get(u, {}).items():
            qw = Quaternion().slerp(q, w)
            out[bone] = qw @ out.get(bone, Quaternion())
    return out


# ------------------------------------------------------------- posing -------
class Poser:
    def __init__(self, rig, units):
        self.rig = rig; self.units = units
        self.B = {b.name: b.matrix_local.to_quaternion() for b in rig.data.bones}
        for pb in rig.pose.bones:
            pb.rotation_mode = 'QUATERNION'

    def clear(self):
        for pb in self.rig.pose.bones:
            pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)

    def rot(self, bone, q_arm):
        """Apply a rotation given about rest armature axes, composed with any existing one."""
        B = self.B[bone]
        ql = B.inverted() @ q_arm @ B
        pb = self.rig.pose.bones[bone]
        pb.rotation_quaternion = pb.rotation_quaternion @ ql

    def axis(self, bone, axis, deg):
        self.rot(bone, Quaternion(Vector(axis), math.radians(deg)))

    def face(self, weights):
        for bone, q in expression_quats(self.units, weights).items():
            if bone in self.rig.pose.bones:
                self.rot(bone, q)

    def key(self, frame):
        for pb in self.rig.pose.bones:
            pb.keyframe_insert('rotation_quaternion', frame=frame, group=pb.name)
        self.rig.pose.bones['root'].keyframe_insert('location', frame=frame, group='root')


X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)


def _new_action(rig, name):
    act = bpy.data.actions.new(name)
    if rig.animation_data is None:
        rig.animation_data_create()
    # Earlier clips sit on NLA tracks. Mute them while authoring, and flush the
    # depsgraph now: otherwise the first view_layer.update() inside the frame loop
    # re-evaluates the NLA and overwrites the frame-0 pose with the previous clip
    # (seen in the CF1 review as a walk pose at frame 0 of the wave).
    for tr in rig.animation_data.nla_tracks:
        tr.mute = True
    rig.animation_data.action = act
    bpy.context.view_layer.update()
    return act


def _foot_min_z(rig):
    bpy.context.view_layer.update()
    zs = []
    for s in ('L', 'R'):
        for b in (f'foot.{s}', f'toe1-1.{s}', f'toe3-1.{s}'):
            pb = rig.pose.bones[b]
            zs.append((rig.matrix_world @ pb.head).z)
            zs.append((rig.matrix_world @ pb.tail).z)
    return min(zs)


def _push(rig, act, name):
    tr = rig.animation_data.nla_tracks.new(); tr.name = name
    st = tr.strips.new(name, int(act.frame_range[0]), act)
    rig.animation_data.action = None
    act.use_fake_user = True
    return act


def make_walk(P, rest_min, T=32):
    """In-place walk cycle; returns stride length (m) for the runtime speed."""
    rig = P.rig
    act = _new_action(rig, 'Elara_Walk')
    for f in range(T + 1):
        ph = 2 * math.pi * f / T
        P.clear()
        for s, off, sx in (('L', 0.0, 1), ('R', math.pi, -1)):
            p = ph + off
            thigh = 24 * math.sin(p) + 2
            knee = 6 + 52 * max(0.0, math.cos(p - 0.25)) ** 1.6 + 10 * max(0.0, math.sin(2 * (p - math.pi / 2))) * (math.sin(p) > 0)
            ankle = -thigh * 0.55 + knee * 0.55 - 12 * max(0.0, math.sin(p - math.pi * 1.25)) ** 2
            P.axis(f'upperleg01.{s}', X, -thigh)
            P.axis(f'lowerleg01.{s}', X, knee)
            P.axis(f'foot.{s}', X, -ankle * 0.8)
            # arms swing opposite
            arm = -16 * math.sin(p)
            P.axis(f'upperarm01.{s}', X, arm)
            P.axis(f'lowerarm01.{s}', X, -(12 + 8 * max(0.0, -math.sin(p))))
            P.axis(f'upperarm01.{s}', Y, sx * -3)
        P.axis('spine05', Z, 5 * math.sin(ph))
        P.axis('spine03', Z, -4 * math.sin(ph))
        P.axis('spine01', Z, -2 * math.sin(ph))
        P.axis('spine05', Y, 2.0 * math.sin(ph))
        P.axis('spine02', X, -3)              # slight forward lean
        P.axis('neck01', X, 2)
        P.axis('head', Z, 1.5 * math.sin(ph))
        P.face(EXPRESSIONS['warm_smile'] if True else {})
        rp = rig.pose.bones['root']
        rp.location = (0, 0, 0)
        bpy.context.view_layer.update()
        dz = rest_min - _foot_min_z(rig)
        # root bone points -Y in rest; its local Y is armature -Y, its local Z is armature Z
        rp.location = Vector((0.012 * math.sin(ph), 0, 0)) + _arm_to_local(rig, 'root', Vector((0, 0, dz)))
        P.key(f)
    stride = 2 * 0.82 * math.sin(math.radians(24))
    _push(rig, act, 'Elara_Walk')
    return {'name': 'Elara_Walk', 'frames': T, 'fps': FPS, 'loop': True, 'in_place': True,
            'speed_mps': round(stride / (T / FPS / 2), 3), 'stride_m': round(stride, 3)}


def _arm_to_local(rig, bone, v):
    B = rig.data.bones[bone].matrix_local.to_3x3()
    return B.inverted() @ v


def make_idle(P, rest_min, T=120):
    rig = P.rig
    act = _new_action(rig, 'Elara_Idle')
    for f in range(T + 1):
        t = f / T; ph = 2 * math.pi * t
        P.clear()
        br = math.sin(ph * 3)                  # three breaths per loop
        P.axis('spine02', X, -1.0 * br)
        P.axis('spine01', X, -0.8 * br)
        for s, sx in (('L', 1), ('R', -1)):
            P.axis(f'clavicle.{s}', Y, sx * 0.8 * br)
            P.axis(f'upperarm01.{s}', X, 2 * math.sin(ph + (0 if s == 'L' else 1)))
            P.axis(f'lowerarm01.{s}', X, -6)
        shift = math.sin(ph)
        P.axis('spine05', Y, 2.0 * shift)
        P.axis('spine03', Y, -1.4 * shift)
        P.axis('upperleg01.L', Y, -2.0 * shift); P.axis('upperleg01.R', Y, -2.0 * shift)
        P.axis('lowerleg01.L', X, 3 + 3 * max(0, shift)); P.axis('lowerleg01.R', X, 3 + 3 * max(0, -shift))
        look = math.sin(ph) * 9 + math.sin(ph * 2 + 1) * 3
        P.axis('neck02', Z, look * 0.4); P.axis('head', Z, look * 0.6)
        P.axis('head', X, -2 * math.sin(ph * 2))
        blink = 0.0
        for bt in (0.27, 0.71, 0.76):
            blink = max(blink, max(0.0, 1 - abs(t - bt) / 0.025))
        w = dict(EXPRESSIONS['warm_smile'])
        w = {k: v * 0.6 for k, v in w.items()}
        if blink:
            for k, v in EXPRESSIONS['blink'].items():
                w[k] = w.get(k, 0) + v * blink
        P.face(w)
        rp = rig.pose.bones['root']; rp.location = (0, 0, 0)
        bpy.context.view_layer.update()
        dz = rest_min - _foot_min_z(rig)
        rp.location = _arm_to_local(rig, 'root', Vector((0.008 * shift, 0, dz)))
        P.key(f)
    _push(rig, act, 'Elara_Idle')
    return {'name': 'Elara_Idle', 'frames': T, 'fps': FPS, 'loop': True}


def make_wave(P, rest_min, T=90):
    """Friendly greeting: right arm raises, three waves, warm smile, returns."""
    rig = P.rig
    act = _new_action(rig, 'Elara_Wave')
    for f in range(T + 1):
        t = f / T
        P.clear()
        up = _ease(min(1, t / 0.22)) * (1 - _ease(max(0, (t - 0.80) / 0.20)))
        wave = math.sin(2 * math.pi * 3 * max(0, (t - 0.22)) / 0.58) * (0.22 < t < 0.80)
        # calls compose right-to-left: twist first, then abduct, then bring slightly forward
        P.axis('upperarm01.R', X, -18 * up)
        P.axis('upperarm01.R', Y, 88 * up)           # abduct to the side
        P.axis('upperarm01.R', Z, (-90 + 16 * wave) * up)   # external rotation (+ the wave)
        P.axis('lowerarm01.R', X, -(10 + 88 * up))   # elbow flex -> forearm up
        P.axis('wrist.R', X, 8 * up)
        P.axis('clavicle.R', Y, 10 * up)
        P.axis('lowerarm01.L', X, -6)
        P.axis('spine02', Y, -2.5 * up)
        P.axis('neck02', Y, 4 * up); P.axis('head', Y, 5 * up); P.axis('head', Z, -6 * up)
        w = {k: v * up for k, v in EXPRESSIONS['smile'].items()}
        P.face(w)
        rp = rig.pose.bones['root']; rp.location = (0, 0, 0)
        bpy.context.view_layer.update()
        dz = rest_min - _foot_min_z(rig)
        rp.location = _arm_to_local(rig, 'root', Vector((0, 0, dz)))
        P.key(f)
    _push(rig, act, 'Elara_Wave')
    return {'name': 'Elara_Wave', 'frames': T, 'fps': FPS, 'loop': False}


def _ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def build_library(rig):
    units = load_poseunits()
    P = Poser(rig, units)
    P.clear(); bpy.context.view_layer.update()
    rest_min = _foot_min_z(rig)
    clips = [make_idle(P, rest_min), make_walk(P, rest_min), make_wave(P, rest_min)]
    for tr in rig.animation_data.nla_tracks:
        tr.mute = False
    P.clear()
    return clips, units


def pose_expression(rig, units, name):
    P = Poser(rig, units); P.clear(); P.face(EXPRESSIONS[name])
    bpy.context.view_layer.update()
