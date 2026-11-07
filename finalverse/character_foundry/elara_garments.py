"""CF1 Elara: garments built on the body in the authoring rest pose.

Tunic and sleeves are lofted from convex cross-sections of the body (fabric
bridges concavities the way cloth does), with ease, flare and fold waves.
Leggings re-material the body's leg faces (zero poke-through by construction).
Boots are an offset, smoothed shell of the feet with a separate sole, cuff
and laces. All pieces carry clean UVs for the texture painters.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

import cf_geo as G
import cf_rig as RG

ARM_KEYS = ('upperarm', 'lowerarm', 'wrist', 'finger', 'metacarpal')
LEG_KEYS = ('upperleg', 'lowerleg', 'foot', 'toe')


class BodyInfo:
    def __init__(self, body, rig):
        self.body, self.rig = body, rig
        me = body.data
        self.co = np.array([v.co[:] for v in me.vertices])
        self.nor = np.array([v.normal[:] for v in me.vertices])
        W = RG.weights_array(body)
        names = [vg.name for vg in body.vertex_groups]
        self.W, self.names = W, names

        def sumw(keys):
            idx = [i for i, n in enumerate(names) if any(n.startswith(k) for k in keys)]
            return W[:, idx].sum(1)
        self.arm = sumw(ARM_KEYS)
        self.leg = sumw(LEG_KEYS)
        self.handw = sumw(('wrist', 'finger', 'metacarpal'))
        self.side = np.sign(self.co[:, 0])

    def bone(self, name, tail=False):
        b = self.rig.data.bones[name]
        return np.array(b.tail_local if tail else b.head_local)

    def slab(self, z, half, mask):
        sel = mask & (np.abs(self.co[:, 2] - z) < half)
        return self.co[sel]


# ---------------------------------------------------------------- tunic -----
def tunic(bi, N=96):
    neck_z = bi.bone('neck01')[2] - 0.006
    hem_z = 0.715
    crotch_z = bi.bone('upperleg01.L', tail=True)[2] - 0.02
    waist_z = bi.bone('spine04')[2] + 0.025
    armpit_z = bi.bone('upperarm01.L', tail=True)[2] + 0.03
    torso_mask = (bi.arm < 0.30) | ((bi.arm < 0.8) & (bi.co[:, 2] > armpit_z) & (bi.handw < 0.1))
    theta = np.linspace(0, 2 * np.pi, N, endpoint=False)
    dirs = np.stack([np.sin(theta), -np.cos(theta)], 1)   # theta 0 = front (-Y)
    # radius table on a fine z grid
    zt = np.linspace(hem_z, neck_z + 0.01, 90)
    table, ctab = [], []
    for z in zt:
        pts = bi.slab(z, 0.014, torso_mask)[:, :2]
        if z < crotch_z + 0.06:
            pts = np.concatenate([pts, bi.slab(z, 0.014, bi.leg > 0.4)[:, :2]])
        hull = G.hull2d(pts)
        c = np.array([0.0, pts[:, 1].mean()])
        table.append(G.circ_smooth(G.polygon_radius(hull, c, dirs), 2)); ctab.append(c)
    table = np.array(table); ctab = np.array(ctab)
    for _ in range(4):
        table[1:-1] = .25 * table[:-2] + .5 * table[1:-1] + .25 * table[2:]
        ctab[1:-1] = .25 * ctab[:-2] + .5 * ctab[1:-1] + .25 * ctab[2:]
    # neckline height per column: scooped front, higher at the back
    neck = bi.bone('neck01')
    ztop = neck_z - 0.060 * np.exp(-(np.angle(np.exp(1j * theta)) / 0.55) ** 2) - 0.012 * np.exp(-(np.angle(np.exp(1j * theta)) / 1.4) ** 2)
    rings = []
    S = np.concatenate([np.linspace(0, 1, 26)[:-1], 1 + np.linspace(0, 1, 24)])   # 0..1 hem->waist, 1..2 waist->top
    for sk in S[::-1]:
        if sk <= 1:
            z = np.full(N, hem_z + (waist_z - hem_z) * sk)
        else:
            z = waist_z + (ztop - waist_z) * (sk - 1)
        r = np.array([np.interp(z[i], zt, table[:, i]) for i in range(N)])
        cy = np.interp(z, zt, ctab[:, 1])
        zz = z.mean()
        below = max(0.0, waist_z - zz)
        ease = 0.010 + 0.005 * smooth01((zz - waist_z) / 0.25)
        if abs(zz - waist_z) < 0.025:
            ease = 0.006
        ease += 0.045 * smooth01(below / (waist_z - hem_z)) ** 1.5
        fold_amp = 0.008 * smooth01((waist_z - 0.04 - zz) / 0.22)
        folds = fold_amp * (np.sin(theta * 9 + 0.7) * .6 + np.sin(theta * 5 + 2.1) * .4)
        r = r + ease + folds
        rings.append(np.stack([dirs[:, 0] * r, cy + dirs[:, 1] * r, z], 1))
    ob = G.loft_rings('Elara_Tunic', rings)
    return ob


def smooth01(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def neckline_cut(ob, bi):
    """Scoop the front neckline and add a short front slit."""
    neck = bi.bone('neck01')
    bm = bmesh.new(); bm.from_mesh(ob.data)
    kill = []
    for f in bm.faces:
        c = f.calc_center_median()
        ang = math.atan2(c.x, -(c.y - neck[1]))   # 0 = front
        zcut = neck[2] - 0.012 - 0.065 * math.exp(-(ang / 0.55) ** 2) - 0.018 * math.exp(-(ang / 1.4) ** 2)
        if c.z > zcut:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(ob.data); bm.free()


def sleeve(bi, side, N=40):
    s = side
    sh = bi.bone(f'shoulder01.{s}'); sht = bi.bone(f'shoulder01.{s}', tail=True)
    a = sh + (sht - sh) * 0.55 + np.array([0, 0, 0.012])
    e = bi.bone(f'lowerarm01.{s}')
    w = bi.bone(f'wrist.{s}')
    end = e + (w - e) * 0.30          # half sleeve, rolled just below the elbow
    pts = []
    for t in np.linspace(0, 1, 14):
        pts.append(a + (e - a) * t)
    for t in np.linspace(0, 1, 8)[1:]:
        pts.append(e + (end - e) * t)
    pts = np.array(pts)
    P, T, Nn, B = G.frame_along(pts, up=Vector((0, -1, 0)))
    armmask = (bi.arm > 0.45) & (bi.side == (1 if s == 'L' else -1)) & (bi.handw < 0.2)
    armco = bi.co[armmask]
    rings = []
    phi = np.linspace(0, 2 * np.pi, N, endpoint=False)
    for i, (p, t, n, b) in enumerate(zip(P, T, Nn, B)):
        p = np.array(p); t = np.array(t); n = np.array(n); b = np.array(b)
        d = armco - p
        along = d @ t
        sel = np.abs(along) < 0.02
        if sel.sum() < 6:
            sel = np.argsort(np.abs(along))[:40]
        q = np.stack([d[sel] @ n, d[sel] @ b], 1)
        hull = G.hull2d(q)
        dirs = np.stack([np.cos(phi), np.sin(phi)], 1)
        r = G.polygon_radius(hull, np.zeros(2), dirs)
        r = G.circ_smooth(r, 2)
        f = i / (len(P) - 1)
        ease = 0.012 + 0.010 * f + 0.004 * np.sin(phi * 4 + i * .9) * f
        if i == 0:
            ease = ease + 0.012
        r = r + ease
        ring = p + np.outer(r * np.cos(phi), n) + np.outer(r * np.sin(phi), b)
        rings.append(ring)
    ob = G.loft_rings(f'Elara_Sleeve.{s}', rings, uv_u=lambda i, N: 0.3 + 0.4 * i / N)
    # rolled cuff
    cuff_pts = [np.array(P[-1]) - np.array(T[-1]) * 0.022, np.array(P[-1]) + np.array(T[-1]) * 0.004]
    last = rings[-1]
    rr = np.linalg.norm(last - np.array(P[-1]), axis=1).mean()
    cuff = G.sweep(f'Elara_Cuff.{s}', cuff_pts, G.circle(N, rr + 0.007), cap=False)
    return ob, cuff


# ------------------------------------------------------------- leggings -----
def leggings(bi, mat_index):
    """Assign the legs' skin faces to the leggings material and inflate slightly."""
    me = bi.body.data
    z = bi.co[:, 2]
    ok = (z < bi.bone('spine04')[2] + 0.03) & (bi.arm < 0.2)
    sel_v = np.zeros(len(z), bool)
    for p in me.polygons:
        if all(ok[list(p.vertices)]):
            p.material_index = mat_index
            sel_v[list(p.vertices)] = True
    co = bi.co.copy()
    co[sel_v] += bi.nor[sel_v] * 0.0018
    me.vertices.foreach_set('co', co.ravel()); me.update()


