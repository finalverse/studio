"""Identical-camera, identical-light render of the V1 Elara asset (before)."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import bpy, os, cf_render as R
args=sys.argv[sys.argv.index('--')+1:]
glb,out,mode=args[:3]; views=args[3:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
sc=bpy.context.scene
for o in sc.objects:
    if o.animation_data: o.animation_data.action=None
R.setup(sc,res=(1024,1536),samples=int(os.environ.get('CF_SAMPLES','64')))
(R.rig_neutral if mode=='neutral' else R.rig_production)(sc)
for v in views:
    if v.startswith('face'):
        sc.render.resolution_x,sc.render.resolution_y=1024,1024
        R.camera(sc,{'face':0,'face3':28}[v],(0,-0.03,1.605),0.85,lens=90)
    else:
        sc.render.resolution_x,sc.render.resolution_y=1024,1536
        R.camera(sc,R.VIEWS[v],(0,0,0.89),5.4,lens=75,height=1.0)
    R.render(sc,f'{out}_{mode}_{v}.png')
