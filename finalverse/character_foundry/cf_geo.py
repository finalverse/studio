"""Character Foundry geometry helpers: hulls, lofts, sweeps, BVH queries."""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def hull2d(pts):
    pts = sorted(set(map(tuple, np.round(pts, 6))))
    if len(pts) < 3:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return np.array(lo[:-1] + up[:-1])


def polygon_radius(poly, center, dirs):
    """Distance from center along each unit dir (Nx2) to the polygon boundary (max hit)."""
    out = np.zeros(len(dirs))
    a = poly; b = np.roll(poly, -1, 0)
    for i, d in enumerate(dirs):
        best = 0.0
        for p, q in zip(a, b):
            e = q - p
            den = d[0] * (-e[1]) - d[1] * (-e[0])
            if abs(den) < 1e-12:
                continue
            w = p - center
            t = (w[0] * (-e[1]) - w[1] * (-e[0])) / den
            s = (d[0] * w[1] - d[1] * w[0]) / den
            if t > 0 and -1e-9 <= s <= 1 + 1e-9:
                best = max(best, t)
        out[i] = best
    return out


def circ_smooth(x, k):
    if k <= 0:
        return x
    n = len(x); out = np.zeros_like(x)
    w = np.exp(-0.5 * (np.arange(-3 * k, 3 * k + 1) / k) ** 2); w /= w.sum()
    for j, wj in zip(range(-3 * k, 3 * k + 1), w):
        out += wj * np.roll(x, j)
    return out


def loft_rings(name, rings, closed=True, uv_u=None, uv_v=None, cap=False):
    """rings: list of (N x 3) arrays. Returns a mesh object with UVs (u around, v along)."""
    R = len(rings); N = len(rings[0])
    verts = np.concatenate(rings)
    faces = []
    M = N if closed else N - 1
    for r in range(R - 1):
        for i in range(M):
            j = (i + 1) % N
            faces.append((r * N + i, r * N + j, (r + 1) * N + j, (r + 1) * N + i))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    # arc-length v
    if uv_v is None:
        mid = np.array([ring.mean(0) for ring in rings])
        L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(mid, axis=0), axis=1))])
        uv_v = 1 - L / max(L[-1], 1e-6)
    uvl = me.uv_layers.new(name='UVMap')
    uvs = []
    for r in range(R - 1):
        for i in range(M):
            for (rr, ii) in ((r, i), (r, i + 1), (r + 1, i + 1), (r + 1, i)):
                u = (ii / N) if uv_u is None else uv_u(ii, N)
                uvs.extend((u, uv_v[rr]))
    uvl.data.foreach_set('uv', uvs)
    for p in me.polygons:
        p.use_smooth = True
    me.update()
    if closed:
        outward_normals(me)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def outward_normals(me):
    """Make face normals point away from the mesh's ring centres (lofts are tubes)."""
    me.update()
    co = np.array([v.co[:] for v in me.vertices])
    c = co.mean(0)
    score = 0.0
    for p in me.polygons:
        score += np.dot(np.array(p.normal), np.array(p.center) - c) * p.area
    if score < 0:
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bm.to_mesh(me); bm.free(); me.update()


def frame_along(points, up=Vector((0, 0, 1))):
    """Parallel-transport frames (tangent, normal, binormal) along a polyline."""
    P = [Vector(p) for p in points]
    T = []
    for i in range(len(P)):
        a = P[max(i - 1, 0)]; b = P[min(i + 1, len(P) - 1)]
        T.append((b - a).normalized())
    n = up.cross(T[0])
    if n.length < 1e-6:
        n = Vector((1, 0, 0)).cross(T[0])
    n.normalize()
    N = [n]
    for i in range(1, len(P)):
        q = T[i - 1].rotation_difference(T[i])
        N.append((q @ N[-1]).normalized())
    B = [t.cross(nn) for t, nn in zip(T, N)]
    return P, T, N, B


