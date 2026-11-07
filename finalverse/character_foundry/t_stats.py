import bpy, json, numpy as np
bpy.ops.wm.open_mainfile(filepath=__import__('sys').argv[__import__('sys').argv.index('--')+1] if '--' in __import__('sys').argv else 'elara_cf1.blend')
dg=bpy.context.evaluated_depsgraph_get(); rows=[]; tot=0
groups={}
for o in bpy.context.scene.objects:
    if o.type!='MESH': continue
    m=o.evaluated_get(dg).to_mesh(); m.calc_loop_triangles(); n=len(m.loop_triangles); o.evaluated_get(dg).to_mesh_clear()
    k=o.name.split('.')[0].replace('Elara_','')
    for pre in ('HairLock','HairStrand','BraidTail','Braid','Lace','FlowerPetal','FluteHole','FluteRing'):
        if k.startswith(pre): k=pre; break
    groups[k]=groups.get(k,0)+n; tot+=n
mats=sorted({s.material.name for o in bpy.context.scene.objects if o.type=='MESH' for s in o.material_slots if s.material})
imgs=[(i.name,i.size[0]) for i in bpy.data.images if i.name.startswith('T_')]
print('STATS',json.dumps({'objects':sum(1 for o in bpy.context.scene.objects if o.type=='MESH'),'triangles':tot,'by_part':dict(sorted(groups.items(),key=lambda x:-x[1])),'materials':mats,'textures':imgs,'bones':len(bpy.data.objects['Elara_Rig'].data.bones),'actions':[a.name for a in bpy.data.actions]}))
