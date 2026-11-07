"""CF1 Elara: runtime exports.

  elara_cf1.glb          hero/authoring profile: full meshes, 163-bone skin, 3 clips,
                         BaseColor/Normal/ORM textures (JPEG in GLB)
  elara_cf1_runtime.glb  runtime candidate: decimated to the M1 budget (<= 40k tris),
                         textures capped at 1024, same skeleton and clips
  elara_cf1_proxy.glb    static single-node/single-mesh, factor-only PBR (<= 8 materials):
                         the subset Genesis import (ec::geometry::validate_glb) accepts today

usage: python elara_export.py SRC.blend OUTDIR
"""
import json
import os
import sys

import bpy
import numpy as np

src, outdir = sys.argv[sys.argv.index('--') + 1:][:2]
os.makedirs(outdir, exist_ok=True)


def open_src():
    bpy.ops.wm.open_mainfile(filepath=src)
    rig = bpy.data.objects['Elara_Rig']
    rig.animation_data.action = None
    for t in rig.animation_data.nla_tracks:
        t.mute = False
    sc = bpy.context.scene
    sc.render.fps = 30; sc.render.fps_base = 1.0   # clips are authored at 30 fps
    sc.frame_set(0)
    return rig


# texture caps per profile (GPU memory budget, RGBA8 + mips): hero <= 160 MiB, runtime <= 48 MiB
HERO_2K = {'T_Elara_Skin_BaseColor', 'T_Elara_Skin_Normal', 'T_Elara_Tunic_BaseColor', 'T_Elara_Cloak_BaseColor'}
SMALL = {'T_Hair_ORM', 'T_Leather_ORM', 'T_Elara_Eye.L_BaseColor', 'T_Elara_Eye.R_BaseColor'}


def cap_textures(profile):
    for img in bpy.data.images:
        if img.size[0] == 0:
            continue
        if profile == 'hero':
            cap = 2048 if img.name in HERO_2K else (512 if img.name in SMALL else 1024)
        else:
            cap = 1024 if img.name in HERO_2K else (256 if img.name in SMALL else 512)
        if img.size[0] > cap:
            img.scale(cap, cap)


def tris(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    m = ob.evaluated_get(dg).to_mesh()
    m.calc_loop_triangles(); n = len(m.loop_triangles)
    ob.evaluated_get(dg).to_mesh_clear()
    return n


def export(path, **kw):
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', export_yup=True, export_apply=True,
                              export_skins=True, export_animations=True, export_animation_mode='NLA_TRACKS',
                              export_force_sampling=True, export_frame_range=False, export_def_bones=False,
                              export_image_format='JPEG', export_jpeg_quality=90, export_texcoords=True,
                              export_normals=True, export_tangents=False, export_materials='EXPORT',
                              export_extras=True, use_selection=False, **kw)


def meshes():
    return [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name.startswith('Elara_')]


report = {}
# --- hero ---------------------------------------------------------------------
rig = open_src()
cap_textures('hero')
report['hero_tris_evaluated'] = sum(tris(o) for o in meshes())
export(os.path.join(outdir, 'elara_cf1.glb'))

# --- runtime candidate --------------------------------------------------------
rig = open_src()
target = 38000
dec = [o for o in meshes() if tris(o) >= 300]
fixed = sum(tris(o) for o in meshes() if o not in dec)
base = {o.name: tris(o) for o in dec}
ratio = min(1.0, (target - fixed) / sum(base.values()))
for o in dec:
    # keep faces (body/eyes/lashes) denser than the cloth and hair
    r = ratio * (1.35 if o.name in ('Elara_Body',) else 1.0)
    if o.name.startswith(('Elara_Eye', 'Elara_Lashes')):
        r = 0.5
    d = o.modifiers.new('lod', 'DECIMATE'); d.ratio = min(1.0, r)
    # decimate must run before solidify/armature: move it to the top
    with bpy.context.temp_override(object=o, active_object=o):
        bpy.ops.object.modifier_move_to_index(modifier='lod', index=0)
# decimate is not linear (solidify, small parts): converge on the target
for _ in range(4):
    total = sum(tris(o) for o in meshes())
    if total <= target:
        break
    k = (target - fixed) / max(1, total - fixed)
    for o in dec:
        o.modifiers['lod'].ratio = max(0.05, o.modifiers['lod'].ratio * k * 0.98)
