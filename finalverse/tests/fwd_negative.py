# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Studio integration refusal tests; no mesh mutation or render required."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import uuid
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts/modules'))
from finalverse_fwd.exchange import roundtrip

source, cas, validator, destination = sys.argv[sys.argv.index('--')+1:]
source, cas, destination = Path(source), Path(cas), Path(destination)
destination.mkdir(exist_ok=False)
original = source.read_bytes()
doc = json.loads(original)
original_hashes = {a['sha256']: hashlib.sha256((cas/a['sha256']).read_bytes()).hexdigest() for a in doc['assets']}
previous_scene = bpy.context.window.scene
cases = []


def refused(name, definition=source, objects=cas, expected=ValueError, **kwargs):
    out = destination/name
    try:
        roundtrip(definition, objects, out, validator, render=False, **kwargs)
    except expected as error:
        cases.append({'case': name, 'refused': True, 'reason': str(error)})
    else:
        raise AssertionError('Expected refusal for '+name)
    assert not out.exists()
    assert bpy.context.window.scene == previous_scene


bad = copy.deepcopy(doc)
bad['arbitrary_code'] = 'should never execute'
path = destination/'unknown-field.fwd.json'
path.write_text(json.dumps(bad))
refused('unknown-schema-field', definition=path)
objects = destination/'corrupt-objects'
objects.mkdir()
for asset in doc['assets']:
    raw = (cas/asset['sha256']).read_bytes()
    (objects/asset['sha256']).write_bytes(raw[:-1]+bytes([raw[-1]^1]))
refused('corrupt-content-hash', objects=objects)
bad = copy.deepcopy(doc)
bad['simulation_bindings'] = [{'asset_id': bad['assets'][0]['id'], 'world_id': bad['world']['id'],
                              'entity_id': str(uuid.UUID(int=123)), 'authority': 'mutsea', 'state': 'reference_only'}]
path = destination/'binding-reference-only.fwd.json'
path.write_text(json.dumps(bad))
refused('cannot-rebind-simulation', definition=path)
refused('sample-budget', samples=65)
refused('pixel-budget', size=4096)
existing = destination/'existing-output'
existing.mkdir()
(existing/'untouched').write_bytes(b'keep')
try:
    roundtrip(source, cas, existing, validator, render=False)
except FileExistsError:
    cases.append({'case': 'existing-output-preserved', 'refused': True})
else:
    raise AssertionError('Existing directory was overwritten')
assert (existing/'untouched').read_bytes() == b'keep'
assert source.read_bytes() == original
for asset in doc['assets']:
    assert hashlib.sha256((cas/asset['sha256']).read_bytes()).hexdigest() == original_hashes[asset['sha256']]
result = {'schema': 'finalverse.studio-fwd-negative/0.1', 'cases': cases,
          'source_unchanged': True, 'prior_scene_unchanged': True, 'world_mutations': 0}
(destination/'result.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
print('FINALVERSE_FWD_REFUSALS '+json.dumps(result, sort_keys=True))
