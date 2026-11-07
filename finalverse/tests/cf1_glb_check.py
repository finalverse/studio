"""CF1: the committed Elara runtime and proxy GLBs pass glb_validate (stdlib + numpy, no Blender)."""
import json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V = os.path.join(ROOT, 'finalverse', 'character_foundry', 'glb_validate.py')
EV = os.path.join(ROOT, 'docs', 'studio', 'evidence', 'cf1')
ok = True
for name, profile in (('elara_cf1_runtime.glb', 'runtime'), ('elara_cf1_proxy.glb', 'proxy')):
    out = subprocess.run([sys.executable, V, os.path.join(EV, name), '--profile', profile], capture_output=True, text=True, check=True).stdout
    r = json.loads(out)
    bad = [c['check'] for c in r['checks'] if not c['pass']]
    print(name, 'PASS' if r['pass'] else f'FAIL {bad}')
    ok &= r['pass']
sys.exit(0 if ok else 1)
