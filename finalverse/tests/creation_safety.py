# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native failure/recovery acceptance, separate from model-generated examples."""
import json
from pathlib import Path
import sys
import time
import uuid

import bpy
from finalverse_creation import engine
from finalverse_creation.host import Host
from finalverse_creation.protocol import CreationError

root = Path(sys.argv[sys.argv.index('--')+1]).resolve(); root.mkdir(parents=True, exist_ok=False)
results = {}


def fresh(name):
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    return Host(root/name)


def submit(host):
    index = host.refresh()
    plan = {'schema_version': 'finalverse.creation/v1', 'summary': 'Native safety fixture', 'operations': [
        {'op': 'object.create', 'ref': '@cube', 'primitive': 'cube', 'name': 'Safety cube'},
        {'op': 'object.transform', 'target': '@cube', 'location': [1, 2, 3]}]}
    return host.store.submit(plan, index['scene_id'], index['revision'], str(uuid.uuid4()), source='test-fixture')


host = fresh('cancel'); job = submit(host)
host.approve(job['id']); host.tick(); host.tick()
assert len(bpy.context.scene.objects) == 1
host.cancel(job['id'])
for _ in range(3): host.tick()
assert host.store.get(job['id'])['state'] == 'Cancelled'
assert list(bpy.context.scene.objects[0].location) == [0, 0, 0]
results['cancel_stops_remaining_steps'] = True; host.close()

host = fresh('restart'); job = submit(host)
host.approve(job['id']); host.tick(); host.tick()
object_id = bpy.context.scene.objects[0][engine.OBJECT_ID]
# Simulate abrupt loss without clean cancellation. Never exercise product replay.
host.authority.close(); host.store.db.close()
host = Host(root/'restart')
assert host.store.get(job['id'])['state'] == 'Interrupted'
for _ in range(3): host.tick()
assert len(bpy.context.scene.objects) == 1
assert host.store.get(job['id'])['step'] == 1
checkpoint = host.store.directory(job['id'])/'checkpoint-001.blend'
host.close()
bpy.ops.wm.open_mainfile(filepath=str(checkpoint), load_ui=False, use_scripts=False)
assert bpy.context.scene.objects[0][engine.OBJECT_ID] == object_id
assert list(bpy.context.scene.objects[0].location) == [0, 0, 0]
results['restart_interrupted_no_duplicate_and_checkpoint_reopened'] = True

host = fresh('concurrent'); job = submit(host); host.approve(job['id']); host.tick(); host.tick()
bpy.context.scene.objects[0].location.x = 7
host.tick()
assert host.store.get(job['id'])['state'] == 'Failed'
assert bpy.context.scene.objects[0].location.x == 7
results['concurrent_edit_aborts_remaining_steps'] = True; host.close()

host = fresh('stale'); job = submit(host)
bpy.context.scene.frame_set(2)
try: host.approve(job['id']); raise AssertionError('Stale approval accepted')
except CreationError: pass
assert host.store.get(job['id'])['state'] == 'Proposed'
results['stale_approval_refused'] = True

host.infer('local', 'models'); child = host.inference['process']; ticks = []
for _ in range(5):
    before = time.monotonic(); host.tick(); ticks.append(time.monotonic()-before)
host.cancel()
assert child.poll() is not None and host.inference is None
results['provider_child_cancelled'] = True
results['pending_provider_tick_max_seconds'] = max(ticks)
host.close()
(root/'result.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
