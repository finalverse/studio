# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Hand-written S2 fixture plans (test data, never model output)."""
V2 = 'finalverse.creation/v2'
LUMI_IDENTITY = '2c92f74c-3643-5dac-95c6-e20af424767d'  # E1 canon identity, referenced only


def plan(summary, operations):
    return {'schema_version': V2, 'summary': summary, 'operations': operations}


def lumi_clips(target='@lumi'):
    return [
        {'op': 'action.create', 'ref': '@hover', 'name': 'Lumi Hover', 'target': target, 'kind': 'idle',
         'locomotion': 'hover', 'loop': True, 'keys': [
            {'frame': 1, 'location': [0, 0, 0], 'scale': [1, 1, 1]},
            {'frame': 24, 'location': [0, 0, .06], 'scale': [1.03, 1.03, .96]},
            {'frame': 48, 'location': [0, 0, 0], 'scale': [1, 1, 1]}]},
        {'op': 'action.create', 'ref': '@drift', 'name': 'Lumi Drift', 'target': target, 'kind': 'locomote',
         'locomotion': 'drift', 'loop': True, 'keys': [
            {'frame': 1, 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
            {'frame': 19, 'location': [.25, .05, .04], 'rotation': [0, 0, .15]},
            {'frame': 37, 'location': [0, 0, .08], 'rotation': [0, 0, 0]},
            {'frame': 55, 'location': [-.25, -.05, .04], 'rotation': [0, 0, -.15]},
            {'frame': 72, 'location': [0, 0, 0], 'rotation': [0, 0, 0]}]},
        {'op': 'action.create', 'ref': '@greet', 'name': 'Lumi Greet', 'target': target, 'kind': 'greet',
         'locomotion': 'none', 'loop': False, 'keys': [
            {'frame': 1, 'location': [0, 0, 0], 'rotation': [0, 0, 0], 'scale': [1, 1, 1]},
            {'frame': 14, 'location': [0, 0, .18], 'rotation': [0, .1, 0], 'scale': [1.06, 1.06, 1.06]},
            {'frame': 36, 'location': [0, 0, .05], 'rotation': [0, 0, 0], 'scale': [1, 1, 1]}]}]


def lumi_scene(camera=([0, -4.2, 1.0], [0, 0, .62])):
    return [
        {'op': 'scene.inspect'},
        {'op': 'character.spirit', 'ref': '@lumi', 'name': 'Lumi', 'height': 1.2, 'body_width': 1.0, 'crown': 1.0,
         'fins': 1.0, 'eyes': 1.1, 'location': [0, 0, 0]},
        {'op': 'material.preset', 'ref': '@glow', 'name': 'Lumi Spirit Glow', 'color': [.68, .86, .76, 1],
         'roughness': .45, 'metallic': 0, 'emission': [.25, .48, .36], 'emission_strength': 1.5},
        {'op': 'material.preset', 'ref': '@eye', 'name': 'Lumi Eye', 'color': [.02, .05, .06, 1], 'roughness': .2},
        {'op': 'material.assign_parts', 'target': '@lumi', 'material': '@glow', 'part': 'all'},
        {'op': 'material.assign_parts', 'target': '@lumi', 'material': '@eye', 'part': 'eyes'},
        *lumi_clips(),
        {'op': 'camera.configure', 'ref': '@cam', 'name': 'Preview Camera', 'location': camera[0],
         'look_at': camera[1], 'lens': 50},
        {'op': 'light.rig', 'ref': '@key', 'name': 'Lumi Light', 'style': 'three_point', 'target': [0, 0, .6],
         'distance': 4, 'energy': 600, 'color': [1, .97, .92]},
        {'op': 'render.configure', 'engine': 'EEVEE', 'frame_start': 1, 'frame_end': 72, 'fps': 24,
         'transparent': True, 'world_color': [.03, .04, .06], 'world_strength': .6, 'view_transform': 'AgX'},
        {'op': 'preview.render', 'path': 'lumi-front.png', 'width': 384, 'height': 384, 'samples': 16, 'frame': 1}]


LUMI_PACKAGE = {'op': 'asset.package', 'path': 'lumi.fvpkg', 'archetype': 'floating_spirit', 'subject': '@lumi',
                'name': 'Lumi', 'identity': LUMI_IDENTITY, 'clips': ['@hover', '@drift', '@greet'], 'lod1_ratio': .35}


def environment():
    return plan('Fixture: village block with buildings and scattered trees', [
        {'op': 'scene.inspect'},
        {'op': 'mesh.primitive', 'ref': '@ground', 'name': 'Village Ground', 'shape': 'plane', 'size': [40, 40, 1]},
        {'op': 'procedural.building', 'ref': '@hall', 'name': 'Town Hall', 'location': [-6, 4, 0], 'floors': 3,
         'width': 8, 'depth': 6, 'floor_height': 3.2, 'window_columns': 4, 'roof': 'gable', 'seed': 11},
        {'op': 'procedural.building', 'ref': '@tower', 'name': 'Archive Tower', 'location': [6, 5, 0], 'floors': 6,
         'width': 5, 'depth': 5, 'floor_height': 3, 'window_columns': 3, 'roof': 'flat', 'seed': 12},
        {'op': 'procedural.tree', 'ref': '@oak', 'name': 'Oak Prototype', 'location': [0, 0, 0], 'kind': 'broadleaf',
         'height': 5, 'trunk_radius': .25, 'branches': 5, 'seed': 3},
        {'op': 'procedural.tree', 'ref': '@pine', 'name': 'Pine', 'location': [12, -8, 0], 'kind': 'conifer',
         'height': 8, 'trunk_radius': .3, 'branches': 4, 'seed': 4},
        {'op': 'mesh.primitive', 'ref': '@meadow', 'name': 'Meadow Patch', 'shape': 'plane', 'size': [14, 8, 1],
         'location': [0, -10, .01]},
        {'op': 'material.preset', 'ref': '@stone', 'name': 'Stone', 'color': [.55, .52, .47, 1], 'roughness': .8},
        {'op': 'material.preset', 'ref': '@glass', 'name': 'Window Glass', 'color': [.1, .16, .22, 1], 'roughness': .1,
         'metallic': .2, 'emission': [1, .75, .4], 'emission_strength': .6},
        {'op': 'material.preset', 'ref': '@slate', 'name': 'Roof Slate', 'color': [.22, .2, .24, 1], 'roughness': .6},
        {'op': 'material.preset', 'ref': '@bark', 'name': 'Bark', 'color': [.18, .13, .05, 1], 'roughness': .9},
        {'op': 'material.preset', 'ref': '@leaf', 'name': 'Leaf', 'color': [.14, .36, .06, 1], 'roughness': .7},
        {'op': 'material.preset', 'ref': '@grass', 'name': 'Grass', 'color': [.2, .3, .1, 1], 'roughness': .9},
        *[{'op': 'material.assign_parts', 'target': t, 'material': m, 'part': p} for t, m, p in [
            ('@ground', '@grass', 'all'), ('@meadow', '@grass', 'all'),
            ('@hall', '@stone', 'walls'), ('@hall', '@glass', 'windows'), ('@hall', '@slate', 'roof'),
            ('@tower', '@stone', 'walls'), ('@tower', '@glass', 'windows'), ('@tower', '@slate', 'roof'),
            ('@oak', '@bark', 'trunk'), ('@oak', '@leaf', 'canopy'), ('@pine', '@bark', 'trunk'), ('@pine', '@leaf', 'canopy')]],
        {'op': 'geonodes.scatter', 'ref': '@grove', 'name': 'Meadow Grove', 'surface': '@meadow', 'instance': '@oak',
         'count': 12, 'seed': 7, 'scale_min': .6, 'scale_max': 1.1},
        {'op': 'mesh.deform', 'target': '@pine', 'kind': 'bend', 'axis': 'Z', 'amount': .12},
        *[{'op': 'object.parent', 'target': t, 'parent': '@ground'} for t in ('@hall', '@tower', '@pine', '@meadow', '@grove')],
        {'op': 'camera.configure', 'ref': '@cam', 'name': 'Village Camera', 'location': [24, -30, 16],
         'look_at': [0, 0, 2], 'lens': 35},
        {'op': 'light.rig', 'ref': '@sun', 'name': 'Village Light', 'style': 'soft_key', 'target': [0, 0, 0],
         'distance': 40, 'energy': 20000, 'color': [1, .95, .88]},
        {'op': 'render.configure', 'engine': 'EEVEE', 'frame_start': 1, 'frame_end': 1, 'fps': 24,
         'transparent': False, 'world_color': [.45, .6, .8], 'world_strength': .8, 'view_transform': 'AgX'},
        {'op': 'preview.render', 'path': 'village.png', 'width': 512, 'height': 320, 'samples': 16, 'frame': 1},
        {'op': 'asset.package', 'path': 'village.fvpkg', 'archetype': 'environment', 'subject': '@ground',
         'name': 'Village Block', 'clips': []}])


def humanoid_rigs():
    walk = [{'frame': f, 'bone': b, 'rotation': [sign*a, 0, 0]}
            for f, a in ((1, .45), (13, -.45), (25, .45)) for b, sign in (('leg_l', 1), ('leg_r', -1), ('arm_l', -1), ('arm_r', 1))]
    return plan('Fixture: human and synthetic rigs, skinning and retargeted walk', [
        {'op': 'scene.inspect'},
        {'op': 'character.humanoid', 'ref': '@elara', 'name': 'Human Study', 'height': 1.72, 'build': 'human'},
        {'op': 'armature.create', 'ref': '@rig', 'name': 'Human Rig', 'template': 'humanoid_basic', 'height': 1.72},
        {'op': 'material.preset', 'ref': '@cloth', 'name': 'Cloth', 'color': [.13, .4, .36, 1], 'roughness': .7},
        {'op': 'material.assign_parts', 'target': '@elara', 'material': '@cloth', 'part': 'all'},
        {'op': 'armature.skin', 'target': '@elara', 'armature': '@rig', 'method': 'automatic'},
        {'op': 'action.create', 'ref': '@walk', 'name': 'Human Walk', 'target': '@rig', 'kind': 'locomote',
         'locomotion': 'walk', 'loop': True, 'keys': walk},
        {'op': 'character.humanoid', 'ref': '@kai', 'name': 'Synthetic Study', 'height': 1.95, 'build': 'synthetic',
         'location': [1.5, 0, 0]},
        {'op': 'armature.create', 'ref': '@rig2', 'name': 'Synthetic Rig', 'template': 'synthetic_basic', 'height': 1.95,
         'location': [1.5, 0, 0]},
        {'op': 'material.assign_parts', 'target': '@kai', 'material': '@cloth', 'part': 'all'},
        {'op': 'armature.skin', 'target': '@kai', 'armature': '@rig2', 'method': 'envelope'},
        {'op': 'action.retarget', 'ref': '@walk2', 'name': 'Synthetic Walk', 'action': '@walk', 'source': '@rig',
         'target': '@rig2', 'bone_map': [['root', 'root'], ['leg_l', 'leg_l'], ['leg_r', 'leg_r'], ['arm_l', 'arm_l'],
                                         ['arm_r', 'arm_r']]},
        {'op': 'camera.configure', 'ref': '@cam', 'name': 'Rig Camera', 'location': [.75, -6, 1.2],
         'look_at': [.75, 0, .95], 'lens': 40},
        {'op': 'light.rig', 'ref': '@key', 'name': 'Rig Light', 'style': 'three_point', 'target': [.75, 0, 1],
         'distance': 5, 'energy': 800, 'color': [1, 1, 1]},
        {'op': 'render.configure', 'engine': 'EEVEE', 'frame_start': 1, 'frame_end': 25, 'fps': 24, 'transparent': True},
        {'op': 'preview.render', 'path': 'rigs.png', 'width': 384, 'height': 384, 'samples': 16, 'frame': 1},
        {'op': 'asset.package', 'path': 'human.fvpkg', 'archetype': 'humanoid', 'subject': '@elara',
         'name': 'Human Study', 'clips': ['@walk']}])
