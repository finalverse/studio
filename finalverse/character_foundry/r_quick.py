import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import bpy, cf_render as R
blend, out = sys.argv[sys.argv.index('--')+1:][:2]
views = sys.argv[sys.argv.index('--')+3:] or ['front']
bpy.ops.wm.open_mainfile(filepath=blend)
sc=bpy.context.scene
R.setup(sc,res=(640,960),samples=24)
R.rig_neutral(sc)
for v in views:
    if v=='face':
        sc.render.resolution_x,sc.render.resolution_y=800,800
        R.camera(sc,15,(0,0,1.60),0.75,lens=85)
    elif v=='bust':
        sc.render.resolution_x,sc.render.resolution_y=900,900
        R.camera(sc,30,(0.02,0,1.45),1.6,lens=70)
    elif v=='bustrear':
        sc.render.resolution_x,sc.render.resolution_y=900,900
        R.camera(sc,200,(0.0,0,1.45),1.6,lens=70)
    elif v=='faceside':
        sc.render.resolution_x,sc.render.resolution_y=800,800
        R.camera(sc,90,(0,0.02,1.60),0.75,lens=85)
    else:
        sc.render.resolution_x,sc.render.resolution_y=640,960
        R.camera(sc,R.VIEWS[v],(0,0,0.88),5.2,lens=50,height=1.0)
    R.render(sc,f'{out}_{v}.png')
