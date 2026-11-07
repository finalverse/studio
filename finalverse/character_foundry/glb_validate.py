"""CF1 runtime-compatibility validator for character GLBs (stdlib + numpy, no Blender).

Checks the glTF directly, the way a native runtime will read it: coordinate
system and bounds, node/mesh hierarchy, material channels, texture formats and
memory, skeleton structure, skin weights (normalised, <= 4 influences, joint
indices in range), animation tracks (targets, durations, finite samples),
and binary integrity (bufferView bounds). Emits finalverse.cf-glb-check/v1.

usage: python3 glb_validate.py FILE.glb [--profile hero|runtime|proxy] > report.json
"""
import hashlib
import io
import json
import struct
import sys

import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
PROFILES = {
    'hero': {'max_tris': 250000, 'max_tex_mib': 160, 'need_skin': True, 'need_anim': True, 'max_tex': 2048},
    'runtime': {'max_tris': 40000, 'max_tex_mib': 48, 'need_skin': True, 'need_anim': True, 'max_tex': 1024},
    'proxy': {'max_tris': 40000, 'max_tex_mib': 0, 'need_skin': False, 'need_anim': False, 'max_tex': 0,
              'single_mesh': True, 'max_materials': 8, 'no_textures': True},
}


def load(path):
    data = open(path, 'rb').read()
    magic, ver, length = struct.unpack_from('<III', data, 0)
    assert magic == 0x46546C67 and ver == 2, 'not a glTF 2 GLB'
    off = 12; chunks = {}
    while off < length:
        clen, ctype = struct.unpack_from('<II', data, off)
        chunks[ctype] = data[off + 8: off + 8 + clen]; off += 8 + clen
    return data, json.loads(chunks[0x4E4F534A]), chunks.get(0x004E4942, b'')


def accessor(g, binc, i):
    a = g['accessors'][i]; bv = g['bufferViews'][a['bufferView']]
    n = NC[a['type']]; dt = CT[a['componentType']]
    start = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    stride = bv.get('byteStride', 0); isz = np.dtype(dt).itemsize * n
    if stride and stride != isz:
        raw = np.frombuffer(binc, np.uint8, count=stride * a['count'], offset=start).reshape(a['count'], stride)[:, :isz]
        arr = np.frombuffer(raw.tobytes(), dt).reshape(a['count'], n)
    else:
        arr = np.frombuffer(binc, dt, count=a['count'] * n, offset=start).reshape(a['count'], n)
    if a.get('normalized'):
        arr = arr.astype(np.float32) / np.iinfo(dt).max
    return arr


