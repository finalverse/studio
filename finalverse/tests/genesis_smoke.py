#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run an existing supervised G0 adapter with the actual source-built Studio."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument('app');p.add_argument('core_binary');p.add_argument('core_source');p.add_argument('output')
a=p.parse_args();root=Path(a.output);root.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('backend',Path(__file__).parents[1]/'genesis_backend.py')
backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
d=backend.descriptor(a.app);config=root/'backend.json';config.write_text(json.dumps(d,indent=2))
env=os.environ.copy();env['FINALVERSE_STUDIO_CONFIG']=str(config)
start=time.monotonic()
r=subprocess.run([a.core_binary,'adapter',str(root/'queue'),str(Path(a.core_source)/'examples/genesis/blender-room.json')],env=env,capture_output=True,text=True,timeout=180)
(root/'stdout.log').write_text(r.stdout);(root/'stderr.log').write_text(r.stderr)
if r.returncode:raise RuntimeError('Genesis rejected Studio job: '+r.stderr[-2000:])
job=json.loads(r.stdout);assert job['state']=='AwaitingAuthorization' and job['artifact']
report={'schema_version':'finalverse.studio-genesis-smoke/v1','backend':d,'job_id':job['id'],
        'gwir':job['artifact'],'state':job['state'],'attempts':job['attempts'],
        'duration_ms':(time.monotonic()-start)*1000,'published':False,'world_effects':0}
# Invalid host approval must fail before claiming a lease or launching a worker.
wrong=dict(d);wrong['executable_sha256']='0'*64
bad=root/'wrong-backend.json';bad.write_text(json.dumps(wrong))
env['FINALVERSE_STUDIO_CONFIG']=str(bad)
negative=subprocess.run([a.core_binary,'adapter',str(root/'refused-queue'),str(Path(a.core_source)/'examples/genesis/blender-room.json')],env=env,capture_output=True,text=True,timeout=30)
assert negative.returncode!=0 and 'pin mismatch' in negative.stderr
import sqlite3
with sqlite3.connect(root/'refused-queue/jobs.sqlite') as db:
    state=json.loads(db.execute('SELECT document FROM jobs').fetchone()[0])
assert state['state']=='Queued' and state['attempts']==0
report['wrong_pin_refused_before_worker']=True
(root/'refused-stderr.log').write_text(negative.stderr)
(root/'receipt.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
