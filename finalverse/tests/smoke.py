# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run with a real engine. Receipt records its actual version and executable."""
import bpy
import json
import math
from pathlib import Path
import sys
import time
from mathutils import Vector

args = sys.argv[sys.argv.index('--')+1:]
root = Path(args[0]);root.mkdir(parents=True, exist_ok=False)
source = Path(args[1])
start = time.monotonic()
try:
    from bl_ui import finalverse_studio as studio
except ImportError:
    # Optional compatibility probe; never counted as a source-fork build test.
    import importlib.util
    spec = importlib.util.spec_from_file_location('finalverse_studio_probe', source/'scripts/startup/bl_ui/finalverse_studio.py')
    studio = importlib.util.module_from_spec(spec);spec.loader.exec_module(studio)
    for cls in studio.classes:bpy.utils.register_class(cls)
    studio.register_workspace()

native_registration = studio.__name__ == "bl_ui.finalverse_studio"
bpy.ops.wm.read_factory_settings(use_empty=True)
if not native_registration:
    studio._load_workspace(None)
assert bpy.data.workspaces.get(studio.WORKSPACE)
bpy.ops.mesh.primitive_cube_add(size=2, location=(0,0,1.2))
obj=bpy.context.object;obj.name='Studio authoring sample'
bevel=obj.modifiers.new('Editable bevel','BEVEL');bevel.width=.14;bevel.segments=3
bpy.ops.object.modifier_apply(modifier=bevel.name)
assert len(obj.data.vertices)>8
mat=bpy.data.materials.new('Studio teal');mat.diffuse_color=(.04,.52,.55,1)
mat.use_nodes=True
mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.04,.52,.55,1)
mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.35
obj.data.materials.append(mat)
bpy.ops.object.camera_add(location=(4,-6,4))
cam=bpy.context.object;cam.rotation_euler=(Vector((0,0,1.0))-cam.location).to_track_quat('-Z','Y').to_euler()
bpy.context.view_layer.update()
matrix = cam.matrix_world.copy();cam.parent=obj;cam.matrix_world=matrix
scene=bpy.context.scene;scene.camera=cam
bpy.ops.object.light_add(type='AREA',location=(1,-3,6));bpy.context.object.data.energy=700
scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=480;scene.render.resolution_y=360;scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('Studio world');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.04,.05,.08,1)
assert bpy.ops.finalverse.inspect_scene()=={'FINISHED'}
identity=obj['finalverse.object_id']
index=studio.inspect_scene(scene)
assert next(v for v in index['objects'] if v['name']==cam.name)['parent']==identity
scene.render.filepath=str(root/'preview.png');bpy.ops.render.render(write_still=True)
preview=bpy.data.images.load(str(root/'preview.png'),check_existing=False)
pixels=list(preview.pixels)
visible=sum(1 for i in range(0,len(pixels),4) if pixels[i+1]>pixels[i]*1.35 and pixels[i+1]-pixels[i]>.08)
assert visible>1000, f'Render did not show the teal subject: {visible} pixels'
project=root/'roundtrip.blend';bpy.ops.wm.save_as_mainfile(filepath=str(project))
bpy.ops.wm.open_mainfile(filepath=str(project))
assert bpy.data.objects['Studio authoring sample']['finalverse.object_id']==identity
result=studio.export_candidate(root/'sample.fvasset',bpy.context.scene)
assert not result['published'] and len(result['scene']['objects'])==3
assert bpy.data.filepath==str(project)
try:studio.export_candidate(root/'sample.fvasset',bpy.context.scene)
except FileExistsError:pass
else:raise AssertionError('Existing candidate directory was overwritten')
record={'schema_version':'finalverse.studio-smoke/v1','engine_executable':bpy.app.binary_path,
        'upstream_version':bpy.app.version_string,'built_in_startup_module':native_registration,'product':studio.PRODUCT,'workspace':studio.WORKSPACE,
        'checks':{'python_api':True,'workspace':True,'mesh_edit':True,'render':True,'save_reopen_identity':True,
                  'glb_export':True,'source_export':True,'refuse_overwrite':True},
        'visible_subject_pixels':visible,'duration_ms':(time.monotonic()-start)*1000,'candidate':str(root/'sample.fvasset')}
(root/'smoke.json').write_text(json.dumps(record,indent=2))
print('FINALVERSE_SMOKE',json.dumps(record))
