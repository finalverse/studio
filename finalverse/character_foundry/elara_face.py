"""CF1 Elara: eyes (MakeHuman CC0 high-poly eyeballs, fitted to the eye helpers),
eyelashes (from the base mesh's lash helper geometry), and the eye texture."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

import cf_tex as TX
from cf_mh import MH, read_obj, mh_to_blender


def _components(faces, nverts):
    parent = list(range(nverts))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for vs, _ in faces:
        for v in vs[1:]:
            ra, rb = find(vs[0]), find(v)
            if ra != rb:
                parent[ra] = rb
    return [find(i) for i in range(nverts)]


def eyes(mh, scene):
    v, uv, faces, groups = read_obj(f'{MH}/high-poly.obj')
    co = mh_to_blender(v)
    comp = _components(faces, len(co))
    roots = sorted(set(comp), key=lambda r: co[[i for i in range(len(co)) if comp[i] == r]][:, 0].mean())
    out = []
    # roots sorted by x: first is her right (-x), last her left (+x)
    sides = {'R': roots[0], 'L': roots[-1]} if len(roots) >= 2 else {'L': roots[0]}
    for side, root in sides.items():
        idx = [i for i in range(len(co)) if comp[i] == root]
        sub = co[idx]
        tgt_ids = sorted(mh.group_verts[f'helper-{side.lower()}-eye'])
        tgt = mh.co[tgt_ids]
        s = (tgt.max(0) - tgt.min(0)).mean() / (sub.max(0) - sub.min(0)).mean()
        c_src = (sub.max(0) + sub.min(0)) / 2; c_tgt = (tgt.max(0) + tgt.min(0)) / 2
        newco = (sub - c_src) * s + c_tgt
        rm = {g: k for k, g in enumerate(idx)}
        fs = [(f, t) for f, t in faces if f[0] in rm]
        me = bpy.data.meshes.new(f'Elara_Eye.{side}')
        me.from_pydata([tuple(p) for p in newco], [], [[rm[x] for x in f] for f, _ in fs])
        uvl = me.uv_layers.new(name='UVMap')
        loop = []
        for f, t in fs:
            for tt in t:
                loop.extend(uv[tt] if tt >= 0 else (0, 0))
        uvl.data.foreach_set('uv', loop)
        for p in me.polygons:
            p.use_smooth = True
        ob = bpy.data.objects.new(f'Elara_Eye.{side}', me); scene.collection.objects.link(ob)
        ob['cf.eye_center'] = list(c_tgt)
        out.append(ob)
    return out


def lashes(mh, scene, eyes_objs=None):
    """Upper-lid lash ribbons along the lid margin (the MH lash helpers are too heavy)."""
    import cf_geo as G
    objs = []
    for e in eyes_objs or []:
        c = np.array(e['cf.eye_center'])
        sx = 1 if e.name.endswith('.L') else -1
        co = np.array([v.co[:] for v in e.data.vertices])
        r = (co.max(0) - co.min(0)).mean() / 2
        pts, nrm = [], []
        for t in np.linspace(0, 1, 18):
            a = math.radians(200 - 220 * t) if sx < 0 else math.radians(-20 + 220 * t)
            # arc over the upper lid in the x-z plane, slightly in front of the cornea
            x = c[0] + math.cos(a) * r * 1.02
            z = c[2] + 0.0004 + math.sin(a) * r * 0.40
            y = c[1] - r * 0.97 + 0.0040 * abs(math.cos(a)) ** 2
            pts.append((x, y, z))
            nrm.append((math.cos(a) * 0.4, -1.0, 0.8))
        L = [0.0026 * math.sin(math.pi * (0.15 + 0.85 * t)) ** 0.7 + 0.0008 for t in np.linspace(0, 1, 18)]
        prof = [(0.0, -0.00025), (1.0, -0.00012), (1.0, 0.00012), (0.0, 0.00025)]
        sc = [(l, 1.0) for l in L]
        ob = G.sweep(f'Elara_Lashes.{"L" if sx > 0 else "R"}', pts, prof, scale=sc, normals=nrm, cap=True)
        objs.append(ob)
    return objs


def lashes_helpers(mh, scene):
    objs = []
    for side in ('l', 'r'):
        grp = [g for g in set(mh.groups) if g.startswith(f'helper-{side}-eyelashes')]
        me, used, remap = mh.body_mesh(f'Elara_Lashes.{side.upper()}', tuple(grp))
        ob = bpy.data.objects.new(f'Elara_Lashes.{side.upper()}', me); scene.collection.objects.link(ob)
        mh.apply_weights(ob, remap)
        objs.append(ob)
    return objs


def eye_texture(eye, size=512, iris_hex='#6b5a2e', ring_hex='#2a2416'):
    """Hazel-green iris (reference: warm brown-hazel), limbal ring, radial fibres,
    sclera with a faint warm edge. Painted from each texel's 3D direction."""
    P, N, M = TX.position_map(eye, size)
    c = np.array(eye['cf.eye_center'])
    d = P - c
    d /= np.maximum(np.linalg.norm(d, axis=-1, keepdims=True), 1e-9)
    fwd = np.array([0, -1, 0.0])
    ang = np.arccos(np.clip(d @ fwd, -1, 1))
    # azimuth around the forward axis for fibres
    az = np.arctan2(d[..., 2], d[..., 0])
    iris_r, pupil_r = 0.50, 0.19
    iris = np.clip((iris_r - ang) / 0.03, 0, 1)
    pupil = np.clip((pupil_r - ang) / 0.02, 0, 1)
    t = np.clip(ang / iris_r, 0, 1)
    col_in = TX.srgb('#8a7a34'); col_mid = TX.srgb(iris_hex); col_out = TX.srgb('#3e4a2a')
    base = np.where(t[..., None] < .45, col_in + (col_mid - col_in) * (t[..., None] / .45),
                    col_mid + (col_out - col_mid) * ((t[..., None] - .45) / .55))
    fib = 0.75 + 0.25 * np.sin(az * 58 + 3 * np.sin(az * 7)) * np.sin(az * 23 + 1.3)
    base = base * fib[..., None]
    ring = np.exp(-((ang - iris_r + 0.02) / 0.03) ** 2)[..., None]
    base = base * (1 - 0.7 * ring) + TX.srgb(ring_hex) * 0.7 * ring
    sclera = TX.srgb('#efe6dc') * (1 - 0.15 * TX.smoothstep(0.9, 1.6, ang))[..., None] + np.array([0.06, 0.0, 0.0]) * TX.smoothstep(1.0, 1.7, ang)[..., None]
    col = sclera * (1 - iris[..., None]) + base * iris[..., None]
    col = col * (1 - pupil[..., None]) + np.array([0.02, 0.02, 0.025]) * pupil[..., None]
    col = TX.dilate(col, M, 4)
    return TX.to_image(f'T_{eye.name}_BaseColor', col)
