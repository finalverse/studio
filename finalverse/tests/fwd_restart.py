# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify only a freshly generated local editable.blend in a separate process.

Never use this helper to open an untrusted downloaded .blend file.
"""
import hashlib
import json
from pathlib import Path
import sys
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts/modules'))
from finalverse_fwd.glb import compare, parse

root = Path(sys.argv[sys.argv.index('--')+1]).resolve()
receipt = json.loads((root/'receipt.json').read_text())
assert receipt['state'] == 'validated-offline-candidate'
scene = bpy.data.scenes.get('Finalverse FWD Geographic Candidate')
assert scene is not None
bpy.context.window.scene = scene
bpy.ops.object.select_all(action='DESELECT')
for obj in scene.objects:
    obj.select_set(obj.type in ('MESH', 'EMPTY'))
path = root/'restart.glb'
if path.exists():
    raise ValueError('Restart output already exists')
bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True, use_active_scene=True,
    export_animations=False, export_skins=False, export_morph=False,
    export_cameras=False, export_lights=False, export_extras=False, export_yup=True,
    export_draco_mesh_compression_enable=False)
before = parse((root/'refined.glb').read_bytes())
after = parse(path.read_bytes())
result = {'schema': 'finalverse.studio-fwd-restart/0.1',
          'editable_project_reopened': True, 'geometry': compare(before, after),
          'export_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
          'material_refinement_retained': all(obj.data.materials[0].name.startswith('Finalverse generated')
                                             for obj in scene.objects if obj.type == 'MESH'),
          'published': False, 'world_mutations': 0}
(root/'restart.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
assert result['material_refinement_retained']
print('FINALVERSE_FWD_RESTART '+json.dumps(result, sort_keys=True))
