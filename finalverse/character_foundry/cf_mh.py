"""Character Foundry: MakeHuman (CC0) base-mesh loader for Blender.

Loads the hm08 base mesh, applies CC0 targets, converts MH Y-up decimetres to
Blender Z-up metres (front = -Y), builds the MakeHuman default skeleton (163
bones incl. face) from joint helper geometry, and applies the CC0 skin
weights. No MakeHuman program code is used; only CC0 data files are read.
"""
import json
import math
import os
from collections import defaultdict

import bpy
import numpy as np
from mathutils import Matrix, Vector

MH = os.environ.get('CF_MH', os.path.expanduser('~/cf/mh'))


def read_obj(path):
    verts, uvs, faces, groups = [], [], [], []
    g = None
    for line in open(path):
        if line.startswith('v '):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith('vt '):
            uvs.append([float(x) for x in line.split()[1:3]])
        elif line.startswith('g '):
            g = line.split()[1]
        elif line.startswith('f '):
            vs, ts = [], []
            for tok in line.split()[1:]:
                a = tok.split('/')
                vs.append(int(a[0]) - 1)
                ts.append(int(a[1]) - 1 if len(a) > 1 and a[1] else -1)
            faces.append((vs, ts)); groups.append(g)
    return np.array(verts, dtype=np.float64), np.array(uvs), faces, groups


def read_target(path):
    idx, d = [], []
    for line in open(path):
        if line.startswith('#') or not line.strip():
            continue
        a = line.split()
        idx.append(int(a[0])); d.append([float(x) for x in a[1:4]])
    return np.array(idx), np.array(d)


def mh_to_blender(co):
    """MH (x, y-up, z-front) decimetres -> Blender (x, -z, y) metres."""
    out = np.empty_like(co)
    out[:, 0] = co[:, 0]; out[:, 1] = -co[:, 2]; out[:, 2] = co[:, 1]
    return out * 0.1


class MHBase:
    def __init__(self, targets):
        self.v, self.uv, self.faces, self.groups = read_obj(f'{MH}/base.obj')
        self.applied = []
        for name, w in targets:
            idx, d = read_target(f'{MH}/{name}.target')
            self.v[idx] += w * d
            self.applied.append((name, w))
        self.skel = json.load(open(f'{MH}/default.mhskel'))
        self.weights = json.load(open(f'{MH}/default_weights.mhw'))['weights']
        self.co = mh_to_blender(self.v)
        self.group_verts = defaultdict(set)
        for (vs, _), g in zip(self.faces, self.groups):
            self.group_verts[g].update(vs)

    def fit_height(self, height_m):
        body = sorted(self.group_verts['body'])
        z = self.co[body, 2]
        s = height_m / (z.max() - z.min())
        ground = self.joint('joint-ground') if 'joint-ground' in self.group_verts else None
        self.co *= s
        zmin = self.co[body, 2].min()
        self.co[:, 2] -= zmin
        c = self.co[body].mean(axis=0)
        self.co[:, 0] -= c[0]; self.co[:, 1] -= c[1]
        self.scale = s
        return s

    def joint(self, name):
        return self.co[sorted(self.group_verts[name])].mean(axis=0)

    def skel_joint(self, key):
        return self.co[self.skel['joints'][key]].mean(axis=0)

    def body_mesh(self, name='Elara_Body', groups=('body',)):
        """Mesh of the selected groups, keeping original vertex indices map."""
        sel = [i for i, g in enumerate(self.groups) if g in groups]
        used = sorted({v for i in sel for v in self.faces[i][0]})
        remap = {v: k for k, v in enumerate(used)}
        polys = [[remap[v] for v in self.faces[i][0]] for i in sel]
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(self.co[v]) for v in used], [], polys)
        uvl = me.uv_layers.new(name='UVMap')
        loop_uv = []
        for i in sel:
            for t in self.faces[i][1]:
                loop_uv.extend(self.uv[t] if t >= 0 else (0, 0))
        uvl.data.foreach_set('uv', loop_uv)
        for p in me.polygons:
            p.use_smooth = True
        me.update()
        return me, used, remap

    def build_armature(self, scene, name='Elara_Rig'):
        arm = bpy.data.armatures.new(name)
        ob = bpy.data.objects.new(name, arm)
        scene.collection.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        bones = self.skel['bones']
        planes = self.skel['planes']
        for bname, b in bones.items():
            eb = arm.edit_bones.new(bname)
            eb.head = Vector(self.skel_joint(b['head']))
            eb.tail = Vector(self.skel_joint(b['tail']))
            if (eb.tail - eb.head).length < 1e-4:
                eb.tail = eb.head + Vector((0, 0, 0.01))
        for bname, b in bones.items():
            eb = arm.edit_bones[bname]
            if b['parent']:
                eb.parent = arm.edit_bones[b['parent']]
            pl = planes.get(b['rotation_plane'])
            if pl:
                p0, p1, p2 = (Vector(self.skel_joint(k)) for k in pl)
                n = (p1 - p0).cross(p2 - p1)
                if n.length > 1e-8:
                    # MakeHuman convention: plane normal is the bone's local X axis
                    eb.align_roll((eb.tail - eb.head).normalized().cross(n.normalized()))
        for eb in arm.edit_bones:
            eb.use_connect = False
            eb.use_deform = True
        bpy.ops.object.mode_set(mode='OBJECT')
        arm.display_type = 'STICK'
        return ob

    def apply_weights(self, ob, remap):
        for bname, pairs in self.weights.items():
            vg = ob.vertex_groups.get(bname) or ob.vertex_groups.new(name=bname)
            for v, w in pairs:
                if v in remap:
                    vg.add([remap[v]], w, 'REPLACE')
