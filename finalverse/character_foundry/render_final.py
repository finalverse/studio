import sys, os; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import bpy, cf_render as R, elara_anim as EA
args=sys.argv[sys.argv.index('--')+1:]
blend, out, mode = args[0], args[1], args[2]
S=int(os.environ.get('CF_SAMPLES','64'))
bpy.ops.wm.open_mainfile(filepath=blend)
sc=bpy.context.scene
rig=bpy.data.objects.get('Elara_Rig')
if rig and rig.animation_data:
    rig.animation_data.action=None
    for t in rig.animation_data.nla_tracks: t.mute=True
R.setup(sc,res=(1024,1536),samples=S)
expr=os.environ.get('CF_EXPR')
if rig and expr:
    EA.pose_expression(rig, EA.load_poseunits(), expr)
(R.rig_neutral if mode=='neutral' else R.rig_production)(sc)
views=args[3:]
for v in views:
    if v.startswith('face'):
        sc.render.resolution_x,sc.render.resolution_y=1024,1024
        yaw={'face':0,'face3':28}[v]
        R.camera(sc,yaw,(0,-0.03,1.605),0.85,lens=90)
    elif v=='bust':
        sc.render.resolution_x,sc.render.resolution_y=1024,1024
        R.camera(sc,30,(0.02,0,1.40),1.9,lens=70)
    else:
        sc.render.resolution_x,sc.render.resolution_y=1024,1536
        R.camera(sc,R.VIEWS[v],(0,0,0.89),5.4,lens=75,height=1.0)
    R.render(sc,f'{out}_{mode}_{v}.png')
