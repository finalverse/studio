# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded self-contained GLB admission and geometric round-trip comparison.

The geographic foundation owns CRS mathematics. This module measures glTF-local
triangles only; FWD frame and transforms are preserved separately and verbatim.
"""
import hashlib
import json
import math
import struct

MAX_BYTES = 64 * 1024 * 1024
MAX_VERTICES = 200_000
MAX_TRIANGLES = 200_000


def unique_object(pairs):
    d = {}
    for key, value in pairs:
        if key in d:
            raise ValueError('Duplicate JSON key: ' + key)
        d[key] = value
    return d


def _index(array, value):
    if type(value) is not int or not 0 <= value < len(array):
        raise ValueError('Index outside array')
    return array[value]


def _vector(value, count):
    if (not isinstance(value, list) or len(value) != count or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise ValueError('Invalid finite vector')
    return value


def _matrix(node):
    if 'matrix' in node:
        m = _vector(node['matrix'], 16)
        if any(k in node for k in ('translation', 'rotation', 'scale')):
            raise ValueError('Matrix and TRS cannot coexist')
        if m[3:16:4] != [0, 0, 0, 1]:
            raise ValueError('Non-affine matrix')
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    t = _vector(node.get('translation', [0, 0, 0]), 3)
    s = _vector(node.get('scale', [1, 1, 1]), 3)
    x, y, z, w = _vector(node.get('rotation', [0, 0, 0, 1]), 4)
    if abs(x*x + y*y + z*z + w*w - 1) > 1e-5:
        raise ValueError('Quaternion must be normalized')
    a = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
         [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
         [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    return [[a[r][c] * s[c] for c in range(3)] + [t[r]] for r in range(3)] + [[0, 0, 0, 1]]


def _mul(a, b):
    return [[sum(a[r][i] * b[i][c] for i in range(4)) for c in range(4)] for r in range(4)]


def _point(matrix, p):
    return tuple(sum(matrix[r][c]*p[c] for c in range(3)) + matrix[r][3] for r in range(3))


def parse(data):
    if not 28 <= len(data) <= MAX_BYTES:
        raise ValueError('GLB size outside 28 bytes..64 MiB')
    magic, version, length = struct.unpack_from('<III', data)
    if (magic, version, length) != (0x46546c67, 2, len(data)):
        raise ValueError('Invalid GLB header')
    chunks = []
    cursor = 12
    while cursor < len(data):
        if cursor + 8 > len(data):
            raise ValueError('Truncated GLB chunk')
        size, kind = struct.unpack_from('<II', data, cursor)
        if size % 4 or cursor + 8 + size > len(data):
            raise ValueError('Invalid GLB chunk length')
        chunks.append((kind, data[cursor+8:cursor+8+size]))
        cursor += 8 + size
    if len(chunks) != 2 or [c[0] for c in chunks] != [0x4e4f534a, 0x004e4942]:
        raise ValueError('Exactly one JSON and one BIN chunk are required')
    if len(chunks[0][1]) > 2 * 1024 * 1024:
        raise ValueError('GLB JSON exceeds two MiB')
    doc = json.loads(chunks[0][1], object_pairs_hook=unique_object,
                     parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
    binary = chunks[1][1]
    if doc.get('asset', {}).get('version') != '2.0':
        raise ValueError('glTF 2.0 required')
    if doc.get('extensionsRequired') or doc.get('extensionsUsed') or doc.get('skins') or doc.get('animations'):
        raise ValueError('Only static, extension-free geographic GLBs are admitted')
    if len(doc.get('buffers', [])) != 1 or 'uri' in doc['buffers'][0]:
        raise ValueError('One embedded buffer required')
    declared = doc['buffers'][0].get('byteLength', -1)
    if type(declared) is not int or not 0 <= declared <= len(binary) or len(binary)-declared > 3:
        raise ValueError('Buffer length mismatch')
    if len(doc.get('nodes', [])) > 1024 or len(doc.get('meshes', [])) > 256:
        raise ValueError('Node/mesh admission budget exceeded')
    if doc.get('images') or doc.get('textures'):
        raise ValueError('Textures and image URIs are outside this geometry/material exchange profile')
    if any(len(doc.get(k, [])) > 2048 for k in ('accessors', 'bufferViews', 'materials')):
        raise ValueError('Metadata array budget exceeded')
    if sum(a.get('count', 0) for a in doc.get('accessors', [])) > 2_000_000:
        raise ValueError('Total accessor element budget exceeded')
    for image in doc.get('images', []):
        if 'uri' in image:
            raise ValueError('External and data image URIs are refused')
        _index(doc.get('bufferViews', []), image.get('bufferView'))
    formats = {5121: ('B', 1), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
    widths = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
    vertices = 0

    def accessor(index, position=False):
        nonlocal vertices
        item = _index(doc.get('accessors', []), index)
        if 'sparse' in item or item.get('normalized', False):
            raise ValueError('Sparse or normalized geometry is unsupported')
        view = _index(doc.get('bufferViews', []), item.get('bufferView'))
        if view.get('buffer') != 0:
            raise ValueError('Only the embedded buffer is allowed')
        component = item.get('componentType')
        if component not in formats or item.get('type') not in widths:
            raise ValueError('Unsupported accessor type')
        fmt, size = formats[component]
        width = widths[item['type']]
        if position and (component != 5126 or width != 3):
            raise ValueError('POSITION must be FLOAT VEC3')
        count = item.get('count')
        if type(count) is not int or not 1 <= count <= MAX_TRIANGLES * 3:
            raise ValueError('Accessor count outside bounds')
        if position:
            vertices += count
            if vertices > MAX_VERTICES:
                raise ValueError('Vertex budget exceeded')
        offset, view_bytes = view.get('byteOffset', 0), view.get('byteLength')
        within = item.get('byteOffset', 0)
        stride = view.get('byteStride', size*width)
        if any(type(v) is not int or v < 0 for v in (offset, view_bytes, within, stride)):
            raise ValueError('Invalid accessor layout')
        if stride < size*width or stride > 252 or stride % size or within % size:
            raise ValueError('Invalid accessor alignment/stride')
        end = within + stride*(count-1) + size*width
        if end > view_bytes or offset + view_bytes > declared:
            raise ValueError('Accessor escapes its buffer view')
        values = [struct.unpack_from('<' + fmt*width, binary, offset+within+i*stride) for i in range(count)]
        if not all(math.isfinite(c) and abs(c) <= 1e7 for v in values for c in v):
            raise ValueError('Non-finite or excessive geometry coordinate')
        return values

    mesh_triangles = []
    for mesh in doc.get('meshes', []):
        tris = []
        if not isinstance(mesh.get('primitives'), list) or len(mesh['primitives']) > 256:
            raise ValueError('Invalid primitive list')
        for prim in mesh['primitives']:
            if prim.get('mode', 4) != 4 or prim.get('targets'):
                raise ValueError('Only static triangle primitives supported')
            pos = accessor(prim['attributes']['POSITION'], True)
            if 'indices' in prim:
                acc = _index(doc['accessors'], prim['indices'])
                if acc.get('componentType') not in (5121, 5123, 5125) or acc.get('type') != 'SCALAR':
                    raise ValueError('Indices must be unsigned SCALAR')
                indices = [i[0] for i in accessor(prim['indices'])]
            else:
                indices = list(range(len(pos)))
            if len(indices) % 3 or any(i >= len(pos) for i in indices):
                raise ValueError('Triangle indices invalid')
            tris.extend(tuple(pos[i] for i in indices[n:n+3]) for n in range(0, len(indices), 3))
            if len(tris) > MAX_TRIANGLES:
                raise ValueError('Triangle budget exceeded')
        mesh_triangles.append(tris)
    nodes = doc.get('nodes', [])
    if len(doc.get('scenes', [])) != 1:
        raise ValueError('Exactly one GLB scene is required; unrelated authoring scenes must not leak')
    scene = _index(doc.get('scenes', []), doc.get('scene', 0))
    visited, used_meshes, triangles = set(), set(), []
    identity = [[float(r == c) for c in range(4)] for r in range(4)]

    def visit(index, parent, depth):
        if index in visited or depth > 64:
            raise ValueError('Scene graph is cyclic or multiply parented')
        node = _index(nodes, index)
        visited.add(index)
        matrix = _mul(parent, _matrix(node))
        if 'mesh' in node:
            used_meshes.add(node['mesh'])
            for triangle in _index(mesh_triangles, node['mesh']):
                transformed = tuple(_point(matrix, p) for p in triangle)
                if any(not math.isfinite(c) or abs(c) > 1e7 for p in transformed for c in p):
                    raise ValueError('Scene transform exceeds coordinate budget')
                triangles.append(transformed)
                if len(triangles) > MAX_TRIANGLES:
                    raise ValueError('Instanced triangle budget exceeded')
        for child in node.get('children', []):
            visit(child, matrix, depth+1)

    for root in scene.get('nodes', []):
        visit(root, identity, 0)
    if len(visited) != len(nodes) or len(used_meshes) != len(mesh_triangles):
        raise ValueError('Orphaned nodes/meshes are outside the geographic exchange profile')
    if not triangles:
        raise ValueError('Scene contains no triangles')
    bounds = [[min(p[a] for tri in triangles for p in tri) for a in range(3)],
              [max(p[a] for tri in triangles for p in tri) for a in range(3)]]
    return {'doc': doc, 'triangles': triangles, 'bounds': bounds,
            'summary': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                        'vertices': vertices, 'triangles': len(triangles),
                        'meshes': len(mesh_triangles), 'bounds_gltf': bounds}}


def compare(before, after, tolerance=0.001):
    """Compare every triangle corner, not only scene extents, in glTF metres."""
    if not 0 < tolerance <= 0.001:
        raise ValueError('At most one millimetre tolerance is allowed')
    def canonical(tris):
        return sorted(tuple(sorted(tri)) for tri in tris)
    a, b = canonical(before['triangles']), canonical(after['triangles'])
    if len(a) != len(b):
        raise ValueError('Round-trip changed the triangle count')
    error = max(abs(x-y) for ta, tb in zip(a, b) for pa, pb in zip(ta, tb) for x, y in zip(pa, pb))
    if error > tolerance:
        raise ValueError(f'Round-trip geometry drift {error:g} exceeds {tolerance:g} metres')
    return {'triangles': len(a), 'maximum_corner_error_gltf_units': error,
            'tolerance_gltf_units': tolerance, 'frame_transform_preserved_separately': True}