cap_textures('runtime')
report['runtime_tris_evaluated'] = sum(tris(o) for o in meshes())
export(os.path.join(outdir, 'elara_cf1_runtime.glb'))

# --- static proxy (Genesis import subset) -------------------------------------
rig = open_src()
for t in rig.animation_data.nla_tracks:
    t.mute = True
for pb in rig.pose.bones:   # rest pose: muted tracks leave the last evaluated pose behind
    pb.location = (0, 0, 0); pb.rotation_quaternion = (1, 0, 0, 0); pb.rotation_euler = (0, 0, 0); pb.scale = (1, 1, 1)
bpy.context.scene.frame_set(0)
dg = bpy.context.evaluated_depsgraph_get()
parts = []
zone_of = {}
ZONES = {'skin': ('Skin',), 'hair': ('Hair', 'Lashes', 'Eye'), 'tunic': ('Tunic',), 'cloak': ('Cloak',),
         'leather': ('Leather', 'Leggings'), 'metal': ('Brass', 'Trim'), 'wood': ('Wood', 'Flower')}


def avg_color(mat):
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image and n.image.colorspace_settings.name == 'sRGB':
            a = np.zeros(n.image.size[0] * n.image.size[1] * 4, np.float32); n.image.pixels.foreach_get(a)
            a = a.reshape(-1, 4)[::97, :3]
            return tuple(float(x) for x in np.median(a, 0))
    b = mat.node_tree.nodes.get('Principled BSDF')
    return tuple(b.inputs['Base Color'].default_value[:3]) if b else (.5, .5, .5)


import bmesh
bm = bmesh.new()
mats = {}
for o in meshes():
    m = bpy.data.meshes.new_from_object(o.evaluated_get(dg), depsgraph=dg)
    m.transform(o.matrix_world)
    remap = []
    for slot in m.materials:
        name = slot.name if slot else 'Skin'
        z = next((k for k, keys in ZONES.items() if any(x in name for x in keys)), 'skin')
        if z not in mats:
            mats[z] = avg_color(slot) if slot else (.8, .6, .5)
        remap.append(list(mats).index(z))
    for p in m.polygons:
        p.material_index = remap[p.material_index] if remap else 0
    bm.from_mesh(m)
    bpy.data.meshes.remove(m)
pm = bpy.data.meshes.new('Elara_Proxy'); bm.to_mesh(pm); bm.free()
for z, c in mats.items():
    mm = bpy.data.materials.new(f'proxy_{z}'); mm.use_nodes = True
    b = mm.node_tree.nodes['Principled BSDF']; b.inputs['Base Color'].default_value = (*c, 1)
    b.inputs['Roughness'].default_value = 0.35 if z == 'metal' else 0.75
    b.inputs['Metallic'].default_value = 0.9 if z == 'metal' else 0.0
    pm.materials.append(mm)
for o in list(bpy.context.scene.objects):
    bpy.data.objects.remove(o)
po = bpy.data.objects.new('Elara_Proxy', pm); bpy.context.scene.collection.objects.link(po)
d = po.modifiers.new('lod', 'DECIMATE'); d.ratio = min(1.0, 20000 / max(1, len(pm.polygons) * 2))
with bpy.context.temp_override(object=po, active_object=po):
    bpy.ops.object.modifier_apply(modifier='lod')
pm.uv_layers.clear() if hasattr(pm.uv_layers, 'clear') else None
while pm.uv_layers:
    pm.uv_layers.remove(pm.uv_layers[0])
report['proxy_tris'] = sum(len(p.vertices) - 2 for p in pm.polygons)
report['proxy_materials'] = len(pm.materials)
bpy.ops.export_scene.gltf(filepath=os.path.join(outdir, 'elara_cf1_proxy.glb'), export_format='GLB', export_yup=True,
                          export_apply=True, export_skins=False, export_animations=False, export_texcoords=False,
                          export_materials='EXPORT')
json.dump(report, open(os.path.join(outdir, 'export-report.json'), 'w'), indent=2)
print('EXPORT', json.dumps(report))
