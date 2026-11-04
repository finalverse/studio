# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fixed headless render entry, never a model-generated script."""
import json
from pathlib import Path
import sys
import socket

import bpy
from finalverse_creation.protocol import check, OPERATIONS, parse

directory = Path(sys.argv[sys.argv.index('--')+1]).resolve()

# Fail closed if the launch profile is missing. These fixed, harmless probes
# inspect only our own workspace marker and never transmit application data.
marker = Path(bpy.data.filepath).parents[2]/'studio-workspace.json'
try:
    with marker.open('rb') as f: f.read(1)
except PermissionError: pass
else: raise RuntimeError('Sandbox allowed an out-of-profile read')
outside = Path(bpy.data.filepath).parent/'sandbox-probe-must-not-exist'
try:
    with outside.open('x'): pass
except PermissionError: pass
else:
    outside.unlink()
    raise RuntimeError('Sandbox allowed an out-of-profile write')
with socket.socket() as network:
    network.settimeout(1)
    try: network.connect(('127.0.0.1', 11434))
    except PermissionError: pass
    else: raise RuntimeError('Sandbox did not refuse a network connection')
item = parse((directory/'render-request.json').read_text())
check(item, OPERATIONS['scene.render'])
scene = bpy.context.scene
if not scene.camera:
    raise ValueError('A scene camera is required')
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = item['width']; scene.render.resolution_y = item['height']
scene.render.resolution_percentage = 100
scene.eevee.taa_render_samples = item['samples']
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = str(directory/item['path'])
bpy.ops.render.render(write_still=True)
(directory/'render-result.json').write_text(json.dumps({'path': item['path'], 'bytes': (directory/item['path']).stat().st_size,
    'isolation_checks': {'outside_read_denied': True, 'outside_write_denied': True, 'network_denied': True}}))
