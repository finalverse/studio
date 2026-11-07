"""Re-author the CF1 clips in an existing .blend with the current elara_anim code."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import bpy, elara_anim as EA
blend = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.open_mainfile(filepath=blend)
rig = bpy.data.objects['Elara_Rig']
ad = rig.animation_data
ad.action = None
for tr in list(ad.nla_tracks):
    ad.nla_tracks.remove(tr)
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
sc = bpy.context.scene; sc.frame_set(0)
clips, units = EA.build_library(rig)
sc.render.fps = EA.FPS; sc.render.fps_base = 1.0
print('CLIPS', [(c['name'], c['frames']) for c in clips])
bpy.ops.wm.save_mainfile()
