# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fixed trusted Cycles worker. Input is verified GLB/FWD, never a Python plan/.blend."""
import json
from pathlib import Path
import sys
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from finalverse_fwd.exchange import _read, _render, native_validate
from finalverse_fwd.glb import MAX_BYTES, parse

definition, cas, validator, output, samples, size = sys.argv[sys.argv.index('--')+1:]
receipt = native_validate(validator, definition, cas)
doc = json.loads(_read(definition, 2*1024*1024))
# Candidate may contain multiple assets, but this offline preview selects the newly
# generated Studio asset; it does not assemble or publish the other world assets.
assets = [a for a in doc['assets'] if any(s.startswith('studio-input-') for s in a['source_ids'])]
if len(assets) != 1:
    raise ValueError('Exactly one Studio candidate asset is required for the Cycles preview')
asset = assets[0]
path = Path(cas)/asset['sha256']
parse(_read(path, MAX_BYTES))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(path))
objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
if not objects:
    raise ValueError('Cycles candidate contains no mesh')
result = _render(bpy.context.scene, objects, Path(output), int(samples), int(size))
Path(output+'.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
print('FINALVERSE_CYCLES_RECEIPT '+json.dumps(result, sort_keys=True))
