"""Re-skin the tunic in an existing CF1 .blend with the current elara_skin rules
(same steps as build_elara's skinning stage, without rebuilding the cloth)."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import bpy, cf_rig as RG, elara_skin as ES
import numpy as np
blend = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.open_mainfile(filepath=blend)
sc = bpy.context.scene; rig = bpy.data.objects['Elara_Rig']; body = bpy.data.objects['Elara_Body']
rig.data.pose_position = 'REST'
for ob in [o for o in sc.objects if o.name.startswith('Elara_Tunic') and o.type == 'MESH']:
    for vg in list(ob.vertex_groups):
        ob.vertex_groups.remove(vg)
    RG.transfer_weights(body, ob)
    z0 = rig.data.bones['upperleg01.L'].tail_local.z
    ES._scale_groups(ob, ES.LEGS, lambda co: np.clip((z0 - co[:, 2]) / 0.12, 0, 1) * 0.55, 'spine05')
    ES.tunic_arm_rule(ob, rig)
    RG.smooth_weights(ob, 4)
    RG.normalize_weights(ob, 4)
    RG.bind(ob, rig)
    print('PATCHED', ob.name, len(ob.vertex_groups))
rig.data.pose_position = 'POSE'
bpy.ops.wm.save_mainfile()
