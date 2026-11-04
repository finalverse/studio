# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Acceptance-only native artist proxy. Approval control is NOT an MCP tool."""
import json
from pathlib import Path
import sys
import time

import bpy
from finalverse_creation.host import Host

root = Path(sys.argv[sys.argv.index('--')+1]).resolve(); root.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
host = Host(root/'workspace')
(root/'ready.json').write_text(json.dumps(host.refresh()))
started = time.monotonic(); approved = []
while time.monotonic()-started < 180 and not (root/'stop').exists():
    artist = root/'artist-approval.json'
    if artist.exists():
        job_id = json.loads(artist.read_text())['job_id']; artist.unlink()
        host.approve(job_id); approved.append(job_id)
    host.tick(); time.sleep(.02)
(root/'artist-receipt.json').write_text(json.dumps({'approved_job_ids': approved, 'authority': 'trusted test artist proxy'}))
host.close()
