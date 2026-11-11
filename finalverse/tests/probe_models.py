# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit live local-model acceptance probe, not part of offline unit tests."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).parents[2]/'scripts/modules'))
from finalverse_creation.protocol import canonical
from finalverse_creation.providers import default_registry, models, plan, registry

parser = argparse.ArgumentParser()
parser.add_argument('--snapshot', required=True); parser.add_argument('--output', required=True)
parser.add_argument('--model', required=True); parser.add_argument('--prompt')
args = parser.parse_args()
out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=True)
default_registry(out/'providers.json'); provider = registry(out/'providers.json')['local']
snapshot = json.loads(Path(args.snapshot).read_text())
prompt = args.prompt or (
    'Inspect this empty scene. Create one cube named Aurora Beacon using @beacon. '
    'Bevel its geometry (width 0.12, segments 3). Create a teal material @teal (RGBA 0.03,0.55,0.46,1; '
    'roughness 0.35, metallic 0.2) and assign it. Animate @beacon rotation [0,0,0] at frame 1 and '
    '[0,0,3.14] at frame 48. Create camera @camera at [6,-8,5], look_at [0,0,0], lens 50. '
    'Create AREA light @light at [2,-4,6], energy 1200, white color. Render preview.png 384x384 '
    'with 16 samples. Export beacon.fvasset. Save beacon.blend. Use only the required typed operations. '
    'Include all these steps in the proposal. Do not add transformations or unrelated objects.')
started = time.monotonic()
try:
    result = {'ok': True, **plan(provider, args.model, prompt, snapshot)}
except Exception as error:
    result = {'ok': False, 'error': type(error).__name__, 'detail': str(error),
              'model': args.model, 'fallback_used': False}
result['total_wall_seconds'] = time.monotonic()-started
result['prompt'] = prompt
(out/'result.json').write_text(canonical(result))
print(json.dumps({k: v for k, v in result.items() if k not in {'plan', 'prompt'}}, indent=2))
sys.exit(0 if result['ok'] else 1)
