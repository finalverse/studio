# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent, dependency-free GLB structure check (no Blender, no glTF library)."""
import json
import math
import struct

COMPONENTS = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
WIDTH = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


class GLBError(ValueError):
    pass


def read_accessor(doc, binary, index):
    a = doc['accessors'][index]; view = doc['bufferViews'][a['bufferView']]
    fmt, size = COMPONENTS[a['componentType']]; width = WIDTH[a['type']]
    stride = view.get('byteStride') or size*width
    start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
    end = start + stride*(a['count']-1) + size*width
    if a['count'] < 1 or end > view.get('byteOffset', 0) + view['byteLength'] or end > len(binary):
        raise GLBError(f'accessor {index} outside its buffer view')
    return [struct.unpack_from('<' + fmt*width, binary, start + i*stride) for i in range(a['count'])]


def check(data):
    if len(data) < 28:
        raise GLBError('file too short')
    magic, version, length = struct.unpack_from('<III', data)
    if magic != 0x46546C67 or version != 2 or length != len(data):
        raise GLBError('invalid GLB header')
    json_len, json_type = struct.unpack_from('<II', data, 12)
    if json_type != 0x4E4F534A:
        raise GLBError('first chunk is not JSON')
    doc = json.loads(data[20:20+json_len])
    offset = 20 + json_len; binary = b''
    if offset < len(data):
        bin_len, bin_type = struct.unpack_from('<II', data, offset)
        if bin_type != 0x004E4942 or offset + 8 + bin_len > len(data):
            raise GLBError('invalid BIN chunk')
        binary = data[offset+8:offset+8+bin_len]
    vertices = triangles = 0
    for mesh in doc.get('meshes', []):
        for prim in mesh['primitives']:
            pos = read_accessor(doc, binary, prim['attributes']['POSITION'])
            if not all(math.isfinite(c) for v in pos for c in v):
                raise GLBError('non-finite position')
            acc = doc['accessors'][prim['attributes']['POSITION']]
            for axis in range(3):
                lo = min(v[axis] for v in pos); hi = max(v[axis] for v in pos)
                if abs(lo - acc['min'][axis]) > 1e-4 or abs(hi - acc['max'][axis]) > 1e-4:
                    raise GLBError('POSITION min/max disagree with data')
            vertices += len(pos)
            if 'indices' in prim:
                idx = read_accessor(doc, binary, prim['indices'])
                if any(i[0] >= len(pos) for i in idx):
                    raise GLBError('index out of range')
                triangles += len(idx)//3
    animations = []
    for anim in doc.get('animations', []):
        times_max = 0.0; channels = 0
        for sampler in anim['samplers']:
            times = [t[0] for t in read_accessor(doc, binary, sampler['input'])]
            if not all(math.isfinite(t) for t in times) or times != sorted(times):
                raise GLBError('animation times not finite/ascending')
            out = read_accessor(doc, binary, sampler['output'])
            if not all(math.isfinite(c) for v in out for c in v):
                raise GLBError('non-finite animation output')
            times_max = max(times_max, times[-1])
        for ch in anim['channels']:
            if ch['target'].get('node', -1) >= len(doc.get('nodes', [])):
                raise GLBError('animation targets a missing node')
            channels += 1
        animations.append({'name': anim.get('name'), 'channels': channels, 'duration_s': round(times_max, 5)})
    return {'valid': True, 'bytes': len(data), 'generator': doc.get('asset', {}).get('generator'),
            'nodes': len(doc.get('nodes', [])), 'meshes': len(doc.get('meshes', [])), 'skins': len(doc.get('skins', [])),
            'joints': sum(len(s['joints']) for s in doc.get('skins', [])), 'materials': len(doc.get('materials', [])),
            'vertices': vertices, 'triangles': triangles, 'animations': animations,
            'node_names': [n.get('name') for n in doc.get('nodes', [])][:64]}


if __name__ == '__main__':
    import sys
    print(json.dumps(check(open(sys.argv[1], 'rb').read()), indent=2))