def png_jpeg_size(b):
    if b[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png', struct.unpack('>II', b[16:24])
    if b[:2] == b'\xff\xd8':
        i = 2
        while i < len(b):
            if b[i] != 0xFF:
                i += 1; continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack('>HH', b[i + 5:i + 9]); return 'jpeg', (w, h)
            i += 2 + struct.unpack('>H', b[i + 2:i + 4])[0]
    return 'unknown', (0, 0)


def check(path, profile='hero'):
    P = PROFILES[profile]
    data, g, binc = load(path)
    out = {'schema_version': 'finalverse.cf-glb-check/v1', 'file': path.split('/')[-1], 'profile': profile,
           'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'checks': [], 'stats': {}}

    def ok(name, cond, detail=''):
        out['checks'].append({'check': name, 'pass': bool(cond), 'detail': detail})
    # binary integrity
    bad = [i for i, bv in enumerate(g.get('bufferViews', [])) if bv.get('byteOffset', 0) + bv['byteLength'] > len(binc)]
    ok('bufferviews_in_bounds', not bad, f'{len(g.get("bufferViews", []))} views')
    # meshes, triangles, bounds
    tris = 0; mins = []; maxs = []; prims = 0; skinned_prims = 0; weight_err = 0.0; over4 = 0; joint_oob = 0
    nskin_joints = max([len(s['joints']) for s in g.get('skins', [])] or [0])
    mesh_nodes = [n for n in g.get('nodes', []) if 'mesh' in n]
    for m in g.get('meshes', []):
        for p in m['primitives']:
            prims += 1
            pos = accessor(g, binc, p['attributes']['POSITION'])
            mins.append(pos.min(0)); maxs.append(pos.max(0))
            ok_f = np.isfinite(pos).all()
            if not ok_f:
                ok('finite_positions', False, m.get('name'))
            n = g['accessors'][p['indices']]['count'] if 'indices' in p else len(pos)
            tris += n // 3
            if 'JOINTS_0' in p['attributes']:
                skinned_prims += 1
                w = accessor(g, binc, p['attributes']['WEIGHTS_0']).astype(np.float64)
                j = accessor(g, binc, p['attributes']['JOINTS_0'])
                weight_err = max(weight_err, float(np.abs(w.sum(1) - 1).max()))
                joint_oob += int((j >= nskin_joints).sum())
                if 'WEIGHTS_1' in p['attributes']:
                    over4 += 1
    lo = np.min(mins, 0); hi = np.max(maxs, 0)
    out['stats'].update({'triangles': tris, 'primitives': prims, 'mesh_nodes': len(mesh_nodes),
                         'bounds_min': [round(float(x), 4) for x in lo], 'bounds_max': [round(float(x), 4) for x in hi]})
    height = hi[1] - lo[1]
    ok('y_up_height', 1.6 < height < 1.85, f'height along +Y = {height:.3f} m (canon 1.72)')
    ok('ground_contact', abs(lo[1]) < 0.02, f'min Y = {lo[1]:.4f} m (origin at ground contact)')
    ok('centred', abs((lo[0] + hi[0]) / 2) < 0.15 and abs((lo[2] + hi[2]) / 2) < 0.25, 'XZ centre near origin')
    ok('within_8m', np.all(np.abs(lo) < 8) and np.all(np.abs(hi) < 8))
    ok('triangle_budget', tris <= P['max_tris'], f'{tris} <= {P["max_tris"]}')
    if P.get('single_mesh'):
        ok('single_node_single_mesh', len(mesh_nodes) == 1 and len(g['meshes']) == 1)
    # materials & textures
    mats = g.get('materials', [])
    out['stats']['materials'] = len(mats)
    chan = {'baseColorTexture': 0, 'normalTexture': 0, 'metallicRoughnessTexture': 0}
    for m in mats:
        pbr = m.get('pbrMetallicRoughness', {})
        chan['baseColorTexture'] += 'baseColorTexture' in pbr
        chan['metallicRoughnessTexture'] += 'metallicRoughnessTexture' in pbr
        chan['normalTexture'] += 'normalTexture' in m
        ok(f'material_alpha_opaque:{m.get("name")}', m.get('alphaMode', 'OPAQUE') == 'OPAQUE')
    out['stats']['material_channels'] = chan
    if P.get('max_materials'):
        ok('material_count', len(mats) <= P['max_materials'], f'{len(mats)} <= {P["max_materials"]}')
    tex_bytes = 0; fmts = {}; maxdim = 0
    for im in g.get('images', []):
        bv = g['bufferViews'][im['bufferView']]
        b = binc[bv.get('byteOffset', 0): bv.get('byteOffset', 0) + bv['byteLength']]
        fmt, (w, h) = png_jpeg_size(b)
        fmts[fmt] = fmts.get(fmt, 0) + 1
        maxdim = max(maxdim, w, h)
        tex_bytes += w * h * 4 * 4 // 3          # RGBA8 + mip chain once uploaded
    out['stats'].update({'images': len(g.get('images', [])), 'image_formats': fmts, 'max_texture_dim': maxdim,
                         'gpu_texture_mib_rgba8_mips': round(tex_bytes / 2 ** 20, 1)})
    if P.get('no_textures'):
        ok('factor_only_pbr', not g.get('images') and not g.get('textures'))
    else:
        ok('textures_jpeg_or_png', set(fmts) <= {'png', 'jpeg'}, str(fmts))
        ok('texture_dim_cap', maxdim <= P['max_tex'], f'{maxdim} <= {P["max_tex"]}')
        ok('texture_memory', tex_bytes / 2 ** 20 <= P['max_tex_mib'], f'{tex_bytes / 2**20:.1f} MiB <= {P["max_tex_mib"]}')
        ok('pbr_channels_present', chan['baseColorTexture'] > 0 and chan['normalTexture'] > 0 and chan['metallicRoughnessTexture'] > 0, str(chan))
    # skeleton & skin
    skins = g.get('skins', [])
    if P['need_skin']:
        ok('one_skin', len(skins) == 1, f'{len(skins)} skins')
        if skins:
            s = skins[0]; joints = s['joints']
            names = [g['nodes'][j].get('name') for j in joints]
            ibm = accessor(g, binc, s['inverseBindMatrices'])
            ok('inverse_bind_matrices', len(ibm) == len(joints) and np.isfinite(ibm).all())
            required = ['root', 'spine05', 'spine01', 'neck01', 'head', 'jaw', 'eye.L', 'eye.R', 'upperarm01.L', 'upperarm01.R',
                        'lowerarm01.L', 'wrist.L', 'upperleg01.L', 'lowerleg01.L', 'foot.L', 'orbicularis03.L', 'oris07.L']
            missing = [r for r in required if r not in names]
            ok('skeleton_structure', not missing, f'{len(joints)} joints; missing: {missing}')
            out['stats']['joints'] = len(joints)
        ok('skin_weights_normalised', weight_err < 0.01, f'max |sum-1| = {weight_err:.4f}')
        ok('max_4_influences', over4 == 0, f'{over4} primitives use WEIGHTS_1')
        ok('joint_indices_in_range', joint_oob == 0)
        ok('all_mesh_nodes_skinned', all('skin' in n for n in mesh_nodes), f'{sum("skin" in n for n in mesh_nodes)}/{len(mesh_nodes)}')
    # animations
    anims = g.get('animations', [])
    out['stats']['animations'] = []
    for a in anims:
        tmax = 0.0; finite = True; targets = set()
        for smp in a['samplers']:
            t = accessor(g, binc, smp['input']); v = accessor(g, binc, smp['output'])
            tmax = max(tmax, float(t.max())); finite &= bool(np.isfinite(v).all())
            ok_mono = bool(np.all(np.diff(t[:, 0]) > 0))
            if not ok_mono:
                finite = False
        for ch in a['channels']:
            targets.add(ch['target'].get('path'))
        out['stats']['animations'].append({'name': a.get('name'), 'duration_s': round(tmax, 3), 'channels': len(a['channels']),
                                           'paths': sorted(targets)})
        ok(f'anim_finite_monotonic:{a.get("name")}', finite)
    if P['need_anim']:
        names = [a.get('name', '') for a in anims]
        for req in ('Elara_Idle', 'Elara_Walk', 'Elara_Wave'):
            ok(f'clip_present:{req}', any(req in n for n in names), str(names))
    out['pass'] = all(c['pass'] for c in out['checks'])
    return out


if __name__ == '__main__':
    prof = sys.argv[sys.argv.index('--profile') + 1] if '--profile' in sys.argv else 'hero'
    print(json.dumps(check(sys.argv[1], prof), indent=2))
