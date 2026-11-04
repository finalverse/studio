# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""V1 founder plans (finalverse.creation/v2 data). Identities are the accepted E1
canon identities; they are referenced, never created. Plans are hand-authored
artist drafts; the Gemma loop may propose its own plans for the same founders."""
V2 = 'finalverse.creation/v2'
FOUNDERS = {
    #  key      name                   identity                                  archetype            height rig
    'elara':  ('Elara',                '904d952a-aca7-51da-aa01-20aab7dd9893', 'humanoid',          1.70, 'humanoid_basic'),
    'auren':  ('Auren',                'b9d8a3dd-6dbe-5aa6-aa0e-24bf7ecba447', 'humanoid',          1.85, 'humanoid_basic'),
    'kai':    ('Kai',                  'af14d037-099a-5db0-9712-6c8a25742930', 'synthetic_humanoid', 1.90, 'synthetic_basic'),
    'lumi':   ('Lumi',                 '2c92f74c-3643-5dac-95c6-e20af424767d', 'floating_spirit',   0.95, None),
    'terra':  ('Terra',                'a7c374b9-d7d9-5a68-9bcb-68e9ea8ecd4d', 'nature_elemental',  2.60, 'tree_basic'),
    'ignis':  ('Ignis',                '1b347812-86f7-576a-bbb8-f44d7bd00643', 'fire_elemental',    2.20, 'fire_basic'),
    'melody': ("Elara's Melody Sprite", '8a801b9c-bf8b-5ca0-a0a7-a41c3a6231a9', 'botanical_sprite',  0.30, None),
}


def bone_clip(ref, name, kind, locomotion, frames, keys):
    return {'op': 'action.create', 'ref': ref, 'name': name, 'target': '@rig', 'kind': kind,
            'locomotion': locomotion, 'loop': kind in ('idle', 'locomote'),
            'keys': [{'frame': f, 'bone': b, 'rotation': r} for f, b, r in keys] if keys else []}


def humanoid_clips(prefix, walk='walk'):
    walk_keys = [(f, b, [s*a, 0, 0]) for f, a in ((1, .4), (13, -.4), (25, .4))
                 for b, s in (('leg_l', 1), ('leg_r', -1), ('arm_l', -.6), ('arm_r', .6))]
    idle_keys = [(1, 'root', [0, 0, 0]), (30, 'root', [.02, 0, 0]), (60, 'root', [0, 0, 0]),
                 (1, 'head', [0, 0, 0]), (30, 'head', [-.04, 0, .03]), (60, 'head', [0, 0, 0])]
    greet_keys = [(1, 'arm_r', [0, 0, 0]), (10, 'arm_r', [0, -.3, -2.2]), (18, 'arm_r', [0, -.3, -2.5]),
                  (26, 'arm_r', [0, -.3, -2.2]), (36, 'arm_r', [0, 0, 0])]
    inspect_keys = [(1, 'head', [0, 0, 0]), (14, 'head', [.25, 0, .35]), (30, 'head', [.25, 0, -.3]), (44, 'head', [0, 0, 0])]
    clips = [bone_clip('@idle', f'{prefix} Idle', 'idle', 'none', 60, sorted(idle_keys)),
             bone_clip('@walk', f'{prefix} Walk', 'locomote', walk, 25, sorted(walk_keys)),
             bone_clip('@greet', f'{prefix} Greet', 'greet', 'none', 36, sorted(greet_keys)),
             bone_clip('@inspect', f'{prefix} Inspect', 'observe', 'none', 44, sorted(inspect_keys))]
    for c in clips:
        c['keys'].sort(key=lambda k: k['frame'])
    return clips


def terra_clips():
    sway = [(f, b, r) for f, ang in ((1, 0), (40, .06), (80, 0)) for b, r in (('canopy', [ang, 0, ang/2]), ('branch_l', [0, ang, 0]), ('branch_r', [0, -ang, 0]))]
    greet = [(1, 'branch_r', [0, 0, 0]), (16, 'branch_r', [0, -.5, -.6]), (30, 'branch_r', [0, -.5, -.4]), (46, 'branch_r', [0, 0, 0])]
    inspect = [(1, 'canopy', [0, 0, 0]), (20, 'canopy', [.12, 0, .2]), (44, 'canopy', [0, 0, 0])]
    rooted = [(1, 'trunk', [0, 0, 0]), (30, 'trunk', [.03, 0, 0]), (60, 'trunk', [0, 0, 0])]
    out = [bone_clip('@idle', 'Terra Canopy Sway', 'idle', 'none', 80, sway),
           bone_clip('@walk', 'Terra Rooted Shift', 'locomote', 'rooted', 60, rooted),
           bone_clip('@greet', 'Terra Branch Greet', 'greet', 'none', 46, greet),
           bone_clip('@inspect', 'Terra Inspect', 'observe', 'none', 44, inspect)]
    for c in out:
        c['keys'].sort(key=lambda k: k['frame'])
    return out


def spirit_clips(prefix, height, travel):
    lift = height * .08
    return [
        {'op': 'action.create', 'ref': '@hover', 'name': f'{prefix} Hover', 'target': '@body', 'kind': 'idle',
         'locomotion': 'hover', 'loop': True, 'keys': [
            {'frame': 1, 'location': [0, 0, 0], 'scale': [1, 1, 1]},
            {'frame': 24, 'location': [0, 0, lift], 'scale': [1.03, 1.03, .97]},
            {'frame': 48, 'location': [0, 0, 0], 'scale': [1, 1, 1]}]},
        {'op': 'action.create', 'ref': '@walk', 'name': f'{prefix} {travel.title()}', 'target': '@body', 'kind': 'locomote',
         'locomotion': travel, 'loop': True, 'keys': [
            {'frame': 1, 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
            {'frame': 18, 'location': [height*.25, 0, lift], 'rotation': [0, .1, .12]},
            {'frame': 36, 'location': [0, 0, lift*1.5], 'rotation': [0, 0, 0]},
            {'frame': 54, 'location': [-height*.25, 0, lift], 'rotation': [0, -.1, -.12]},
            {'frame': 72, 'location': [0, 0, 0], 'rotation': [0, 0, 0]}]},
        {'op': 'action.create', 'ref': '@greet', 'name': f'{prefix} Greet', 'target': '@body', 'kind': 'greet',
         'locomotion': 'none', 'loop': False, 'keys': [
            {'frame': 1, 'location': [0, 0, 0], 'scale': [1, 1, 1]},
            {'frame': 12, 'location': [0, 0, lift*2], 'scale': [1.06, 1.06, 1.06]},
            {'frame': 30, 'location': [0, 0, lift*.5], 'scale': [1, 1, 1]}]}]


def plan(key, palette=None):
    name, identity, archetype, h, rig = FOUNDERS[key]
    founder = {'op': 'character.founder', 'ref': '@body', 'name': name, 'founder': key, 'height': h}
    if palette:
        founder['palette'] = palette
    ops = [{'op': 'scene.inspect'}, founder]
    prefix = name.split("'")[0].split()[0]
    if rig:
        ops += [{'op': 'armature.create', 'ref': '@rig', 'name': f'{prefix} Rig', 'template': rig, 'height': h},
                {'op': 'armature.skin', 'target': '@body', 'armature': '@rig', 'method': 'rigid'}]
        ops += terra_clips() if key == 'terra' else humanoid_clips(prefix)
    else:
        ops += spirit_clips(prefix, h, 'drift' if key == 'lumi' else 'fly')
    clips = [o['ref'] for o in ops if o['op'] == 'action.create']
    width = max(h * .9, .45) if key not in ('terra',) else h * .8
    centre = h * (.62 if key in ('lumi', 'melody') else .52)
    dist = max(h, width) * 2.35
    ops += [{'op': 'camera.configure', 'ref': '@cam', 'name': f'{prefix} Front Camera',
             'location': [0, -dist, centre + h*.06], 'look_at': [0, 0, centre], 'lens': 50},
            {'op': 'light.rig', 'ref': '@key', 'name': f'{prefix} Light', 'style': 'three_point',
             'target': [0, 0, centre], 'distance': max(3, h*2.2), 'energy': 260*max(1, h)**2, 'color': [1, .97, .93]},
            {'op': 'render.configure', 'engine': 'EEVEE', 'frame_start': 1, 'frame_end': 72, 'fps': 24,
             'transparent': True, 'world_color': [.05, .06, .08], 'world_strength': .7,
             'view_transform': 'Khronos PBR Neutral'},
            {'op': 'preview.render', 'path': f'{key}-front.png', 'width': 512, 'height': 512, 'samples': 16, 'frame': 1}]
    return {'schema_version': V2, 'summary': f'V1 {name}: reviewed founder template, rig, clips and preview', 'operations': ops}, \
        {'op': 'asset.package', 'path': f'{key}.fvpkg', 'archetype': archetype, 'subject': '@body', 'name': name,
         'identity': identity, 'clips': clips, 'lod1_ratio': .38}
