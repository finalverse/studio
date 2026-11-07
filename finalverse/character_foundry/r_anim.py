import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import bpy, cf_render as R
args=sys.argv[sys.argv.index('--')+1:]
blend,out=args[:2]; specs=args[2:]   # action:frame:view
bpy.ops.wm.open_mainfile(filepath=blend)
sc=bpy.context.scene; rig=bpy.data.objects['Elara_Rig']
R.setup(sc,res=(560,840),samples=20); R.rig_neutral(sc)
for tr in rig.animation_data.nla_tracks: tr.mute=True
for sp in specs:
    a,f,v=sp.split(':')
    for pb in rig.pose.bones:   # unkeyed channels must not inherit the previous clip's pose
        pb.location=(0,0,0); pb.rotation_quaternion=(1,0,0,0); pb.rotation_euler=(0,0,0); pb.scale=(1,1,1)
    rig.animation_data.action=bpy.data.actions[a]
    sc.frame_set(int(f))
    if v=='face3':
        sc.render.resolution_x,sc.render.resolution_y=600,600
        R.camera(sc,25,(0,-0.02,1.60),0.75,lens=85)
    elif v=='face':
        sc.render.resolution_x,sc.render.resolution_y=600,600
        R.camera(sc,10,(0,-0.02,1.60),0.75,lens=85)
    else:
        sc.render.resolution_x,sc.render.resolution_y=560,840
        R.camera(sc,R.VIEWS[v],(0,0,0.9),5.0,lens=50,height=1.0)
    R.render(sc,f'{out}_{a}_{f}_{v}.png')
