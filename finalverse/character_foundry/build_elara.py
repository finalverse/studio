import sys, os, time; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import bpy, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import cf_geo as G
bpy.ops.wm.read_factory_settings(use_empty=True)
sc=bpy.context.scene
import elara_body as EB, elara_garments as EG, elara_props as EP, elara_cloak as EC, elara_hair as EH
T0=time.time(); log=lambda *a: print(f'[{time.time()-T0:6.1f}s]',*a, flush=True)
mh,rig,body=EB.build_body(sc)
M={k:G.material(k,c,r,m) for k,c,r,m in [('Skin',(0.8,0.55,0.42),0.45,0),('Leggings',(0.16,0.10,0.05),0.8,0),('Tunic',(0.10,0.25,0.08),0.85,0),
  ('Leather',(0.25,0.12,0.05),0.6,0),('LeatherDark',(0.12,0.06,0.03),0.55,0),('Brass',(0.8,0.6,0.3),0.35,1),('Wood',(0.35,0.2,0.09),0.5,0),
  ('Cloak',(0.06,0.13,0.25),0.9,0),('CloakLining',(0.03,0.05,0.12),0.85,0),('CloakTrim',(0.6,0.45,0.15),0.6,0),('Hair',(0.35,0.10,0.04),0.5,0),('Flower',(0.9,0.35,0.08),0.5,0)]}
body.data.materials.append(M['Skin']); body.data.materials.append(M['Leggings'])
bi=EG.BodyInfo(body,rig)
def mat(o,k): o.data.materials.append(M[k]); return o
tun=mat(EG.tunic(bi),'Tunic')
garm=[tun]
for s in 'LR':
    sl,cu=EG.sleeve(bi,s); mat(sl,'Tunic'); mat(cu,'Tunic'); garm+= [sl,cu]
EG.leggings(bi,1)
for o in EG.boots(bi): mat(o,'Leather')
log('tunic/boots')
tb=G.bvh_of(tun)
b,bk,tg=EP.belt(bi,tb); mat(b,'Leather'); mat(bk,'Brass'); mat(tg,'Leather')
# strap rides on tunic+belt
surf=BVHTree.FromObject(G.join([G.evaluated_copy(o) for o in [tun,b]],'tmp_surf'), bpy.context.evaluated_depsgraph_get())
bpy.data.objects.remove(bpy.data.objects['tmp_surf'])
straps,hip=EP.strap(bi,surf)
for o in straps: mat(o,'Leather')
sat,c,Rm=EP.satchel(hip,bi)
mat(sat[0],'Leather'); mat(sat[1],'Leather'); mat(sat[2],'LeatherDark'); mat(sat[3],'Brass')
fl=EP.flute(c,Rm)
for o in fl: mat(o,'Wood')
log('props')
# cloak sim
cols=[body,tun]+garm[1:]+[sat[0],b]
for o in cols: EC.add_collision(o)
cloak=EC.build_cloak_rest(bi)
cb=G.join([G.evaluated_copy(o) for o in cols],'tmp_c'); cbvh=BVHTree.FromObject(cb,bpy.context.evaluated_depsgraph_get()); bpy.data.objects.remove(cb)
EC.push_out(cloak,cbvh,0.014)
cloak=EC.simulate(cloak,frames=int(os.environ.get('CF_FRAMES','60')))
log('cloak draped')
hood=EC.hood_from_cloak(cloak,56,72)
for o in cols:
    m=o.modifiers.get('Collision')
    if m: o.modifiers.remove(m)
EC.finish(cloak,mats=[M['Cloak'],M['CloakLining'],M['CloakTrim']])
EC.finish(hood,mats=[M['Cloak'],M['CloakLining'],M['CloakTrim']])
gb=G.join([G.evaluated_copy(o) for o in [tun,cloak,hood]+straps],'tmp_g')
gbvh=BVHTree.FromObject(gb,bpy.context.evaluated_depsgraph_get()); bpy.data.objects.remove(gb)
hair,braid_path=EH.build_hair(bi,gbvh)
for o in hair: mat(o,'Hair')
log('hair')
# clasp flower on her left collarbone, on the cloak edge
p=np.array([0.075,bi.bone('neck01')[1]-0.085,bi.bone('neck01')[2]-0.075])
for o in EP.flower(p,(0.25,-1,0.15)): mat(o,'Flower')
import elara_face as EF, elara_lookdev as LD
eyes=EF.eyes(mh,sc); lashes=EF.lashes(mh,sc,eyes)
for o in lashes: mat(o,'Lashes') if 'Lashes' in M else None
# UVs for meshes without them
for o in list(sc.objects):
    if o.type=='MESH' and not o.data.uv_layers and o.name.startswith('Elara'):
        G.uv_smart(o)
ec={1:np.array(eyes[1]['cf.eye_center']) if eyes[1].name.endswith('L') else np.array(eyes[0]['cf.eye_center'])}
eL=[e for e in eyes if e.name.endswith('.L')][0]; eR=[e for e in eyes if e.name.endswith('.R')][0]
mouth=mh.joint('joint-mouth')
co=bi.co; ez=eL['cf.eye_center'][2]
cand=co[(np.abs(co[:,0])<0.006)&(co[:,2]<ez-0.01)&(co[:,2]>ez-0.055)]
nose=cand[np.argmin(cand[:,1])]
mouth=np.array([0.0, nose[1]+0.017, nose[2]-0.0345])  # lip seam: measured on the hm08 midline profile
lm={'eye':{1:np.array(eL['cf.eye_center']),-1:np.array(eR['cf.eye_center'])},'mouth':mouth,'nose':nose,
    'chin_z':mouth[2]-0.05,'brow_z':ez+0.02,'ear_y':bi.bone('head')[1]+0.005}
print('landmarks',{k:(v if not isinstance(v,dict) else {kk:list(np.round(vv,3)) for kk,vv in v.items()}) for k,v in lm.items()})
LM=LD.build_materials(lm,body,eyes)
for o in sc.objects:
    if o.type!='MESH': continue
    if o.name.startswith('Elara_Eye'):
        o.data.materials.clear(); o.data.materials.append(LM[o.name]); continue
    if o.name.startswith('Elara_Lashes'):
        o.data.materials.clear(); o.data.materials.append(LM['Lashes']); continue
    if o.name.startswith('Elara_HairCap'):
        o.data.materials.clear(); o.data.materials.append(LM['HairCap']); continue
    for i,slot in enumerate(o.material_slots):
        if slot.material and slot.material.name in LM:
            o.data.materials[i]=LM[slot.material.name]
for k,m in list(M.items()):
    if m.users==0: bpy.data.materials.remove(m)
import elara_skin as ES, elara_anim as EA, json
rep=ES.skin_all(sc,body,rig,braid_path)
log('skinned',len(rep))
clips,units=EA.build_library(rig)
bpy.context.scene.render.fps=EA.FPS; bpy.context.scene.render.fps_base=1.0
rig['cf.clips']=json.dumps(clips)
log('anim',clips)
log('done')
bpy.ops.wm.save_as_mainfile(filepath=os.environ.get('CF_OUT',os.path.expanduser('~/cf/work/elara_wip.blend')))
