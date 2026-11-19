# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""V1 reviewed founder anatomy templates (Q2 production-stylized target).

Each founder is a fixed, reviewed parameter template: primitives are grouped
into parts (material zone × E1 joint × runtime role), each part is fused into a
continuous surface with a voxel remesh, relaxed, optionally given real
geometric surface detail (bark, molten crust) and decimated to a triangle
budget. Parts are rigid per E1 joint, which is exactly what Infinity's E1 path
animates; roles `flame` and `petal` drive its procedural flicker/flutter.
No model-provided geometry or code is interpreted: a planner only chooses the
founder, height and a bounded palette. Original CC0 geometry; no third-party
assets are used."""
import json
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from .creation2 import PART_ATTR, PARTS, CreationError

ROLES = ('solid', 'expressive_detail', 'flame', 'petal')


class Part:
    def __init__(self, name, zone, joint=None, role='solid', voxel=.012, smooth=4, detail=None, tris=1800):
        self.name, self.zone, self.joint, self.role = name, zone, joint, role
        self.voxel, self.smooth, self.detail, self.tris = voxel, smooth, detail, tris
        self.prims = []

    def ell(self, c, r, seg=24):
        self.prims.append(('ell', Vector(c), Vector(r), seg)); return self

    def cap(self, a, b, r1, r2=None, seg=16):
        self.prims.append(('cap', Vector(a), Vector(b), r1, r1 if r2 is None else r2, seg)); return self

    def box(self, c, s):
        self.prims.append(('box', Vector(c), Vector(s))); return self

    def tube(self, points, radii, seg=10):
        for (a, b), (r1, r2) in zip(zip(points, points[1:]), zip(radii, radii[1:])):
            self.cap(a, b, r1, r2, seg)
            self.ell(b, (r2, r2, r2), max(8, seg))
        return self


def _add(bm, prim):
    kind = prim[0]
    if kind == 'ell':
        _, c, r, seg = prim
        g = bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg//2), radius=1)
        bmesh.ops.transform(bm, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*r, 1)), verts=g['verts'])
    elif kind == 'cap':
        _, a, b, r1, r2, seg = prim
        d = b - a
        if d.length < 1e-5:
            return
        g = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r1, radius2=max(r2, 1e-4), depth=d.length)
        rot = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        bmesh.ops.transform(bm, matrix=Matrix.Translation((a+b)/2) @ rot, verts=g['verts'])
    elif kind == 'box':
        _, c, s = prim
        g = bmesh.ops.create_cube(bm, size=1)
        bmesh.ops.transform(bm, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)), verts=g['verts'])


def _texture(kind, scale, seed):
    tex = bpy.data.textures.new('fv-detail', 'VORONOI' if kind == 'cells' else 'CLOUDS')
    tex.noise_scale = scale
    if kind != 'cells':
        tex.noise_depth = 2; tex.noise_basis = 'ORIGINAL_PERLIN'
    tex['finalverse.seed'] = seed
    return tex


def _build_part(scene, part, h, seed):
    bm = bmesh.new()
    for prim in part.prims:
        _add(bm, prim)
    mesh = bpy.data.meshes.new('fv-part'); bm.to_mesh(mesh); bm.free()
    temp = bpy.data.objects.new('fv-part', mesh); scene.collection.objects.link(temp)
    textures = []
    try:
        if part.voxel:
            # Octree "smooth" remesh fuses primitives into one continuous surface without
            # OpenVDB (disabled in the reduced Studio build profile; voxel mode would no-op).
            # Voxel remesh (OpenVDB) gives a closed manifold surface; the octree fallback
            # leaves holes at thin overlaps, which render as dark seams.
            size = max(temp.dimensions) if max(temp.dimensions) > 0 else h
            m = temp.modifiers.new('fuse', 'REMESH'); m.use_smooth_shade = True
            if bpy.app.build_options.openvdb:
                m.mode = 'VOXEL'; m.voxel_size = max(part.voxel*h, size/256); m.adaptivity = 0
            else:
                m.mode = 'SMOOTH'; m.scale = .99
                m.octree_depth = max(4, min(8, math.ceil(math.log2(size/(part.voxel*h)))))
                m.use_remove_disconnected = False
        if part.smooth:
            m = temp.modifiers.new('relax', 'LAPLACIANSMOOTH'); m.iterations = part.smooth
            m.lambda_factor = .5; m.use_volume_preserve = True
        if part.detail:
            kind, strength, scale = part.detail
            tex = _texture(kind, scale*h, seed); textures.append(tex)
            m = temp.modifiers.new('detail', 'DISPLACE'); m.texture = tex; m.strength = strength*h
            m.mid_level = .5; m.texture_coords = 'LOCAL'
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        fused = bpy.data.meshes.new_from_object(temp.evaluated_get(depsgraph))
        tris = sum(len(p.vertices)-2 for p in fused.polygons)
        if tris > part.tris:
            temp.data = fused
            for m in list(temp.modifiers):
                temp.modifiers.remove(m)
            d = temp.modifiers.new('budget', 'DECIMATE'); d.ratio = part.tris/tris
            bpy.context.view_layer.update()
            reduced = bpy.data.meshes.new_from_object(temp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
            temp.data = mesh
            bpy.data.meshes.remove(fused); fused = reduced
        # Decimating thin voxel shells (flames, petals) can leave zero-area triangles,
        # which the package validator rightly rejects; dissolve them here.
        bm = bmesh.new(); bm.from_mesh(fused)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-5*h, edges=bm.edges)
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')
        bm.to_mesh(fused); bm.free()
        return fused
    finally:
        bpy.data.objects.remove(temp)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        for t in textures:
            bpy.data.textures.remove(t)


def _material(name, color, rough, metal=0.0, emit=(0, 0, 0), strength=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    s = m.node_tree.nodes.get('Principled BSDF')
    s.inputs['Base Color'].default_value = (*color, 1)
    s.inputs['Roughness'].default_value = rough; s.inputs['Metallic'].default_value = metal
    s.inputs['Emission Color'].default_value = (*emit, 1); s.inputs['Emission Strength'].default_value = strength
    m.diffuse_color = (*color, 1)
    return m


def assemble(scene, name, parts, zones, h, location, seed):
    """Fuse each part, then merge all parts into one canonical mesh."""
    coords, faces, part_of, material_of = [], [], [], []
    zone_names = list(zones)
    for index, part in enumerate(parts):
        mesh = _build_part(scene, part, h, seed + index)
        base = len(coords)
        coords += [tuple(round(c, 6) for c in v.co) for v in mesh.vertices]
        for p in mesh.polygons:
            ids = [base + i for i in p.vertices]; k = ids.index(min(ids))
            faces.append((index, tuple(ids[k:] + ids[:k])))
        bpy.data.meshes.remove(mesh)
    faces.sort()
    if len(coords) > 100000:
        raise CreationError('Founder exceeds 100,000 vertices')
    mesh = bpy.data.meshes.new(name); mesh.from_pydata(coords, [], [f for _, f in faces]); mesh.update()
    attr = mesh.attributes.new(PART_ATTR, 'INT', 'FACE'); attr.data.foreach_set('value', [p for p, _ in faces])
    for zone in zone_names:
        mesh.materials.append(_material(f'{name} {zone}', *zones[zone]))
    for poly, (p, _) in zip(mesh.polygons, faces):
        poly.material_index = zone_names.index(parts[p].zone); poly.use_smooth = True
    block = bpy.data.objects.new(name, mesh); scene.collection.objects.link(block); block.location = location
    block[PARTS] = json.dumps([[p.name, p.zone, p.joint, p.role] for p in parts])
    joints = sorted({p.joint for p in parts if p.joint})
    for j in joints:
        group = block.vertex_groups.new(name=j)
        verts = {i for poly in mesh.polygons if parts[faces[poly.index][0]].joint == j for i in poly.vertices}
        group.add(sorted(verts), 1.0, 'REPLACE')
    for m in mesh.materials:
        m['finalverse.founder'] = name
    return block


# --- founders (Blender Z-up, metres, front = -Y, origin at ground contact) ---------
def palette(item, defaults):
    """Planner palette overrides: only existing zones, base colour only, ≤ 0.85 for emissive zones."""
    out = dict(defaults)
    for entry in item.get('palette') or []:
        zone, rgb = entry['zone'], entry['color']
        if zone not in out:
            raise CreationError(f'Founder has no {zone!r} zone; zones: ' + ', '.join(out))
        c, *rest = out[zone]
        if len(rest) >= 4 and rest[3] > 0:
            rgb = [min(.85, x) for x in rgb]  # keep luminous zones off white under Khronos Neutral
        out[zone] = (tuple(rgb), *rest)
    return out


def face(parts, h, head_c, head_r, iris, joint='head', brows=None, mouth=True):
    # joint=None for skeleton-free spirits
    """Eyes with sclera, iris and pupil, brows and a mouth line on the -Y face."""
    x, y, z = head_c; hy = head_r[1]
    eyes = Part('eye whites', 'sclera', joint, 'expressive_detail', voxel=None, smooth=0, tris=600)
    irises = Part('irises', 'iris', joint, 'expressive_detail', voxel=None, smooth=0, tris=500)
    pupils = Part('pupils', 'pupil', joint, 'expressive_detail', voxel=None, smooth=0, tris=400)
    for s in (1, -1):
        ex = x + s*head_r[0]*.38; ey = y - hy*.86; ez = z + head_r[2]*.12
        eyes.ell((ex, ey, ez), (h*.016, h*.008, h*.012), 16)
        irises.ell((ex, ey - h*.006, ez), (h*.010, h*.005, h*.010), 14)
        pupils.ell((ex, ey - h*.009, ez), (h*.005, h*.003, h*.005), 12)
    parts += [eyes, irises, pupils]
    if brows:
        b = Part('brows', brows, joint, 'expressive_detail', voxel=None, smooth=0, tris=200)
        for s in (1, -1):
            b.cap((x + s*head_r[0]*.18, y - hy*.88, z + head_r[2]*.33), (x + s*head_r[0]*.58, y - hy*.8, z + head_r[2]*.36),
                  h*.004, h*.003, 8)
        parts.append(b)
    if mouth:
        parts.append(Part('mouth', 'pupil', joint, 'expressive_detail', voxel=None, smooth=0, tris=120)
                     .cap((x - head_r[0]*.22, y - hy*.93, z - head_r[2]*.42), (x + head_r[0]*.22, y - hy*.93, z - head_r[2]*.42),
                          h*.0035, h*.0035, 8))


def human_body(parts, h, skin, outfit, boots, build=1.0):
    """Shared stylized human anatomy split by E1 joint; clothing zones wrap it."""
    w = build
    head = Part('head', skin, 'head', tris=3200).ell((0, 0, h*.905), (h*.066, h*.072, h*.082), 32)
    head.cap((0, 0, h*.80), (0, 0, h*.86), h*.03, h*.032)          # neck
    head.ell((h*.064, 0, h*.905), (h*.012, h*.02, h*.026), 12); head.ell((-h*.064, 0, h*.905), (h*.012, h*.02, h*.026), 12)
    head.ell((0, -h*.07, h*.895), (h*.012, h*.016, h*.02), 12)     # nose
    parts.append(head)
    torso = Part('torso', outfit['torso'], 'root', voxel=.009, tris=3400)
    torso.ell((0, 0, h*.66), (h*.118*w, h*.072, h*.15), 28).ell((0, 0, h*.53), (h*.104*w, h*.066, h*.08), 24)
    torso.ell((0, 0, h*.745), (h*.15*w, h*.068, h*.045), 20)        # shoulders
    parts.append(torso)
    for s, side in ((1, 'l'), (-1, 'r')):
        arm = Part(f'sleeve {side}', outfit['sleeve'], f'arm_{side}', voxel=.008, tris=1800)
        arm.tube([(s*h*.15*w, 0, h*.745), (s*h*.185*w, 0, h*.60), (s*h*.2*w, -h*.01, h*.47)], [h*.036, h*.031, h*.027])
        parts.append(arm)
        hand = Part(f'hand {side}', skin, f'arm_{side}', voxel=.006, tris=800)
        hand.ell((s*h*.205*w, -h*.012, h*.43), (h*.022, h*.018, h*.034), 16)
        hand.cap((s*h*.198*w, -h*.025, h*.44), (s*h*.19*w, -h*.03, h*.415), h*.007)   # thumb
        parts.append(hand)
        leg = Part(f'leg {side}', outfit['leg'], f'leg_{side}', voxel=.008, tris=2000)
        leg.tube([(s*h*.06, 0, h*.49), (s*h*.064, -h*.005, h*.27), (s*h*.066, 0, h*.1)], [h*.05, h*.04, h*.034])
        parts.append(leg)
        boot = Part(f'boot {side}', boots, f'leg_{side}', voxel=.008, tris=1200)
        boot.cap((s*h*.066, 0, h*.14), (s*h*.066, 0, h*.04), h*.037, h*.035).ell((s*h*.066, -h*.035, h*.025), (h*.036, h*.07, h*.026), 20)
        parts.append(boot)


def elara(item):
    h = item['height']
    zones = palette(item, {'skin': ((.78, .55, .42), .62), 'hair': ((.42, .12, .04), .55),
        'tunic': ((.12, .36, .17), .78), 'cloak': ((.07, .17, .42), .82), 'leather': ((.32, .17, .08), .58),
        'trousers': ((.24, .19, .13), .8), 'sclera': ((.92, .9, .86), .3), 'iris': ((.12, .42, .26), .25),
        'pupil': ((.03, .02, .02), .3), 'gold': ((.85, .62, .25), .3, .8)})
    parts = []
    human_body(parts, h, 'skin', {'torso': 'tunic', 'sleeve': 'tunic', 'leg': 'trousers'}, 'leather', .95)
    face(parts, h, (0, 0, h*.905), (h*.066, h*.072, h*.082), 'iris', brows='hair')
    hair = Part('hair', 'hair', 'head', detail=('clouds', .006, .03), tris=2400)
    hair.ell((0, h*.008, h*.935), (h*.074, h*.078, h*.068), 28).ell((0, h*.035, h*.88), (h*.06, h*.045, h*.07), 20)
    hair.ell((h*.055, -h*.02, h*.9), (h*.022, h*.035, h*.05), 14).ell((-h*.055, -h*.02, h*.9), (h*.022, h*.035, h*.05), 14)
    parts.append(hair)
    braid = Part('braid', 'hair', 'head', voxel=.008, tris=1400)
    braid.tube([(h*.03, h*.07, h*.87), (h*.045, h*.075, h*.78), (h*.05, h*.07, h*.69), (h*.055, h*.06, h*.62)],
               [h*.02, h*.018, h*.016, h*.008])
    parts.append(braid)
    cloak = Part('cloak', 'cloak', 'root', voxel=.008, smooth=6, tris=2600)
    cloak.ell((0, h*.045, h*.765), (h*.165, h*.06, h*.032), 24)               # shoulder drape
    for z, w, y in ((.68, .16, .085), (.56, .175, .1), (.44, .19, .112), (.33, .2, .12)):
        cloak.ell((0, h*y, h*z), (h*w, h*.022, h*.075), 24)                     # curved back shell, open at the front
    cloak.ell((h*.07, -h*.055, h*.79), (h*.018, h*.012, h*.018), 10).ell((-h*.07, -h*.055, h*.79), (h*.018, h*.012, h*.018), 10)
    parts.append(cloak)
    belt = Part('belt and satchel', 'leather', 'root', tris=1200)
    belt.cap((0, 0, h*.505), (0, 0, h*.535), h*.11, h*.11, 24)
    belt.box((h*.13, -h*.02, h*.46), (h*.05, h*.03, h*.06)).cap((h*.1, -h*.06, h*.72), (h*.13, -h*.04, h*.49), h*.006)
    parts.append(belt)
    parts.append(Part('buckle', 'gold', 'root', voxel=None, smooth=0, tris=200).box((0, -h*.072, h*.52), (h*.025, h*.008, h*.02)))
    return parts, zones


def auren(item):
    h = item['height']
    zones = palette(item, {'skin': ((.72, .52, .4), .6), 'hair': ((.16, .1, .06), .6),
        'jacket': ((.16, .17, .19), .7), 'shirt': ((.07, .075, .085), .75), 'trousers': ((.1, .1, .11), .78),
        'shoes': ((.06, .05, .05), .45), 'sclera': ((.92, .9, .86), .3), 'iris': ((.5, .42, .3), .25),
        'pupil': ((.03, .02, .02), .3), 'light': ((.2, .55, .7), .3, 0, (.25, .75, 1.0), 2.5)})
    parts = []
    human_body(parts, h, 'skin', {'torso': 'shirt', 'sleeve': 'jacket', 'leg': 'trousers'}, 'shoes', 1.02)
    face(parts, h, (0, 0, h*.905), (h*.066, h*.072, h*.082), 'iris', brows='hair')
    hair = Part('wavy hair', 'hair', 'head', detail=('clouds', .008, .05), tris=2200)
    hair.ell((0, h*.006, h*.94), (h*.071, h*.076, h*.06), 28).ell((0, h*.03, h*.9), (h*.066, h*.05, h*.05), 20)
    parts.append(hair)
    jacket = Part('tailored jacket', 'jacket', 'root', voxel=.009, tris=3200)
    jacket.ell((0, 0, h*.665), (h*.128, h*.08, h*.155), 28).ell((0, 0, h*.75), (h*.158, h*.074, h*.05), 20)
    jacket.cap((0, 0, h*.62), (0, 0, h*.46), h*.13, h*.125, 24)
    jacket.cap((h*.03, -h*.08, h*.78), (h*.05, -h*.085, h*.62), h*.012).cap((-h*.03, -h*.08, h*.78), (-h*.05, -h*.085, h*.62), h*.012)  # lapels
    parts.append(jacket)
    glow = Part('luminous trim', 'light', 'root', voxel=None, smooth=0, tris=300)
    glow.cap((h*.0, -h*.082, h*.60), (h*.0, -h*.08, h*.47), h*.003).cap((-h*.12, -h*.04, h*.47), (h*.12, -h*.04, h*.47), h*.003)
    parts.append(glow)
    for s, side in ((1, 'l'), (-1, 'r')):
        parts.append(Part(f'cuff light {side}', 'light', f'arm_{side}', voxel=None, smooth=0, tris=120)
                     .cap((s*h*.198, -h*.012, h*.465), (s*h*.202, -h*.012, h*.455), h*.029))
    return parts, zones


def kai(item):
    h = item['height']
    zones = palette(item, {'gold': ((.86, .62, .2), .26, .95), 'joint': ((.18, .14, .1), .4, .9),
        'core': ((1.0, .75, .3), .3, 0, (1.0, .62, .18), 4.0), 'visor': ((.3, .7, .9), .2, 0, (.35, .85, 1.0), 3.0),
        'panel': ((.55, .38, .12), .35, .9)})
    parts = []
    head = Part('helm', 'gold', 'head', voxel=.01, tris=1800).ell((0, 0, h*.905), (h*.06, h*.066, h*.078), 28)
    head.cap((0, 0, h*.8), (0, 0, h*.86), h*.026, h*.028)
    parts.append(head)
    parts.append(Part('visor', 'visor', 'head', voxel=None, smooth=0, tris=300).ell((0, -h*.058, h*.91), (h*.045, h*.012, h*.016), 20))
    for z in (.97, .84):
        parts.append(Part('helm ring', 'joint', 'head', voxel=.006, smooth=1, tris=500).cap((0, 0, h*z), (0, 0, h*(z+.008)), h*.064*(1 if z > .9 else .45)))
    chest = Part('chest plating', 'gold', 'root', voxel=.009, tris=2600)
    chest.ell((0, 0, h*.68), (h*.13, h*.075, h*.12), 28).ell((0, 0, h*.53), (h*.09, h*.06, h*.07), 20)
    chest.ell((h*.15, 0, h*.75), (h*.05, h*.055, h*.045), 16).ell((-h*.15, 0, h*.75), (h*.05, h*.055, h*.045), 16)
    parts.append(chest)
    parts.append(Part('energy core', 'core', 'root', voxel=None, smooth=0, tris=500).ell((0, -h*.072, h*.68), (h*.035, h*.012, h*.035), 20))
    seams = Part('energy seams', 'core', 'root', voxel=None, smooth=0, tris=600)
    for z in (.6, .56, .52):
        seams.cap((-h*.08, -h*.06, h*z), (h*.08, -h*.06, h*z), h*.0035)
    parts.append(seams)
    parts.append(Part('waist joint', 'joint', 'root', voxel=.008, tris=700).cap((0, 0, h*.47), (0, 0, h*.5), h*.08, h*.085, 20))
    for s, side in ((1, 'l'), (-1, 'r')):
        a = Part(f'arm plates {side}', 'gold', f'arm_{side}', voxel=.008, tris=1100)
        a.cap((s*h*.16, 0, h*.72), (s*h*.19, 0, h*.6), h*.032, h*.03).cap((s*h*.195, 0, h*.57), (s*h*.205, -h*.01, h*.46), h*.028, h*.024)
        parts.append(a)
        parts.append(Part(f'elbow {side}', 'joint', f'arm_{side}', voxel=None, smooth=0, tris=300).ell((s*h*.192, 0, h*.585), (h*.03, h*.03, h*.026), 14))
        parts.append(Part(f'hand {side}', 'panel', f'arm_{side}', voxel=.006, tris=500).ell((s*h*.207, -h*.012, h*.43), (h*.02, h*.017, h*.032), 14))
        l = Part(f'leg plates {side}', 'gold', f'leg_{side}', voxel=.009, tris=1300)
        l.cap((s*h*.06, 0, h*.47), (s*h*.064, 0, h*.29), h*.05, h*.04).cap((s*h*.065, 0, h*.26), (s*h*.066, 0, h*.07), h*.038, h*.032)
        l.ell((s*h*.066, -h*.035, h*.03), (h*.034, h*.07, h*.026), 18)
        parts.append(l)
        parts.append(Part(f'knee {side}', 'joint', f'leg_{side}', voxel=None, smooth=0, tris=300).ell((s*h*.065, -h*.005, h*.275), (h*.036, h*.036, h*.03), 14))
        parts.append(Part(f'limb light {side}', 'core', f'leg_{side}', voxel=None, smooth=0, tris=200).cap((s*h*.065, -h*.04, h*.4), (s*h*.065, -h*.036, h*.32), h*.004))
    return parts, zones


def lumi(item):
    h = item['height']
    zones = palette(item, {'body': ((.62, .86, .78), .5, 0, (.22, .55, .45), 1.1),
        'glow': ((.72, .95, .9), .4, 0, (.45, 1.0, .85), 2.2), 'sclera': ((.94, .97, .96), .25),
        'iris': ((.06, .36, .42), .2), 'pupil': ((.02, .03, .04), .25)})
    # One continuous floating silhouette: body, crown and fins fused by the remesh. No arms or legs.
    body = Part('continuous spirit body', 'body', None, voxel=.016, smooth=8, tris=5200)
    body.ell((0, 0, h*.42), (h*.3, h*.26, h*.32), 40).ell((0, 0, h*.68), (h*.33, h*.27, h*.25), 40)
    body.cap((0, 0, h*.82), (0, h*.03, h*1.0), h*.13, h*.01, 24)                         # crown tip
    for s in (1, -1):
        body.ell((s*h*.32, h*.02, h*.62), (h*.13, h*.05, h*.08), 20)                       # soft crown fins
        body.ell((s*h*.27, 0, h*.34), (h*.05, h*.04, h*.09), 16)                           # subtle side fins
    body.cap((0, 0, h*.14), (0, h*.04, h*.04), h*.13, h*.02, 24)                          # tapering wisp, not legs
    # Canon: large expressive eyes (V0 sheet). Eye scale and spacing sized for a ~1 m spirit.
    face(parts := [body], h*4.2, (0, -h*.17, h*.6), (h*.2, h*.1, h*.1), 'iris', joint=None, mouth=False)
    parts.append(Part('cheek glow', 'glow', None, 'expressive_detail', voxel=None, smooth=0, tris=300)
                 .ell((h*.16, -h*.235, h*.5), (h*.03, h*.01, h*.018), 14).ell((-h*.16, -h*.235, h*.5), (h*.03, h*.01, h*.018), 14))
    parts.append(Part('heart light', 'glow', None, voxel=None, smooth=0, tris=300).ell((0, -h*.255, h*.38), (h*.035, h*.01, h*.035), 16))
    return parts, zones


def terra(item):
    h = item['height']
    zones = palette(item, {'bark': ((.24, .15, .08), .92), 'deep bark': ((.14, .09, .05), .95),
        'moss': ((.22, .4, .12), .9), 'leaf': ((.18, .45, .14), .75), 'leaf light': ((.42, .62, .18), .7),
        'amber': ((1.0, .62, .15), .3, 0, (1.0, .55, .12), 3.5)})
    parts = []
    trunk = Part('bark trunk', 'bark', 'trunk', voxel=.012, detail=('cells', .012, .06), tris=5200)
    trunk.cap((0, 0, h*.08), (0, 0, h*.62), h*.15, h*.12, 32).ell((0, 0, h*.62), (h*.16, h*.12, h*.1), 28)
    trunk.ell((0, 0, h*.18), (h*.19, h*.16, h*.12), 28)
    parts.append(trunk)
    roots = Part('roots', 'deep bark', 'trunk', voxel=.01, detail=('cells', .008, .05), tris=2400)
    for i in range(6):
        a = i*math.tau/6 + .3
        roots.tube([(math.cos(a)*h*.1, math.sin(a)*h*.08, h*.14), (math.cos(a)*h*.22, math.sin(a)*h*.18, h*.05),
                    (math.cos(a)*h*.3, math.sin(a)*h*.26, h*.012)], [h*.05, h*.03, h*.012])
    parts.append(roots)
    for s, side in ((1, 'l'), (-1, 'r')):
        b = Part(f'branch arm {side}', 'bark', f'branch_{side}', voxel=.01, detail=('cells', .008, .05), tris=1800)
        b.tube([(s*h*.12, 0, h*.55), (s*h*.24, -h*.02, h*.5), (s*h*.3, -h*.05, h*.38), (s*h*.31, -h*.06, h*.3)],
               [h*.05, h*.04, h*.028, h*.012])
        b.cap((s*h*.3, -h*.05, h*.38), (s*h*.36, -h*.07, h*.34), h*.012, h*.004)
        parts.append(b)
        parts.append(Part(f'shoulder moss {side}', 'moss', f'branch_{side}', detail=('clouds', .01, .04), tris=900)
                     .ell((s*h*.14, 0, h*.6), (h*.07, h*.08, h*.04), 16))
    canopy = Part('living canopy', 'leaf', 'canopy', voxel=.016, detail=('clouds', .02, .08), tris=4200)
    for i, (x, y, z, r) in enumerate([(0, 0, .86, .2), (.16, .04, .8, .14), (-.17, .02, .81, .15), (.05, .12, .9, .13),
                                       (-.06, -.1, .88, .12), (.0, .02, .98, .12)]):
        canopy.ell((x*h, y*h, z*h), (r*h, r*h, r*h*.8), 20)
    parts.append(canopy)
    parts.append(Part('canopy highlights', 'leaf light', 'canopy', voxel=.012, detail=('clouds', .01, .06), tris=1600)
                 .ell((h*.1, -h*.1, h*.93), (h*.09, h*.07, h*.06), 16).ell((-h*.12, -h*.08, h*.86), (h*.08, h*.06, h*.05), 16))
    eyes = Part('amber eyes', 'amber', 'trunk', 'expressive_detail', voxel=None, smooth=0, tris=300)
    eyes.ell((h*.05, -h*.13, h*.56), (h*.018, h*.01, h*.014), 14).ell((-h*.05, -h*.13, h*.56), (h*.018, h*.01, h*.014), 14)
    parts.append(eyes)
    parts.append(Part('amber heart', 'amber', 'trunk', voxel=None, smooth=0, tris=300).ell((0, -h*.135, h*.4), (h*.028, h*.012, h*.034), 16))
    return parts, zones


def ignis(item):
    h = item['height']
    # Emission kept near 1.5-2.6 so Khronos PBR Neutral keeps the fire hue instead of clipping to white.
    zones = palette(item, {'armor': ((.09, .07, .07), .55, .7), 'core': ((.85, .22, .03), .4, 0, (1.0, .28, .02), .9),
        'seam': ((1.0, .45, .08), .35, 0, (1.0, .4, .06), 1.2), 'flame': ((1.0, .42, .06), .4, 0, (1.0, .38, .04), 1.4),
        'ember': ((.55, .12, .04), .6, 0, (.7, .14, .02), 1.2)})
    parts = []
    core = Part('molten core', 'core', 'root', voxel=.012, detail=('clouds', .01, .05), tris=2400)
    core.ell((0, 0, h*.64), (h*.12, h*.08, h*.15), 28).ell((0, 0, h*.5), (h*.09, h*.065, h*.07), 20)
    parts.append(core)
    plates = Part('forged armour', 'armor', 'root', voxel=.01, detail=('cells', .006, .06), tris=3400)
    plates.ell((0, -h*.012, h*.7), (h*.128, h*.075, h*.09), 28).ell((h*.155, 0, h*.76), (h*.06, h*.06, h*.05), 18)
    plates.ell((-h*.155, 0, h*.76), (h*.06, h*.06, h*.05), 18).cap((0, 0, h*.52), (0, 0, h*.45), h*.1, h*.095, 24)
    parts.append(plates)
    head = Part('helm', 'armor', 'head', voxel=.01, detail=('cells', .005, .05), tris=1800)
    head.ell((0, 0, h*.88), (h*.06, h*.066, h*.072), 26).cap((0, 0, h*.8), (0, 0, h*.84), h*.03)
    parts.append(head)
    parts.append(Part('eye slit', 'seam', 'head', 'expressive_detail', voxel=None, smooth=0, tris=200)
                 .cap((-h*.03, -h*.062, h*.89), (h*.03, -h*.062, h*.89), h*.006))
    seams = Part('luminous seams', 'seam', 'root', voxel=None, smooth=0, tris=600)
    for a, b in [((-.07, -.085, .74), (.07, -.085, .74)), ((0, -.088, .78), (0, -.08, .56)), ((-.09, -.07, .6), (.09, -.07, .6))]:
        seams.cap(Vector(a)*h, Vector(b)*h, h*.005)
    parts.append(seams)
    flames = Part('flame plumes', 'flame', 'head', 'flame', voxel=.008, smooth=3, tris=2400)
    for x, y, top in ((0, .01, 1.06), (.04, .02, 1.0), (-.04, .02, 1.01), (.0, .05, .98)):
        flames.tube([(x*h, y*h, h*.93), (x*1.4*h, y*h + h*.02, h*(top-.06)), (x*.6*h, y*h + h*.03, h*top)], [h*.03, h*.018, h*.002])
    parts.append(flames)
    for s, side in ((1, 'l'), (-1, 'r')):
        arm = Part(f'gauntlet {side}', 'armor', f'arm_{side}', voxel=.009, detail=('cells', .005, .05), tris=1400)
        arm.tube([(s*h*.16, 0, h*.74), (s*h*.19, 0, h*.6), (s*h*.2, -h*.01, h*.46)], [h*.036, h*.033, h*.03])
        arm.ell((s*h*.205, -h*.012, h*.43), (h*.026, h*.022, h*.036), 14)
        parts.append(arm)
        parts.append(Part(f'hand flame {side}', 'flame', f'arm_{side}', 'flame', voxel=.006, smooth=2, tris=500)
                     .tube([(s*h*.205, -h*.015, h*.41), (s*h*.21, -h*.02, h*.36)], [h*.018, h*.002]))
        leg = Part(f'greave {side}', 'armor', f'leg_{side}', voxel=.01, detail=('cells', .005, .05), tris=1500)
        leg.tube([(s*h*.06, 0, h*.47), (s*h*.064, 0, h*.27), (s*h*.066, 0, h*.08)], [h*.05, h*.042, h*.036])
        leg.ell((s*h*.066, -h*.035, h*.03), (h*.037, h*.072, h*.028), 18)
        parts.append(leg)
        parts.append(Part(f'knee ember {side}', 'ember', f'leg_{side}', voxel=None, smooth=0, tris=200)
                     .ell((s*h*.065, -h*.04, h*.28), (h*.02, h*.008, h*.02), 12))
    return parts, zones


def melody(item):
    h = item['height']
    zones = palette(item, {'petal': ((.98, .78, .25), .55, 0, (.5, .3, .05), .6), 'leaf': ((.25, .58, .2), .6),
        'face': ((.48, .72, .32), .55), 'bio': ((.6, 1.0, .75), .3, 0, (.45, 1.0, .7), 3.0),
        'sclera': ((.95, .97, .9), .3), 'iris': ((.15, .35, .2), .25), 'pupil': ((.02, .03, .02), .3)})
    parts = []
    head = Part('flower face', 'face', None, voxel=.02, smooth=4, tris=1800)
    head.ell((0, 0, h*.62), (h*.2, h*.13, h*.2), 28)
    parts.append(head)
    face(parts, h*2.4, (0, -h*.09, h*.64), (h*.09, h*.05, h*.08), 'iris', joint=None, mouth=False)
    petals = Part('petals', 'petal', None, 'petal', voxel=.018, smooth=3, tris=3200)
    for i in range(8):
        a = i*math.tau/8
        petals.ell((math.cos(a)*h*.27, h*.03, h*.62 + math.sin(a)*h*.27), (h*.12 if i % 2 else h*.11, h*.03, h*.07), 16)
    parts.append(petals)
    wings = Part('leaf wings', 'leaf', None, 'petal', voxel=.016, smooth=3, tris=1800)
    for s in (1, -1):
        wings.ell((s*h*.42, h*.1, h*.5), (h*.2, h*.025, h*.09), 18).ell((s*h*.36, h*.1, h*.36), (h*.14, h*.022, h*.06), 16)
    parts.append(wings)
    stem = Part('stem body', 'leaf', None, voxel=.016, tris=900)
    stem.tube([(0, h*.02, h*.42), (h*.02, h*.03, h*.24), (0, h*.02, h*.1)], [h*.05, h*.035, h*.015])
    parts.append(stem)
    bio = Part('bioluminescent pattern', 'bio', None, 'expressive_detail', voxel=None, smooth=0, tris=600)
    for i in range(8):
        a = i*math.tau/8 + math.tau/16
        bio.ell((math.cos(a)*h*.2, -h*.0, h*.62 + math.sin(a)*h*.2), (h*.018, h*.008, h*.018), 10)
    parts.append(bio)
    return parts, zones


FOUNDERS = {'elara': ('humanoid', 'humanoid_basic', elara), 'auren': ('humanoid', 'humanoid_basic', auren),
            'kai': ('synthetic_humanoid', 'synthetic_basic', kai), 'lumi': ('floating_spirit', None, lumi),
            'terra': ('nature_elemental', 'tree_basic', terra), 'ignis': ('fire_elemental', 'fire_basic', ignis),
            'melody': ('botanical_sprite', None, melody)}


def founder(scene, item):
    archetype, template, build = FOUNDERS[item['founder']]
    parts, zones = build(item)
    for p in parts:
        if p.role not in ROLES:
            raise CreationError('Unknown runtime role')
        if archetype in ('floating_spirit', 'botanical_sprite') and (p.joint or any(w in p.name for w in ('leg', 'foot', 'walk'))):
            raise CreationError('Spirit templates have no joints or legs')
    block = assemble(scene, item['name'], parts, zones, item['height'], item.get('location', (0, 0, 0)),
                     item.get('seed', 0))
    block['finalverse.founder'] = item['founder']; block['finalverse.archetype'] = archetype
    return block, template
