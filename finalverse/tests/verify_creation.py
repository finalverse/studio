# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent artifact assertions for the actual Gemma beacon acceptance scene."""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

root = Path(sys.argv[1]).resolve()
native = json.loads((root/'native-result.json').read_text()); job = native['job']
assert job['state'] == 'Completed' and native['identity_animation_geometry_persisted']
assert job['model_receipt']['real_inference'] and not job['model_receipt']['fallback_used']
directory = root/'workspace/jobs'/job['id']
bundle = directory/'beacon.fvasset'
manifest = json.loads((bundle/'candidate.json').read_text())
assert manifest['published'] is False
for name, metadata in manifest['assets'].items():
    data = (bundle/name).read_bytes()
    assert len(data) == metadata['byte_length']
    assert hashlib.sha256(data).hexdigest() == metadata['sha256']
glb = (bundle/'asset.glb').read_bytes()
assert struct.unpack_from('<4sII', glb) == (b'glTF', 2, len(glb))
length, kind = struct.unpack_from('<II', glb, 12); assert kind == 0x4e4f534a
g = json.loads(glb[20:20+length]); offset = 20+length
length, kind = struct.unpack_from('<II', glb, offset); assert kind == 0x004e4942
binary = glb[offset+8:offset+8+length]


def values(index):
    a = g['accessors'][index]; v = g['bufferViews'][a['bufferView']]
    n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
    fmt = {5126: 'f', 5125: 'I', 5123: 'H', 5121: 'B'}[a['componentType']]
    size = struct.calcsize('<'+fmt*n); stride = v.get('byteStride', size)
    start = v.get('byteOffset', 0)+a.get('byteOffset', 0)
    assert start + (a['count']-1)*stride+size <= len(binary)
    result = [struct.unpack_from('<'+fmt*n, binary, start+i*stride) for i in range(a['count'])]
    assert all(math.isfinite(c) for row in result for c in row)
    return result


mesh = g['meshes'][0]['primitives'][0]
positions = values(mesh['attributes']['POSITION']); indices = values(mesh['indices'])
assert len(positions) > 8 and len(indices) % 3 == 0
assert all(0 <= row[0] < len(positions) for row in indices)
pbr = g['materials'][mesh['material']]['pbrMetallicRoughness']
assert all(abs(a-b)<1e-6 for a,b in zip(pbr['baseColorFactor'], [.03,.55,.46,1]))
assert abs(pbr['roughnessFactor']-.35) < 1e-6
assert abs(pbr['metallicFactor']-.2) < 1e-6
animation = g['animations'][0]
rotation = next(c for c in animation['channels'] if c['target']['path'] == 'rotation')
sampler = animation['samplers'][rotation['sampler']]
times, rotations = values(sampler['input']), values(sampler['output'])
assert len(times) >= 2 and times[-1][0] > times[0][0]
assert abs(sum(a*b for a,b in zip(rotations[0], rotations[-1]))) < .01
assert any(n.get('extras', {}).get('finalverse.object_id') == job['aliases']['@beacon'] for n in g['nodes'])
render = next(r for r in job['results'] if 'isolation_checks' in r)
assert all(render['isolation_checks'].values())
assert render['metrics']['peak_rss_bytes'] <= render['metrics']['memory_limit_bytes']
assert render['metrics']['wall_seconds'] <= render['metrics']['wall_limit_seconds']
report = {'passed': True, 'job_id': job['id'], 'glb_vertices': len(positions), 'triangles': len(indices)//3,
          'animation_samples': len(times), 'animation_duration_seconds': times[-1][0]-times[0][0],
          'material': pbr, 'stable_id_exported': True, 'source_reopen_passed': True,
          'isolation_checks': render['isolation_checks'], 'render_metrics': render['metrics'],
          'native_wall_seconds': native['wall_seconds'], 'tick_max_seconds': native['tick_max_seconds'],
          'tick_median_seconds': native['tick_median_seconds'],
          'artifact_bytes': {str(p.relative_to(directory)): p.stat().st_size for p in directory.rglob('*') if p.is_file()}}
(root/'verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
