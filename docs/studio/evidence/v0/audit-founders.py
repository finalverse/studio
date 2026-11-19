"""V0 read-only audit of the seven E1 founders' published assets (Genesis CAS)."""
import json, hashlib, sys, struct
from pathlib import Path
G = Path('/Users/wenyan/Finalverse/dev/civilization-os2-20261103/e1/generated')
cat = json.loads((G/'catalog.json').read_text())
canon = {c['identity']: c for c in json.load(open('/Users/wenyan/Finalverse/dev/worktrees/core-civilization-os2-e1-20261103/docs/civilization-os/e1-evidence/canon.json'))['characters']}
out = []
for ch in cat['characters']:
    d = ch['definition']; ident = ch['identity']; c = canon.get(ident, {})
    job = ch.get('job', {}); arts = job.get('artifacts', {})
    body = json.loads((G/'cas'/d['artifact_sha256']).read_bytes())
    lods = []
    for lod in body['lods']:
        mats = {json.dumps(p['material'], sort_keys=True) for p in lod['parts']}
        lods.append({'distance_m': lod['distance_m'], 'parts': len(lod['parts']),
                     'triangles': sum(len(p['indices'])//3 for p in lod['parts']),
                     'vertices': sum(len(p['positions']) for p in lod['parts']),
                     'unique_materials': len(mats),
                     'emissive_parts': sum(1 for p in lod['parts'] if any(p['material']['emissive_rgb'])),
                     'pulsing_parts': sum(1 for p in lod['parts'] if p['material']['pulse_amplitude'] > 0),
                     'metallic_parts': sum(1 for p in lod['parts'] if p['material']['metallic'] > .5)})
    ys = [v[1] for p in body['lods'][0]['parts'] for v in p['positions']]
    glb = {k: v for k, v in arts.items() if k.endswith('.glb')}
    glb_info = {}
    for k, h in glb.items():
        b = (G/'cas'/h).read_bytes(); n = struct.unpack_from('<I', b, 12)[0]; doc = json.loads(b[20:20+n])
        glb_info[k] = {'bytes': len(b), 'meshes': len(doc.get('meshes', [])), 'skins': len(doc.get('skins', [])),
                       'animations': len(doc.get('animations', [])), 'images': len(doc.get('images', [])),
                       'textures': len(doc.get('textures', [])), 'materials': len(doc.get('materials', []))}
    out.append({'name': c.get('display_name'), 'identity': ident, 'archetype': d['archetype'], 'revision': d['revision'],
                'canon_appearance': c.get('appearance'), 'generator': ch['generation']['generator'],
                'blender': ch['generation']['blender'], 'body_bytes': ch['generation']['body_bytes'],
                'height_m': round(max(ys)-min(ys), 3) if ys else None,
                'skeleton_joints': len(d['skeleton']['joints']) if d['skeleton'] else 0,
                'joint_names': [j['name'] for j in d['skeleton']['joints']] if d['skeleton'] else [],
                'lods': lods, 'part_names_lod0': sorted({p['name'] for p in body['lods'][0]['parts']})[:40],
                'locomotion': d['locomotion']['modes'], 'expressions': d['animation']['expressions'],
                'animation_procedure': d['animation']['procedure'], 'deformation': d['deformation'],
                'particles': d['manifestation']['max_particles'], 'collision': d['collision'],
                'job_artifacts': sorted(arts), 'glb_proxies': glb_info,
                'baked_clips': 0, 'textures': sum(g['textures'] for g in glb_info.values())})
print(json.dumps({'schema_version': 'finalverse.v0-founder-audit/v1', 'source': str(G), 'characters': out}, indent=1))
