# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run inside Studio: --background --factory-startup --python THIS -- ..."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/modules'))
from finalverse_fwd.exchange import PALETTES, roundtrip

parser = argparse.ArgumentParser(description='Studio canonical FWD offline material round-trip')
parser.add_argument('--definition', required=True)
parser.add_argument('--cas-root', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--validator', required=True)
parser.add_argument('--asset-id')
parser.add_argument('--palette', choices=sorted(PALETTES), default='urban_clay')
parser.add_argument('--samples', type=int, default=16)
parser.add_argument('--size', type=int, default=512)
parser.add_argument('--no-render', action='store_true')
parser.add_argument('--cycles-binary', help='Explicit Cycles-enabled backend when Studio was built without Cycles')
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
result = roundtrip(args.definition, args.cas_root, args.output, args.validator,
                   args.asset_id, args.palette, not args.no_render, args.samples, args.size, args.cycles_binary)
print('FINALVERSE_FWD_RECEIPT ' + json.dumps(result, sort_keys=True))
