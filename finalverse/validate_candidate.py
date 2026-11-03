#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""S0 transport-integrity gate. Not a substitute for Genesis geometry/policy validation."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def validate(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('regular candidate directory required')
    raw = root / 'candidate.json'
    if raw.is_symlink() or raw.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('bounded regular manifest required')
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('duplicate JSON key')
            out[key] = value
        return out
    doc = json.loads(raw.read_text(), object_pairs_hook=pairs)
    if doc['schema_version'] != 'finalverse.studio-candidate/v1' or doc['state'] != 'candidate' or doc['published'] is not False:
        raise ValueError('candidate schema or authority mismatch')
    if set(doc['assets']) != {'asset.glb', 'source.blend'}:
        raise ValueError('only named local source and GLB assets supported')
    for name, ref in doc['assets'].items():
        p = root / name
        if p.is_symlink() or not p.is_file() or not 0 < p.stat().st_size <= 128 * 1024 * 1024:
            raise ValueError('bounded regular asset required')
        data = p.read_bytes()
        if len(data) != ref['byte_length'] or hashlib.sha256(data).hexdigest() != ref['sha256']:
            raise ValueError('asset integrity mismatch')
        if name == 'asset.glb':
            if len(data) < 20 or struct.unpack_from('<III', data) != (0x46546c67, 2, len(data)):
                raise ValueError('invalid GLB header')
    return {'schema_version': 'finalverse.studio-integrity-receipt/v1', 'valid': True,
            'manifest_sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
            'genesis_geometry_validated': False, 'publication_authorized': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate')
    print(json.dumps(validate(parser.parse_args().candidate), sort_keys=True))
