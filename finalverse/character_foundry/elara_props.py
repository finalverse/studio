"""CF1 Elara: belt, crossbody strap, satchel, wooden flute, cloak clasp flower."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

import cf_geo as G


def belt(bi, tunic_bvh, z=None, height=0.038, thick=0.006):
    z = z if z is not None else bi.bone('spine04')[2] + 0.02
    N = 72
    th = np.linspace(0, 2 * np.pi, N, endpoint=False)
    cy = bi.bone('spine04')[1] - 0.01
    rings = []
    for zz, out in ((z - height / 2, 0.0035), (z - height / 2 + 0.002, thick), (z + height / 2 - 0.002, thick), (z + height / 2, 0.0035)):
        ring = []
        for t in th:
            d = Vector((math.sin(t), -math.cos(t), 0))
            o = Vector((0, cy, zz)) + d * 0.5
            hit = tunic_bvh.ray_cast(o, -d)
            p = np.array(hit[0]) if hit[0] is not None else np.array(o - d * 0.35)
            ring.append(p + np.array(d) * out)
        rings.append(np.array(ring))
    ob = G.loft_rings('Elara_Belt', rings)
    # buckle at front, slightly to her right
    a = math.radians(-14)
    d = np.array([math.sin(a), -math.cos(a), 0])
    p = rings[1][int(((a % (2 * np.pi)) / (2 * np.pi)) * N) % N]
    buckle = G.sweep('Elara_Buckle', [p + d * 0.002, p + d * 0.0075],
                     G.rounded_rect(0.046, 0.034, 0.007), cap=True, up=Vector((0, 0, 1)))
    # make it a frame: inner cut-out via a slightly smaller dark plate is enough at this scale
    tongue = G.sweep('Elara_BeltTongue', [p + d * 0.004 + np.array([0.012, 0, 0]), p + d * 0.004 + np.array([0.022, 0, -0.06])],
                     G.rounded_rect(0.032, 0.004, 0.0015), cap=True, up=Vector((0, 0, 1)))
    return ob, buckle, tongue


def strap(bi, surf_bvh, width=0.034, thick=0.005):
    """Crossbody strap: her right shoulder -> across the chest -> left hip; and the back run."""
    shR = bi.bone('shoulder01.R', tail=True); shR = shR + (bi.bone('shoulder01.R') - shR) * 0.35
    hipL = np.array([0.175, bi.bone('spine05')[1] - 0.02, 0.86])
    front, back = [], []
    for t in np.linspace(0, 1, 40):
        p = shR + (hipL - shR) * t
        p[1] = -0.30
        front.append(p)
        q = shR + (hipL - shR) * t
        q[1] = 0.45
        back.append(q)
    out = []
    for name, pts, ray in (('Elara_Strap', front, Vector((0, 1, 0))), ('Elara_StrapBack', back, Vector((0, -1, 0)))):
        path, nrm = [], []
        for p in pts:
            hit = surf_bvh.ray_cast(Vector(p), ray)
            if hit[0] is None:
                continue
            n = np.array(hit[1]);
            if n @ np.array(-ray) < 0:
                n = -n
            path.append(np.array(hit[0]) + n * (thick + 0.002)); nrm.append(n)
        path = np.array(path)
        # over the shoulder: connect the two runs at the top
        for _ in range(4):
            path[1:-1] = .25 * path[:-2] + .5 * path[1:-1] + .25 * path[2:]
        prof = [(0, -width / 2), (thick, -width / 2), (thick, width / 2), (0, width / 2)]
        prof = [(x - thick / 2, y) for x, y in prof]
        out.append(G.sweep(name, path, prof, normals=nrm, cap=True))
    # bridge over the shoulder top
    a = np.array(out[0].data.vertices[0].co); b = np.array(out[1].data.vertices[0].co)
    top = shR + np.array([0, 0, 0.035])
    arc = [a, (a + top) / 2 + np.array([0, 0, 0.012]), top + np.array([0, 0, 0.012]), (b + top) / 2 + np.array([0, 0, 0.012]), b]
    out.append(G.sweep('Elara_StrapTop', arc, [(0, -width / 2), (thick, -width / 2), (thick, width / 2), (0, width / 2)],
                       up=Vector((0, 0, 1)), cap=True))
    return out, hipL


def satchel(anchor, bi):
    """Leather satchel at her left hip: rounded body, domed flap, buckle strap."""
    w, h, d = 0.215, 0.165, 0.070
    c = anchor + np.array([0.035, -0.055, -0.07])
    me = bpy.data.meshes.new('Elara_Satchel')
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w, d, h), verts=bm.verts)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('Elara_Satchel', me); bpy.context.scene.collection.objects.link(ob)
    bev = ob.modifiers.new('round', 'BEVEL'); bev.width = 0.022; bev.segments = 5; bev.limit_method = 'NONE'
    sub = ob.modifiers.new('soft', 'SUBSURF'); sub.levels = 1; sub.render_levels = 1
    G.apply_modifiers(ob)
    # slight bulge and sag
    co = np.array([v.co[:] for v in me.vertices])
    co[:, 1] *= 1 + 0.25 * (1 - (co[:, 0] / (w / 2)) ** 2) * (co[:, 1] < 0)
    co[:, 0] *= 1 - 0.05 * (co[:, 2] > 0)
    me.vertices.foreach_set('co', co.ravel()); me.update()
    # orientation: hang angled to follow the hip
    ob.rotation_euler = (math.radians(4), 0, math.radians(-28))
    ob.location = c
    bpy.context.view_layer.update()
    with bpy.context.temp_override(object=ob, active_object=ob, selected_editable_objects=[ob]):
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # flap: front-top shell
    flap_pts = []
    R = ob.matrix_world.to_3x3()
    Rm = Matrix.Rotation(math.radians(-28), 3, 'Z') @ Matrix.Rotation(math.radians(4), 3, 'X')
    fw = w * 0.96
    rows = []
    for t in np.linspace(0, 1, 12):
        # from the back-top edge over the top and down the front, 70% of the height
        if t < 0.35:
            k = t / 0.35
            y = d / 2 * (1 - 2 * k) * 1.0
            z = h / 2 + 0.006 + 0.004 * math.sin(k * math.pi)
        else:
            k = (t - 0.35) / 0.65
            y = -d / 2 * 1.25 - 0.004
            z = h / 2 - h * 0.62 * k
        row = []
        for x in np.linspace(-fw / 2, fw / 2, 14):
            xx = x * (1 - 0.06 * (t > 0.35) * k ** 2 if t > 0.35 else 1)
            v = Rm @ Vector((xx, y, z))
            row.append(np.array(v) + c)
        rows.append(np.array(row))
    flap = G.loft_rings('Elara_SatchelFlap', rows, closed=False, uv_u=lambda i, N: i / (N - 1))
    sol = flap.modifiers.new('Thickness', 'SOLIDIFY'); sol.thickness = 0.004; sol.offset = 1
    # flap tip rounded via bevel-less trick: fine at this scale
    # buckle strap down the flap front
    a = Rm @ Vector((0, -d / 2 * 1.25 - 0.009, h / 2 - h * 0.45))
    b = Rm @ Vector((0, -d / 2 * 1.30 - 0.010, -h / 2 + 0.03))
    bstrap = G.sweep('Elara_SatchelStrap', [np.array(a) + c, np.array(b) + c], G.rounded_rect(0.026, 0.004, 0.0015),
                     up=Vector(Rm @ Vector((0, -1, 0))), cap=True)
    bk = Rm @ Vector((0, -d / 2 * 1.25 - 0.012, h / 2 - h * 0.55))
    buckle = G.sweep('Elara_SatchelBuckle', [np.array(bk) + c, np.array(bk) + c + np.array(Rm @ Vector((0, -0.005, 0)))],
                     G.rounded_rect(0.034, 0.026, 0.006), cap=True, up=Vector((0, 0, 1)))
    return [ob, flap, bstrap, buckle], c, Rm


def flute(c, Rm):
    """Wooden end-blown flute tucked diagonally behind the satchel strap (reference)."""
    a = c + np.array(Rm @ Vector((0.075, -0.052, 0.20)))
    b = c + np.array(Rm @ Vector((0.120, -0.052, -0.17)))
    pts = [a + (b - a) * t for t in np.linspace(0, 1, 30)]
    sc = [(1, 1)] * 30
    body = G.sweep('Elara_Flute', pts, G.circle(16, 0.0105), scale=sc, up=Vector((1, 0, 0)), cap=True)
    rings = []
    for t in (0.03, 0.30, 0.97):
        p = a + (b - a) * t
        rings.append(G.sweep(f'Elara_FluteRing', [p - (b - a) * 0.012, p + (b - a) * 0.012], G.circle(16, 0.0122), up=Vector((1, 0, 0)), cap=True))
    holes = []
    dvec = (b - a) / np.linalg.norm(b - a)
    side = np.cross(dvec, np.array(Rm @ Vector((0, 1, 0))))
    side /= np.linalg.norm(side)
    face = np.array(Rm @ Vector((0, -1, 0)))
    for t in np.linspace(0.45, 0.85, 6):
        p = a + (b - a) * t + face * 0.0098
        holes.append(G.sweep('Elara_FluteHole', [p - face * 0.0006, p + face * 0.0008], G.circle(10, 0.0028), up=Vector(dvec), cap=True))
    return [body] + rings + holes


def flower(center, normal, name='Elara_Flower', r=0.022, petals=6):
    """Small orange flower brooch (cloak clasp)."""
    n = Vector(normal).normalized()
    t = n.orthogonal().normalized(); b = n.cross(t)
    objs = []
    for k in range(petals):
        a = 2 * math.pi * k / petals
        d = t * math.cos(a) + b * math.sin(a)
        p0 = Vector(center) + n * 0.002
        pts = [np.array(p0 + d * (r * s) + n * (0.006 * math.sin(s * math.pi) - 0.003 * s)) for s in np.linspace(0.1, 1, 8)]
        sc = [(0.0018, 0.0105 * math.sin(min(1, s * 1.1) * math.pi * 0.95) + 0.002) for s in np.linspace(0.1, 1, 8)]
        objs.append(G.sweep(f'{name}Petal', pts, G.circle(8, 1, 1), scale=sc, normals=[tuple(n)] * 8, cap=True))
    objs.append(G.sweep(f'{name}Heart', [np.array(Vector(center) + n * 0.002), np.array(Vector(center) + n * 0.008)], G.circle(12, 0.0055), cap=True, up=Vector(t)))
    return objs
