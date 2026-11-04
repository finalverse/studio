# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Real native S1 acceptance harness; never loaded as a model tool."""
import json
from pathlib import Path
import statistics
import sys
import time
import uuid

import bpy
from finalverse_creation import engine
from finalverse_creation.host import Host
from finalverse_creation.protocol import canonical

args = sys.argv[sys.argv.index('--')+1:]
work = Path(args[0]).resolve(); work.mkdir(parents=True, exist_ok=True)
mode = args[1]
if mode == 'snapshot':
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    index = engine.snapshot(bpy.context.scene)
    (work/'snapshot.json').write_text(canonical(index))
    bpy.ops.wm.save_as_mainfile(filepath=str(work/'seed.blend'))
elif mode == 'execute':
    response = json.loads(Path(args[2]).read_text())
    host = Host(work/'workspace')
    index = host.refresh()
    job = host.store.submit(response['plan'], index['scene_id'], index['revision'], str(uuid.uuid4()),
                            source='model', model_receipt=response['receipt'])
    host.approve(job['id'])
    started = time.monotonic(); ticks = []
    while time.monotonic()-started < 180:
        before = time.monotonic(); host.tick(); ticks.append(time.monotonic()-before)
        job = host.store.get(job['id'])
        if job['state'] in {'Completed', 'Failed', 'Cancelled', 'Interrupted'}: break
        time.sleep(.02)
    result = {'job': job, 'wall_seconds': time.monotonic()-started,
              'tick_max_seconds': max(ticks), 'tick_median_seconds': statistics.median(ticks),
              'scene': host.refresh()}
    directory = host.store.directory(job['id'])
    host.close()
    if job['state'] == 'Completed':
        saves = [o for o in job['plan']['operations'] if o['op'] == 'scene.save']
        if saves:
            before = engine.snapshot(bpy.context.scene)
            bpy.ops.wm.open_mainfile(filepath=str(directory/saves[-1]['path']), load_ui=False, use_scripts=False)
            after = engine.snapshot(bpy.context.scene)
            result['reopened'] = after
            result['identity_animation_geometry_persisted'] = before['objects'] == after['objects']
    (work/'native-result.json').write_text(canonical(result))
    if job['state'] != 'Completed': raise RuntimeError(job.get('error') or job['state'])
    assert result.get('identity_animation_geometry_persisted'), 'Reopen did not preserve the scene'
else:
    raise ValueError('Unknown harness mode')
