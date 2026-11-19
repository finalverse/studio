# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run in Studio to prove supported UI registration and restored scene context."""
import json
from pathlib import Path
import sys
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts/modules'))
import finalverse_fwd
from finalverse_fwd.glb import compare, parse
from finalverse_fwd.exchange import roundtrip

args = sys.argv[sys.argv.index('--')+1:]
source, cas, out, validator = args[:4]
palette = args[4] if len(args) > 4 else 'urban_clay'
old = bpy.context.window.scene
old_names = sorted(obj.name for obj in old.objects)
finalverse_fwd.register()
assert hasattr(bpy.types.Scene, 'fv_fwd_definition')
assert hasattr(bpy.types, 'FINALVERSE_PT_fwd')
finalverse_fwd.unregister()
assert not hasattr(bpy.types.Scene, 'fv_fwd_definition')
finalverse_fwd.register()
finalverse_fwd.unregister()
cycles_binary = args[5] if len(args) > 5 else None
result = roundtrip(source, cas, out, validator, palette=palette, cycles_binary=cycles_binary)
assert result['state'] == 'validated-offline-candidate'
assert result['published'] is False and result['world_mutations'] == 0
assert bpy.context.window.scene == old
assert sorted(obj.name for obj in old.objects) == old_names
original = json.loads(Path(source).read_text())
derived = json.loads((Path(out)/'world.fwd.json').read_text())
assert derived['world'] == original['world']
assert derived['frames'] == original['frames']
assert derived['definition_id'] == original['definition_id']
assert derived['version'] == original['version']+1
assert derived['assets'][0]['transform'] == original['assets'][0]['transform']
assert derived['assets'][0]['id'] != original['assets'][0]['id']
assert Path(out, 'cycles-preview.png').stat().st_size > 512
check = {'ui_register_unregister': True, 'existing_scene_unchanged': True,
         'world_identity_preserved': True, 'geographic_frames_preserved': True,
         'asset_transform_preserved': True, 'definition_version_incremented': True,
         'new_asset_identity': True, 'canonical_admission': True,
         'render_engine': result['render']['engine'],
         'geometry': result['roundtrip']}
Path(out, 'native-test.json').write_text(json.dumps(check, sort_keys=True, indent=2)+'\n')
print('FINALVERSE_FWD_NATIVE_TEST '+json.dumps(check, sort_keys=True))
