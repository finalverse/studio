"""CF1 Elara: hooded cloak, cloth-simulated onto the body.

The cloak starts as a lofted, flared panel open at the front, pinned along the
neck/shoulder line, and is draped by Blender's cloth solver (wool preset
values) against collision proxies of the body, tunic and satchel. The hood is
a second panel, folded down onto the shoulders and simulated against the
draped cloak. After the drape the result is frozen into a plain mesh, given
thickness (solidify, outer / lining / rim materials) and skinned.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

import cf_geo as G


def _panel(bi, name, rows, cols, ring_fn, open_fn):
    rings = []
    for r in range(rows):
        s = r / (rows - 1)
        a0, a1 = open_fn(s)
        th = np.linspace(a0, a1, cols)
        rings.append(ring_fn(s, th))
    ob = G.loft_rings(name, rings, closed=False, uv_u=lambda i, N: i / (N - 1))
    G.laplacian(ob, 4, 0.4)
    return ob


def build_cloak_rest(bi, rows=56, cols=72):
    neck = bi.bone('neck01')
    shz = bi.bone('shoulder01.L', tail=True)[2]
    cy = neck[1] + 0.005
    top_z = neck[2] + 0.004
    hem_z = 0.32

    def ring(s, th):
        # s: 0 top (neck) .. 1 hem; th: 0 = front
        z = top_z - (top_z - hem_z) * s
        if s < 0.10:
            k = s / 0.10
            rx = 0.082 + (0.265 - 0.082) * math.sin(k * math.pi / 2)
            ry = 0.074 + (0.165 - 0.074) * math.sin(k * math.pi / 2)
            z = top_z - (top_z - (shz + 0.01)) * k
        else:
            k = (s - 0.10) / 0.90
            rx = 0.265 + 0.11 * k ** 1.2
            ry = 0.165 + 0.15 * k ** 1.2
            z = (shz + 0.01) - ((shz + 0.01) - hem_z) * k
        x = np.sin(th) * rx
        y = cy - np.cos(th) * ry
        # flatten the front of the shoulder line a little
        return np.stack([x, y + 0.02 * (s < 0.1), np.full_like(th, z)], 1)

    def opening(s):
        # narrow gap at the throat clasp, swinging back behind the hands lower down
        a = math.radians(24 + 46 * min(1, s / 0.45) ** 1.3)
        return (a, 2 * math.pi - a)

    ob = _panel(bi, 'Elara_Cloak', rows, cols, ring, opening)
    # pin group: the top rows
    vg = ob.vertex_groups.new(name='pin')
    for v in ob.data.vertices:
        r = v.index // cols
        w = 1.0 if r == 0 else 0.0
        if w:
            vg.add([v.index], w, 'REPLACE')
    return ob


def build_hood_rest(bi, rows=18, cols=48):
    neck = bi.bone('neck01')
    cy = neck[1] + 0.012
    top_z = neck[2] + 0.005

    def ring(s, th):
        # a soft cowl rolling back and down over the upper back
        z = top_z + 0.02 * math.sin(s * math.pi) - 0.17 * s ** 1.4
        rx = 0.10 + 0.13 * math.sin(min(1, s * 1.3) * math.pi / 2)
        ry = 0.095 + 0.12 * s
        back = 0.06 * s
        x = np.sin(th) * rx
        y = cy - np.cos(th) * ry + back * (1 - np.cos(th)) * 0.5
        return np.stack([x, y, np.full_like(th, z)], 1)

    def opening(s):
        a = math.radians(38 + 22 * s)
        return (a, 2 * math.pi - a)
    ob = _panel(bi, 'Elara_Hood', rows, cols, ring, opening)
    vg = ob.vertex_groups.new(name='pin')
    for v in ob.data.vertices:
        if v.index // cols <= 1:
            vg.add([v.index], 1.0, 'REPLACE')
    return ob


def push_out(ob, bvh, margin=0.012, iterations=3):
    """Move any vertex inside/too close to the collision surface outward (stable sim start)."""
    me = ob.data
    for _ in range(iterations):
        moved = 0
        for v in me.vertices:
            loc, nor, idx, dist = bvh.find_nearest(v.co)
            if loc is None:
                continue
            d = v.co - loc
            if d.dot(nor) < margin:
                v.co = loc + nor * margin; moved += 1
        if not moved:
            break
    G.laplacian(ob, 2, 0.3)


def add_collision(ob, outer=0.006):
    m = ob.modifiers.new('Collision', 'COLLISION')
    ob.collision.thickness_outer = outer
    ob.collision.thickness_inner = 0.002
    ob.collision.cloth_friction = 8
    return m


def simulate(ob, frames=70, mass=0.4, tension=15, bending=0.6, shrink=0.0):
    cm = ob.modifiers.new('Cloth', 'CLOTH')
    s = cm.settings
    s.quality = 8
    s.mass = mass
    s.tension_stiffness = tension; s.compression_stiffness = tension
    s.shear_stiffness = tension * 0.6
    s.bending_stiffness = bending
    s.air_damping = 2.0
    s.vertex_group_mass = 'pin'
    s.shrink_min = shrink
    c = cm.collision_settings
    c.use_collision = True
    c.distance_min = 0.004
    c.use_self_collision = False
    c.self_distance_min = 0.003
    c.collision_quality = 4
    cm.point_cache.frame_start = 1
    cm.point_cache.frame_end = frames
    sc = bpy.context.scene
    sc.frame_start = 1; sc.frame_end = frames
    for f in range(1, frames + 1):
        sc.frame_set(f)
    frozen = G.evaluated_copy(ob, ob.name + '_draped')
    sc.frame_set(1)
    name = ob.name
    bpy.data.objects.remove(ob)
    frozen.name = name; frozen.data.name = name
    return frozen


def finish(ob, thickness=0.0045, mats=None):
    sol = ob.modifiers.new('Thickness', 'SOLIDIFY')
    sol.thickness = thickness
    sol.offset = -1
    sol.use_rim = True
    sol.material_offset = 1
    sol.material_offset_rim = 2
    sol.use_even_offset = False
    sol.use_quality_normals = True
    if mats:
        for m in mats:
            ob.data.materials.append(m)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def hood_from_cloak(cloak, rows, cols, name='Elara_Hood'):
    """Hood lying down on the back: a padded cowl that follows the draped cloak's
    top rows, deepening into a soft pointed lobe at the centre back."""
    co = np.array([v.co[:] for v in cloak.data.vertices]).reshape(rows, cols, 3)
    du = np.gradient(co, axis=1); dv = np.gradient(co, axis=0)
    nrm = np.cross(du, dv)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-9)
    out_rows = 16
    rings = []
    for k in range(out_rows):
        s = k / (out_rows - 1)
        ring = []
        for c in range(cols):
            u = c / (cols - 1)
            depth = 7 + 15 * math.exp(-((u - 0.5) / 0.13) ** 2)      # rows covered by the hood
            depth *= min(1.0, 0.45 + 4 * min(u, 1 - u))              # taper toward the front edges
            rr = s * depth
            r0 = int(min(rows - 2, math.floor(rr))); f = rr - r0
            p = co[r0, c] * (1 - f) + co[r0 + 1, c] * f
            n = nrm[r0, c] * (1 - f) + nrm[r0 + 1, c] * f
            n /= max(np.linalg.norm(n), 1e-9)
            # make n point away from the body (outward from the neck axis)
            radial = p - np.array([0, co[0, :, 1].mean(), p[2]]); radial[2] = 0
            if n @ radial < 0:
                n = -n
            puff = 0.007 + 0.026 * math.sin(math.pi * min(1.0, s * 1.05)) * (0.2 + 0.8 * math.exp(-((u - 0.5) / 0.18) ** 2))
            ring.append(p + n * puff + np.array([0, 0, 0.012 * (1 - s)]))
        rings.append(np.array(ring))
    ob = G.loft_rings(name, rings, closed=False, uv_u=lambda i, N: i / (N - 1))
    G.laplacian(ob, 4, 0.4)
    return ob
