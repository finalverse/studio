"""Character Foundry presentation renders (Cycles CPU, deterministic).

Two lighting rigs:
  neutral    - soft grey studio, Khronos PBR Neutral view transform (matches
               Infinity's tone mapper, so colour reads the way the runtime will)
  production - dusk key/rim rig after the canonical vision art, AgX
"""
import math

import bpy
from mathutils import Vector

VIEWS = {  # yaw (deg, 0 = camera on -Y looking +Y at the character's front)
    'front': 0, 'three_quarter': 35, 'side': 90, 'rear': 180, 'three_quarter_rear': 215,
}


def _world(scene, color, strength):
    w = bpy.data.worlds.new('cf-world'); w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs[0].default_value = (*color, 1); bg.inputs[1].default_value = strength
    scene.world = w


def _area(scene, name, loc, target, energy, size, color=(1, 1, 1), shape='DISK'):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = energy; ld.size = size
    ld.color = color; ld.shape = shape
    ob = bpy.data.objects.new(name, ld); scene.collection.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    ob['cf.light'] = True
    return ob


def clear_lights(scene):
    for ob in list(scene.objects):
        if ob.get('cf.light') or ob.get('cf.backdrop'):
            bpy.data.objects.remove(ob)


def backdrop(scene, color, rough=0.9):
    me = bpy.data.meshes.new('cf-backdrop')
    import bmesh
    bm = bmesh.new()
    # cyclorama: floor + curved wall behind the character (+Y)
    n = 16; R = 1.5; W = 8
    rows = []
    for i in range(n + 1):
        a = (i / n) * math.pi / 2
        y = 2.5 + R * math.sin(a); z = R - R * math.cos(a)
        rows.append((y, z))
    rows = [(-6, 0)] + rows + [(2.5 + R, 8)]
    vs = [[bm.verts.new((x, y, z)) for x in (-W, W)] for y, z in rows]
    for a, b in zip(vs, vs[1:]):
        bm.faces.new((a[0], a[1], b[1], b[0]))
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.new('cf-backdrop'); mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1); bsdf.inputs['Roughness'].default_value = rough
    me.materials.append(mat)
    ob = bpy.data.objects.new('cf-backdrop', me); scene.collection.objects.link(ob)
    ob['cf.backdrop'] = True
    return ob


def rig_neutral(scene, center_z=0.9):
    clear_lights(scene)
    _world(scene, (0.5, 0.5, 0.5), 0.35)
    backdrop(scene, (0.18, 0.18, 0.18))
    _area(scene, 'key', (-2.2, -3.0, 3.0), (0, 0, center_z), 220, 2.5)
    _area(scene, 'fill', (2.8, -2.4, 1.6), (0, 0, center_z), 80, 3.0)
    _area(scene, 'rim', (1.2, 2.8, 2.8), (0, 0, center_z + .3), 160, 1.5)
    _area(scene, 'rim2', (-1.8, 2.4, 2.2), (0, 0, center_z + .3), 90, 1.5)
    scene.view_settings.view_transform = 'Khronos PBR Neutral'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0.0


def rig_production(scene, center_z=0.9):
    clear_lights(scene)
    _world(scene, (0.035, 0.05, 0.11), 1.0)
    backdrop(scene, (0.03, 0.045, 0.07), rough=1.0)
    _area(scene, 'key', (-2.4, -2.6, 3.2), (0, 0, center_z + .2), 1100, 1.8, (1.0, 0.86, 0.68))
    _area(scene, 'fill', (2.6, -2.8, 1.2), (0, 0, center_z), 160, 3.5, (0.55, 0.68, 1.0))
    _area(scene, 'rimL', (-2.0, 2.6, 2.6), (0, 0, center_z + .4), 900, 1.2, (0.45, 0.75, 1.0))
    _area(scene, 'rimR', (2.2, 2.2, 2.4), (0, 0, center_z + .4), 700, 1.2, (0.55, 1.0, 0.75))
    _area(scene, 'bounce', (0, -1.5, 0.05), (0, 0, center_z), 60, 3.0, (1.0, 0.7, 0.4))
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = 0.0


def setup(scene, res=(1024, 1536), samples=96):
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.seed = 7
    scene.cycles.max_bounces = 8
    scene.cycles.transparent_max_bounces = 16
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    scene.render.threads_mode = 'FIXED'; scene.render.threads = 4


def camera(scene, yaw_deg, target, distance, lens=85, height=None, pitch_target=None):
    cam = scene.camera
    if cam is None:
        cd = bpy.data.cameras.new('cf-cam'); cam = bpy.data.objects.new('cf-cam', cd)
        scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = lens
    cam.data.clip_start = 0.05
    a = math.radians(yaw_deg)
    t = Vector(target)
    h = t.z if height is None else height
    cam.location = (t.x + distance * math.sin(a), t.y - distance * math.cos(a), h)
    d = t - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    for ob in scene.objects:
        if ob.get('cf.backdrop'):
            ob.rotation_euler = (0, 0, a)
    for ob in scene.objects:
        if ob.get('cf.light'):
            if 'cf.base' not in ob:
                ob['cf.base'] = list(ob.location) + list(ob.rotation_euler)
            bx, by, bz, rx, ry, rz = ob['cf.base']
            ca, sa = math.cos(a), math.sin(a)
            ob.location = (bx * ca - by * sa, bx * sa + by * ca, bz)
            ob.rotation_euler = (rx, ry, rz + a)
    return cam


def render(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path
