"""CF1 Elara: sculpted stylised hair.

A scalp shell (offset head surface) carries the base colour; ~40 flattened
locks are swept over the shell from a centre part back to a gathering point
behind her left ear, layered so the clumps overlap like real hair; a
three-strand braid (true interleaved braid parametrisation) falls over her
left shoulder to the chest, finished with a tie and a tufted tail; loose
face-framing strands at both temples. Every lock has u-around/v-along UVs
for the strand texture.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import cf_geo as G


class HeadShell:
    def __init__(self, bi):
        self.bi = bi
        hb = bi.rig.data.bones['head']
        self.c = np.array(hb.head_local) + np.array([0, 0.004, 0.058])  # skull centre
        names = bi.names
        hi = names.index('head')
        headw = bi.W[:, hi]
        me = bi.body.data
        vmask = headw > 0.5
        polys = [list(p.vertices) for p in me.polygons if all(vmask[list(p.vertices)])]
        self.bvh = BVHTree.FromPolygons([Vector(v) for v in bi.co], polys)

    def surf(self, d, out=0.0):
        d = np.asarray(d, float); d = d / np.linalg.norm(d)
        o = Vector(self.c + d * 0.25)
        hit = self.bvh.ray_cast(o, Vector(-d))
        if hit[0] is None:
            p = self.c + d * 0.095; n = d
        else:
            p = np.array(hit[0]); n = np.array(hit[1])
            if n @ d < 0:
                n = -n
        return p + d * out, d


def slerp_dir(a, b, t):
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    om = math.acos(max(-1, min(1, a @ b)))
    if om < 1e-5:
        return a
    return (math.sin((1 - t) * om) * a + math.sin(t * om) * b) / math.sin(om)


def bez_dirs(a, m, b, n):
    out = []
    for t in np.linspace(0, 1, n):
        p = slerp_dir(slerp_dir(a, m, t), slerp_dir(m, b, t), t)
        out.append(p)
    return out


def sph(az, el):
    """azimuth: 0 = front (-Y), +90 = her left (+X); elevation from horizontal."""
    a, e = math.radians(az), math.radians(el)
    return np.array([math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)])


def lock(shell, name, dirs, base_out, width, thick, rng, lift=None):
    pts, nrm = [], []
    n = len(dirs)
    for i, d in enumerate(dirs):
        t = i / (n - 1)
        extra = base_out + (lift(t) if lift else 0)
        p, nn = shell.surf(d, extra)
        pts.append(p); nrm.append(nn)
    pts = np.array(pts)
    # smooth the path
    for _ in range(2):
        pts[1:-1] = .25 * pts[:-2] + .5 * pts[1:-1] + .25 * pts[2:]
    prof = [(math.cos(a) * 0.5, math.sin(a) * 0.5) for a in np.linspace(0, 2 * math.pi, 10, endpoint=False)]
    scale = []
    for i in range(n):
        t = i / (n - 1)
        taper = min(1.0, 0.35 + t * 3.0) * (1 - 0.55 * t ** 2)
        scale.append((thick * (0.6 + 0.4 * taper), width * taper))
    return G.sweep(name, pts, prof, scale=scale, normals=nrm, cap=True)


def build_hair(bi, garments_bvh=None, seed=11):
    rng = np.random.default_rng(seed)
    shell = HeadShell(bi)
    objs = []
    # --- scalp cap: head faces in the hair region, offset outward -----------
    me = bi.body.data
    hi = bi.names.index('head')
    c = shell.c
    keep = []
    for p in me.polygons:
        vs = list(p.vertices)
        if bi.W[vs, hi].min() < 0.5:
            continue
        d = bi.co[vs].mean(0) - c; d /= np.linalg.norm(d)
        az = math.degrees(math.atan2(d[0], -d[1])); el = math.degrees(math.asin(d[2]))
        face = abs(az) < 62 and el < 38 - 0.0 * abs(az)
        ear = abs(az) > 62 and abs(az) < 118 and el < -14
        lowback = el < -72
        if not (face or ear or lowback):
            keep.append(vs)
    used = sorted({v for f in keep for v in f}); rm = {v: k for k, v in enumerate(used)}
    co = bi.co[used] + bi.nor[used] * 0.006
    cm = bpy.data.meshes.new('Elara_HairCap')
    cm.from_pydata([tuple(x) for x in co], [], [[rm[v] for v in f] for f in keep])
    # body UVs are kept for the strand texture lookup (3D-painted)
    for p in cm.polygons:
        p.use_smooth = True
    cap = bpy.data.objects.new('Elara_HairCap', cm); bpy.context.scene.collection.objects.link(cap)
    G.laplacian(cap, 4, .4)
    objs.append(cap)

    gather = sph(150, -18)             # behind her left ear: braid root
    part_az = -6                       # centre part, a touch to her right
    # --- top locks: from the part line, swept to each side then back -------
    k = 0
    for side in (1, -1):
        for j, el in enumerate(np.linspace(40, 86, 9)):
            start = sph(part_az + side * 1.5, el)
            if el > 80:
                start = sph(part_az + 180 * (el > 88), el)
            side_az = side * (70 + 25 * (j / 8)) + rng.normal(0, 4)
            mid = sph(side_az, 8 + 30 * (j / 8) + rng.normal(0, 3))
            end = gather + rng.normal(0, 0.05, 3)
            dirs = bez_dirs(start, mid, end, 26)
            lift = (lambda t, a=0.012 + 0.005 * rng.random(): a * math.sin(math.pi * min(t * 1.15, 1)))
            objs.append(lock(shell, f'Elara_HairLock.{k:02d}', dirs, 0.014 + 0.003 * (j % 3) + 0.004 * (j / 8),
                             0.036 + 0.008 * rng.random(), 0.013, rng, lift)); k += 1
    # --- crown and back locks down to the gather point ----------------------
    for j, az in enumerate(np.linspace(-150, 150, 13)):
        start = sph(az * 0.25 + 180, 70)
        mid = sph(180 + az * 0.75 if az < 0 else 180 + az * 0.55, 15 + rng.normal(0, 4))
        dirs = bez_dirs(start, mid, gather + rng.normal(0, 0.04, 3), 22)
        objs.append(lock(shell, f'Elara_HairLock.{k:02d}', dirs, 0.010 + 0.003 * (j % 2),
                         0.040, 0.013, rng, lambda t: 0.006 * math.sin(math.pi * t))); k += 1
    # nape locks: from the low hairline up into the gather point (covers the nape)
    for j, az in enumerate(np.linspace(-125, 140, 12)):
        start = sph(180 + az * 0.55, -62)
        dirs = bez_dirs(start, sph(180 + az * 0.35, -35), gather, 14)
        objs.append(lock(shell, f'Elara_HairLock.{k:02d}', dirs, 0.007, 0.040, 0.011, rng)); k += 1
    # --- temple strands: loose, framing the face (reference) ----------------
    for side in (1, -1):
        for j in range(2):
            s = sph(side * (52 + 6 * j), 34 - 4 * j)
            pts = []
            p0, n0 = shell.surf(s, 0.008)
            pts.append(p0)
            down = np.array([side * 0.012, -0.004, -1.0])
            for t in np.linspace(0, 1, 12)[1:]:
                p = p0 + down * (0.10 + 0.02 * j) * t + np.array([side * 0.010 * math.sin(t * 3), -0.006 * t, 0])
                # keep outside the cheek
                q, _ = shell.surf(p - shell.c, 0.006 + 0.004 * t)
                if np.linalg.norm(p - shell.c) < np.linalg.norm(q - shell.c):
                    p = q
                pts.append(p)
            prof = G.circle(8, 0.5, 0.5)
            sc = [(0.004 * (1 - .6 * t), 0.010 * (1 - .7 * t ** 1.5)) for t in np.linspace(0, 1, len(pts))]
            objs.append(G.sweep(f'Elara_HairStrand.{side:+d}{j}', pts, prof, scale=sc, cap=True))
    # --- braid over her left shoulder ---------------------------------------
    root, _ = shell.surf(gather, 0.010)
    braid_objs, braid_path = braid(root, bi, garments_bvh)
    objs.extend(braid_objs)
    return objs, braid_path


def braid_curve(root, bi):
    sh = bi.bone('shoulder01.L', tail=True)
    neck = bi.bone('neck01')
    ctrl = np.array([
        root,
        root + np.array([0.02, 0.02, -0.06]),
        np.array([0.075, neck[1] + 0.035, neck[2] - 0.005]),
        np.array([0.110, neck[1] - 0.020, sh[2] + 0.04]),
        np.array([0.112, -0.120, sh[2] - 0.05]),
        np.array([0.105, -0.150, sh[2] - 0.17]),
        np.array([0.100, -0.150, sh[2] - 0.27]),
    ])
    # Catmull-Rom through the controls
    pts = []
    P = np.concatenate([[ctrl[0]], ctrl, [ctrl[-1]]])
    for i in range(1, len(P) - 2):
        for t in np.linspace(0, 1, 14, endpoint=False):
            p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
            pts.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    pts.append(ctrl[-1])
    return np.array(pts)


def braid(root, bi, garments_bvh, cycles=7.5):
    path = braid_curve(root, bi)
    if garments_bvh is not None:
        for i in range(len(path)):
            loc, nor, idx, dist = garments_bvh.find_nearest(Vector(path[i]))
            if loc is not None:
                want = 0.020 * (1 - 0.35 * i / len(path))
                v = path[i] - np.array(loc)
                if v @ np.array(nor) < want or i > len(path) * 0.30:
                    path[i] = np.array(loc) + np.array(nor) * want
        for _ in range(3):
            path[1:-1] = .25 * path[:-2] + .5 * path[1:-1] + .25 * path[2:]
    # resample uniformly
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1); L = np.concatenate([[0], np.cumsum(seg)])
    s = np.linspace(0, L[-1], 180)
    path = np.stack([np.interp(s, L, path[:, k]) for k in range(3)], 1)
    P, T, N, B = G.frame_along(path, up=Vector((0, -1, 0)))
    objs = []
    A = 0.0105
    for k in range(3):
        ph = 2 * math.pi * k / 3
        pts = []; scale = []
        for i, (p, n, b) in enumerate(zip(P, N, B)):
            u = i / (len(P) - 1)
            tt = 2 * math.pi * cycles * u
            amp = A * (1 - 0.38 * u) * min(1, u * 8 + 0.25)
            off = np.array(b) * (amp * math.sin(tt + ph)) + np.array(n) * (amp * 0.55 * math.sin(2 * (tt + ph)))
            pts.append(np.array(p) + off)
            w = 0.0125 * (1 - 0.40 * u) * min(1, u * 6 + 0.55)
            scale.append((w * 0.75, w))
        prof = G.circle(10, 1.0, 1.0)
        objs.append(G.sweep(f'Elara_Braid.{k}', pts, prof, scale=scale, up=Vector((0, -1, 0)), cap=True))
    # tie and tail
    end = np.array(P[-1]); t_end = np.array(T[-1])
    tie = G.sweep('Elara_BraidTie', [end - t_end * 0.004, end + t_end * 0.008], G.circle(16, 0.0085), cap=True)
    objs.append(tie)
    rng = np.random.default_rng(3)
    for j in range(7):
        a = 2 * math.pi * j / 7
        spread = np.array(N[-1]) * math.cos(a) + np.array(B[-1]) * math.sin(a)
        pts = [end + t_end * 0.004 + spread * 0.002]
        for t in np.linspace(0, 1, 8)[1:]:
            pts.append(end + t_end * (0.004 + 0.055 * t) + spread * (0.004 + 0.010 * t) + np.array([0, 0, -0.004]) * t)
        sc = [(0.0045 * (1 - .8 * t), 0.006 * (1 - .8 * t)) for t in np.linspace(0, 1, len(pts))]
        objs.append(G.sweep(f'Elara_BraidTail.{j}', pts, G.circle(8, 1, 1), scale=sc, cap=True))
    return objs, path