def sweep(name, points, profile, scale=None, twist=None, up=Vector((0, 0, 1)), cap=True, normals=None):
    """Sweep a 2D profile (K x 2, in (N,B) plane) along points. Optional per-point
    scale (sx, sy) and twist (radians). Optional explicit normal vectors per point."""
    P, T, N, B = frame_along(points, up)
    if normals is not None:
        N = [Vector(n) for n in normals]
        N = [(n - t * n.dot(t)).normalized() for n, t in zip(N, T)]
        B = [t.cross(n) for t, n in zip(T, N)]
    rings = []
    for i in range(len(P)):
        sx, sy = (scale[i] if scale is not None else (1, 1))
        a = twist[i] if twist is not None else 0
        ca, sa = math.cos(a), math.sin(a)
        ring = []
        for (x, y) in profile:
            x2, y2 = x * ca - y * sa, x * sa + y * ca
            ring.append(P[i] + N[i] * (x2 * sx) + B[i] * (y2 * sy))
        rings.append(np.array([tuple(v) for v in ring]))
    ob = loft_rings(name, rings)
    if cap:
        cap_ends(ob, len(profile), len(points))
    return ob


def cap_ends(ob, K, R):
    bm = bmesh.new(); bm.from_mesh(ob.data); bm.verts.ensure_lookup_table()
    for r in (0, R - 1):
        vs = [bm.verts[r * K + k] for k in range(K)]
        try:
            f = bm.faces.new(vs if r else list(reversed(vs)))
            f.smooth = False
        except ValueError:
            pass
    bm.normal_update()
    bm.to_mesh(ob.data); bm.free()


def circle(n, rx, ry=None):
    ry = rx if ry is None else ry
    return [(rx * math.cos(2 * math.pi * i / n), ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rounded_rect(w, h, r, n=4):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def bvh_of(obj, face_filter=None, world=True):
    me = obj.data
    M = obj.matrix_world if world else Matrix()
    verts = [M @ v.co for v in me.vertices]
    polys = [list(p.vertices) for p in me.polygons if face_filter is None or face_filter(p)]
    return BVHTree.FromPolygons(verts, polys)


def evaluated_copy(obj, name=None):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    ob = bpy.data.objects.new(name or obj.name + '_eval', me)
    bpy.context.scene.collection.objects.link(ob)
    ob.matrix_world = obj.matrix_world
    return ob


def apply_modifiers(obj, keep=('Armature',)):
    for m in list(obj.modifiers):
        if m.name in keep or m.type == 'ARMATURE':
            continue
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.object.modifier_apply(modifier=m.name)


def join(objs, name):
    base = objs[0]
    with bpy.context.temp_override(active_object=base, selected_editable_objects=objs, object=base):
        bpy.ops.object.join()
    base.name = name; base.data.name = name
    return base


def laplacian(obj, iterations, factor=.5, pin=None):
    me = obj.data
    co = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    e = np.zeros(len(me.edges) * 2, np.int64); me.edges.foreach_get('vertices', e); e = e.reshape(-1, 2)
    for _ in range(iterations):
        acc = np.zeros_like(co); cnt = np.zeros(len(co))
        np.add.at(acc, e[:, 0], co[e[:, 1]]); np.add.at(acc, e[:, 1], co[e[:, 0]])
        np.add.at(cnt, e[:, 0], 1); np.add.at(cnt, e[:, 1], 1)
        new = co * (1 - factor) + factor * acc / np.maximum(cnt, 1)[:, None]
        if pin is not None:
            new[pin] = co[pin]
        co = new
    me.vertices.foreach_set('co', co.ravel()); me.update()


def material(name, color=(.8, .8, .8), rough=.5, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    m.diffuse_color = (*color, 1)
    return m


def uv_smart(ob, angle=66):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    if not ob.data.uv_layers:
        ob.data.uv_layers.new(name='UVMap')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=0.01)
    bpy.ops.object.mode_set(mode='OBJECT')
