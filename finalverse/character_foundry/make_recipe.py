"""Write finalverse.character-foundry.recipe/v1 for a CF build (stdlib only)."""
import glob, hashlib, json, os, sys, datetime
root, out = sys.argv[1], sys.argv[2]
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
mh=os.environ.get('CF_MH',os.path.expanduser('~/cf/mh')); build=os.path.dirname(os.path.abspath(__file__))
r={'schema_version':'finalverse.character-foundry.recipe/v1','recipe_id':'cf1-elara-vayne','recipe_version':1,
 'character':{'identity':'Elara','canon':'Core E1 finalverse.embodiment-spec/v1 (Elara, height_mm 1720)','vision_reference':'elara-vision.png (owner upload, 2026-11-07)',
  'asset_class':'humanoid_embodiment','embodiment':'biological_humanoid','design_brief':'CF1-ELARA-DESIGN.md'},
 'path':'A (CC0 professional base) + procedural garments/hair/lookdev; no AI-generated geometry',
 'tools':{'blender':'bpy 5.2.3 LTS (upstream PyPI wheel, sha256 8ef4a335930d647233c661ae21be1abf81207af33e1440fc5a4fc2f2f2d44db7)','renderer':'Cycles CPU + OIDN','numpy':True,'python':'3.13'},
 'source_assets':[{'file':os.path.basename(p),'sha256':sha(p),'license':'CC0-1.0','origin':'github.com/makehumancommunity/makehuman@master makehuman/data'} for p in sorted(glob.glob(mh+'/*')) if not p.endswith('.md')],
 'code':[{'file':os.path.basename(p),'sha256':sha(p)} for p in sorted(glob.glob(build+'/*.py'))+[build+'/elara_rig_map.json']],
 'operations':['body: hm08 + targets [caucasian-female-young 1.0, idealproportions 0.6, minweight 0.3], height 1.72 m, eyes +8%, lifted 14 mm for soles',
   'rig: MakeHuman default skeleton (163), CC0 weights, relaxed rest pose (arms 14 deg), 4 influences',
   'garments: tunic loft (96x49 rings), sleeves + rolled cuffs, leggings via body re-material, boots offset shell + sole + cuff + laces',
   'props: belt + buckle, crossbody strap, satchel + flap + buckle, wooden flute, flower clasp',
   'cloth: cloak 56x72 grid, Blender cloth (quality 8, mass 0.4, tension 15, bending 0.6), 80 frames, collisions body/tunic/sleeves/satchel/belt; hood derived from drape',
   'hair: scalp shell + 18 top + 13 crown + 12 nape locks + 4 temple strands; 3-strand braid 7.5 cycles over left shoulder; tie + tail',
   'lookdev: numpy-painted maps (skin 2048 BaseColor/Normal/ORM, tunic 2048, cloak 2048 + lining, leather/hair 1024 tiles, knit/wood 512, eye 512)',
   'skin: data-transfer from body + per-part rules (see elara_skin.py)',
   'animation: Elara_Idle 120f, Elara_Walk 32f in-place, Elara_Wave 90f @30fps; expressions smile/warm_smile/curious/blink from face pose units',
   'review fixes applied to the delivered .blend: patch_tunic_skin.py (tunic arm weights), patch_clips.py (frame-0 NLA leak); both now in the build code',
   'export: hero (textures capped 2048/1024/512), runtime (iterative decimate to <= 38k tris, textures 1024/512/256), proxy (single mesh, 7 factor materials)'],
 'seeds':{'tunic':21,'cloak':31,'leather':41,'hair':11,'skin':5},
 'outputs':[{'file':os.path.relpath(p,root),'sha256':sha(p),'bytes':os.path.getsize(p)} for p in sorted(glob.glob(root+'/*.glb'))+sorted(glob.glob(root+'/*.blend'))+sorted(glob.glob(root+'/textures/*.png'))],
 'validation':[os.path.basename(p) for p in sorted(glob.glob(root+'/glb-check-*.json'))],
 'evidence':[os.path.relpath(p,root) for p in sorted(glob.glob(root+'/renders/*.png'))],
 'approval':{'status':'candidate','required':['all glb checks pass','independent artistic review (not the generating agent)','Infinity Gate B capture'],
   'reviews':[],'publication':'blocked: hero replacement needs owner visual approval before catalogue admission'},
 'created':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),'author':'Claude (Character Foundry CF1 thread)'}
json.dump(r,open(out,'w'),indent=2); print('recipe',len(r['outputs']),'outputs')
