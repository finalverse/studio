"""CF1 Elara: skinning of every garment/accessory to the MakeHuman default rig."""
import numpy as np

import bpy

import cf_rig as RG

LEGS = ('upperleg', 'lowerleg', 'foot', 'toe')


def _scale_groups(ob, prefixes, factor, into):
    A = RG.weights_array(ob)
    names = [vg.name for vg in ob.vertex_groups]
    if into not in names:
        ob.vertex_groups.new(name=into); names.append(into)
        A = np.concatenate([A, np.zeros((len(A), 1), np.float32)], 1)
    ti = names.index(into)
    co = np.array([v.co[:] for v in ob.data.vertices])
    for i, n in enumerate(names):
        if n.startswith(prefixes):
            f = factor(co) if callable(factor) else factor
            moved = A[:, i] * (1 - f)
            A[:, i] -= moved; A[:, ti] += moved
    RG.set_weights_array(ob, A)


def skin_all(scene, body, rig, braid_path=None):
    report = {}
    for ob in list(scene.objects):
        if ob.type != 'MESH' or ob is body or not ob.name.startswith('Elara_'):
            continue
        n = ob.name
        for vg in list(ob.vertex_groups):
            ob.vertex_groups.remove(vg)
        if n.startswith(('Elara_Hair', 'Elara_HairCap', 'Elara_HairLock', 'Elara_HairStrand')):
            RG.rigid_bind(ob, rig, 'head'); report[n] = 'rigid:head'; continue
        if n.startswith('Elara_Lashes.'):
            RG.rigid_bind(ob, rig, 'orbicularis03.' + n[-1]); report[n] = 'rigid:upper-lid'; continue
        if n.startswith('Elara_Eye.'):
            RG.rigid_bind(ob, rig, 'eye.' + n[-1]); report[n] = 'rigid:eye'; continue
        if n.startswith(('Elara_Braid', 'Elara_BraidTie', 'Elara_BraidTail')):
            braid_weights(ob, rig, braid_path); report[n] = 'braid-chain'; continue
        if n.startswith(('Elara_Satchel', 'Elara_Flute')):
            RG.rigid_bind(ob, rig, 'spine05'); report[n] = 'rigid:spine05'; continue
        if n.startswith('Elara_Flower'):
            RG.rigid_bind(ob, rig, 'spine01'); report[n] = 'rigid:spine01'; continue
        RG.transfer_weights(body, ob)
        if n.startswith('Elara_Tunic'):
            # skirt below the hips follows the pelvis more than the thighs
            z0 = rig.data.bones['upperleg01.L'].tail_local.z
            _scale_groups(ob, LEGS, lambda co: np.clip((z0 - co[:, 2]) / 0.12, 0, 1) * 0.55, 'spine05')
            tunic_arm_rule(ob, rig)
            RG.smooth_weights(ob, 4)
        elif n.startswith(('Elara_Cloak', 'Elara_Hood')):
            _scale_groups(ob, LEGS, 0.75, 'spine05')
            _scale_groups(ob, ('upperarm', 'lowerarm', 'wrist', 'finger', 'metacarpal'), 0.7, 'spine01')
            RG.smooth_weights(ob, 12)
        elif n.startswith(('Elara_Strap', 'Elara_Belt', 'Elara_Buckle')):
            _scale_groups(ob, ('upperarm', 'lowerarm'), 0.9, 'spine01')
            RG.smooth_weights(ob, 6)
        else:
            RG.smooth_weights(ob, 2)
        RG.normalize_weights(ob, 4)
        RG.bind(ob, rig)
        report[n] = 'transfer'
    return report


ARM_LOW = ('lowerarm', 'wrist', 'finger', 'metacarpal')


def tunic_arm_rule(ob, rig):
    """The tunic body hangs beside the arms, so nearest-surface transfer gives its
    flanks forearm and hand weights, and a raised arm drags the side panel up
    (seen in the CF1 wave review). The sleeves are separate objects, so the tunic
    keeps arm influence only around the armhole: forearm/hand weights go to the
    chest, and upper-arm weights fade out below the armpit."""
    _scale_groups(ob, ARM_LOW, 0.0, 'spine03')
    za = min(rig.data.bones[f'upperarm01.{s}'].head_local.z for s in 'LR') - 0.03
    _scale_groups(ob, ('upperarm', 'shoulder'), lambda co: np.clip((co[:, 2] - (za - 0.07)) / 0.07, 0, 1), 'spine03')


def braid_weights(ob, rig, path):
    co = np.array([v.co[:] for v in ob.data.vertices])
    if path is None:
        RG.rigid_bind(ob, rig, 'head'); return
    d = np.linalg.norm(co[:, None, :] - path[None, ::4, :], axis=2)
    s = np.argmin(d, axis=1) * 4 / (len(path) - 1)       # 0 root .. 1 tip
    chain = [('head', 0.0), ('neck03', 0.18), ('neck01', 0.30), ('spine01', 0.45), ('spine02', 1.0)]
    for name, _ in chain:
        ob.vertex_groups.new(name=name)
    for i, si in enumerate(s):
        for (a, sa), (b, sb) in zip(chain, chain[1:]):
            if sa <= si <= sb:
                f = (si - sa) / max(sb - sa, 1e-6)
                ob.vertex_groups[a].add([i], 1 - f, 'REPLACE')
                ob.vertex_groups[b].add([i], f, 'REPLACE')
                break
        else:
            ob.vertex_groups['spine02'].add([i], 1.0, 'REPLACE')
    RG.bind(ob, rig)