# ---------------------------------------------------------------- boots -----
def boots(bi, top_z=0.395, sole=0.014):
    me = bi.body.data
    z = bi.co[:, 2]
    objs = []
    for s, sx in (('L', 1), ('R', -1)):
        vmask = (z < top_z + 0.03) & (bi.side == sx) & (bi.leg > 0.3)
        faces = [list(p.vertices) for p in me.polygons if all(vmask[list(p.vertices)])]
        used = sorted({v for f in faces for v in f}); rm = {v: k for k, v in enumerate(used)}
        co = bi.co[used] + bi.nor[used] * 0.008
        bme = bpy.data.meshes.new(f'Elara_Boot.{s}')
        bme.from_pydata([tuple(c) for c in co], [], [[rm[v] for v in f] for f in faces])
        ob = bpy.data.objects.new(f'Elara_Boot.{s}', bme); bpy.context.scene.collection.objects.link(ob)
        # smooth away toes, keep the boot top edge in place
        bm = bmesh.new(); bm.from_mesh(bme)
        boundary = [v.index for v in bm.verts if v.is_boundary]; bm.free()
        G.laplacian(ob, 40, 0.5, pin=np.array(boundary, dtype=np.int64))
        c = np.array([v.co[:] for v in bme.vertices])
        # re-inflate the volume lost by smoothing (keep a full toe box)
        cen = c.mean(0)
        foot = c[:, 2] < 0.12
        c[foot, 0] = cen[0] + (c[foot, 0] - cen[0]) * 1.06
        c[:, 2] = np.maximum(c[:, 2], sole)
        # boot last: fill the gaps between toes by pushing every foot vertex out to the
        # convex hull of its horizontal slice (a shoe has no toe clefts)
        for z0 in np.arange(sole, 0.14, 0.008):
            sl = np.nonzero(np.abs(c[:, 2] - z0) < 0.006)[0]
            if len(sl) < 8:
                continue
            hull = G.hull2d(c[sl, :2]); cen = hull.mean(0)
            d = c[sl, :2] - cen; dn = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
            r = G.polygon_radius(hull, cen, dn)
            c[sl, :2] = cen + dn * np.maximum(np.linalg.norm(d, axis=1), r)[:, None]
        bme.vertices.foreach_set('co', c.ravel()); bme.update()
        G.laplacian(ob, 12, 0.5, pin=np.array(boundary, dtype=np.int64))
        c = np.array([v.co[:] for v in bme.vertices]); c[:, 2] = np.maximum(c[:, 2], sole)
        bme.vertices.foreach_set('co', c.ravel()); bme.update()
        # the shell must stay outside the skin everywhere (smoothing shrinks it)
        from mathutils import Vector as V3
        from mathutils.bvhtree import BVHTree
        fm = (z < top_z + 0.05) & (bi.side == sx)
        fpolys = [list(p.vertices) for p in me.polygons if all(fm[list(p.vertices)])]
        bvh = BVHTree.FromPolygons([V3(x) for x in bi.co], fpolys)
        for it in range(3):
            for v in bme.vertices:
                if v.co.z < 0.11:
                    continue      # toe box is shaped by the hull fill below; skin there is removed
                loc, nor, idx, dist = bvh.find_nearest(v.co)
                if loc is None:
                    continue
                if (v.co - loc).dot(nor) < 0.007:
                    v.co = loc + nor * 0.007
            if it < 2:
                G.laplacian(ob, 2, 0.4, pin=np.array(boundary, dtype=np.int64))
        c = np.array([v.co[:] for v in bme.vertices])
        for rep in range(3):
            for z0 in np.arange(sole, 0.12, 0.006):
                sl = np.nonzero(np.abs(c[:, 2] - z0) < 0.004)[0]
                if len(sl) < 8:
                    continue
                hull = G.hull2d(c[sl, :2]); cen = hull.mean(0)
                d = c[sl, :2] - cen; dn = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
                r = G.polygon_radius(hull, cen, dn)
                c[sl, :2] = cen + dn * np.maximum(np.linalg.norm(d, axis=1), r)[:, None]
            bme.vertices.foreach_set('co', c.ravel()); bme.update()
            G.laplacian(ob, 4, 0.5, pin=np.array(boundary, dtype=np.int64))
            c = np.array([v.co[:] for v in bme.vertices]); c[:, 2] = np.maximum(c[:, 2], sole)
        bme.vertices.foreach_set('co', c.ravel()); bme.update()
        # trim top edge to a clean horizontal-ish line
        bm = bmesh.new(); bm.from_mesh(bme)
        kill = [f for f in bm.faces if f.calc_center_median().z > top_z]
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bm.to_mesh(bme); bm.free()
        for p in bme.polygons:
            p.use_smooth = True
        objs.append(ob)
        # sole: hull of the bottom outline, extruded to the ground
        cc = np.array([v.co[:] for v in bme.vertices])
        bot = cc[cc[:, 2] < sole + 0.012][:, :2]
        hull = G.hull2d(bot)
        cen2 = hull.mean(0)
        hull = cen2 + (hull - cen2) * 1.0 + 0.004 * (hull - cen2) / np.linalg.norm(hull - cen2, axis=1)[:, None]
        hull = resample_closed(hull, 48)
        sole_rings = [np.c_[hull, np.full(len(hull), zz)] for zz in (0.0, 0.004, sole + 0.002, sole + 0.012)]
        insets = [1.0, 1.0, 1.0, 0.94]
        sr = []
        for ring, k in zip(sole_rings, insets):
            r2 = ring.copy(); r2[:, :2] = cen2 + (r2[:, :2] - cen2) * k; sr.append(r2)
        so = G.loft_rings(f'Elara_Sole.{s}', sr)
        G.cap_ends(so, len(hull), len(sr))
        objs.append(so)
        # folded cuff at the boot top
        top = cc[cc[:, 2] > top_z - 0.02]
        tc = top.mean(0)
        ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)
        rings = []
        for zz, extra in ((top_z - 0.055, 0.004), (top_z - 0.05, 0.008), (top_z - 0.01, 0.0095), (top_z + 0.004, 0.0085), (top_z + 0.008, 0.004)):
            sl = cc[np.abs(cc[:, 2] - min(zz, top_z - 0.008)) < 0.015]
            hull2 = G.hull2d(sl[:, :2]) if len(sl) > 6 else G.hull2d(top[:, :2])
            r = G.polygon_radius(hull2, tc[:2], np.stack([np.sin(ang), -np.cos(ang)], 1))
            r = G.circ_smooth(r, 2) + extra
            rings.append(np.stack([tc[0] + np.sin(ang) * r, tc[1] - np.cos(ang) * r, np.full(48, zz)], 1))
        cuff = G.loft_rings(f'Elara_BootCuff.{s}', rings)
        objs.append(cuff)
        objs.extend(laces(ob, s, sole))
    # hide the skin inside the boots (no poke-through, fewer triangles)
    bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
    hidden = (z < top_z - 0.03) & (bi.leg > 0.3)
    kill = [f for f in bm.faces if all(hidden[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=kill, context='FACES_ONLY')
    bm.to_mesh(me); bm.free(); me.update()
    return objs


def resample_closed(poly, n):
    seg = np.linalg.norm(np.roll(poly, -1, 0) - poly, axis=1)
    L = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, L[-1], n, endpoint=False)
    out = []
    for tt in t:
        i = np.searchsorted(L, tt, side='right') - 1
        f = (tt - L[i]) / max(seg[i], 1e-9)
        out.append(poly[i] + (poly[(i + 1) % len(poly)] - poly[i]) * f)
    return np.array(out)


def laces(boot, s, sole):
    bvh = G.bvh_of(boot)
    cs = np.array([v.co[:] for v in boot.data.vertices])
    out = []
    zs = np.linspace(0.11, 0.31, 7)
    eyelets = []
    for z in zs:
        sl = cs[np.abs(cs[:, 2] - z) < 0.01]
        cx = sl[:, 0].mean()
        row = []
        for dx in (-0.012, 0.012):
            o = Vector((cx + dx, -0.4, z))
            hit = bvh.ray_cast(o, Vector((0, 1, 0)))
            if hit[0] is None:
                break
            row.append(np.array(hit[0]) + np.array(hit[1]) * 0.0025)
        if len(row) == 2:
            eyelets.append(row)
    for a, b in zip(eyelets, eyelets[1:]):
        for p, q in ((a[0], b[1]), (a[1], b[0])):
            mid = (p + q) / 2 + np.array([0, -0.003, 0])
            out.append(G.sweep(f'Elara_Lace.{s}', [p, mid, q], G.circle(6, 0.0016), cap=True))
    return out
