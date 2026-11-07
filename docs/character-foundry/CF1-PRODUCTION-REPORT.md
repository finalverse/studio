# CF1: Elara Vayne production report

Status: **candidate**. All Gate A technical checks pass and all three GLB profiles
validate. The artistic items and Gate B (Infinity) are open. Elara is **not**
declared Q3 or Q4. See [CF1-ACCEPTANCE](CF1-ACCEPTANCE.md).

## 1. How to rebuild

```
python finalverse/character_foundry/build_elara.py            # ~85 s on 4 vCPU → elara_cf1.blend
python finalverse/character_foundry/elara_export.py -- elara_cf1.blend OUT   # hero, runtime, proxy GLBs
python finalverse/character_foundry/glb_validate.py OUT/elara_cf1_runtime.glb --profile runtime
python finalverse/character_foundry/render_final.py -- elara_cf1.blend OUT/renders/elara neutral front three_quarter side rear face
python finalverse/character_foundry/make_recipe.py OUT OUT/recipe.json
```

Environment: upstream `bpy` 5.2.3 (PyPI wheel) and numpy. MakeHuman CC0 data is
fetched once from `makehumancommunity/makehuman@master` and checked against the
digests in `recipe.json`. The build is deterministic (fixed seeds), apart from
cloth-solver float noise.

## 2. What was built

| Stage | Method | Result |
| --- | --- | --- |
| Body | MakeHuman hm08 (CC0) + targets: caucasian-female-young 1.0, idealproportions 0.6, minweight 0.3. Scaled to 1.72 m. Eyes +8%. | 21,988 tris, quad topology designed for deformation, full UVs |
| Rig | MakeHuman default skeleton, 163 bones incl. face. CC0 weights. Relaxed rest pose (arms 14°) applied as rest. | one armature `Elara_Rig` |
| Tunic and sleeves | Rings lofted from 2D hulls of body slices, with ease, A-line flare and fold modulation. Rolled cuffs. | 9,216 + 3,200 + 160 tris |
| Leggings | Body leg faces re-materialed with a knit texture (no separate shell, so no clipping). | in body |
| Boots | Offset shell of the shin and foot, relaxed. Hull-filled toe box, sole, folded cuff, criss-cross laces. Skin inside the boots deleted. | 4,880 + 760 + 768 + 768 tris |
| Belt, strap, satchel, flute, flower clasp | Parallel-transport sweeps, raycast onto the tunic. | ~5,600 tris |
| Cloak | 56×72 grid pinned at the neckline, draped by the Blender cloth solver over the body, tunic, sleeves, satchel and belt (80 frames). Solidify 4.5 mm with lining and rim materials. | 16,124 tris |
| Hood | Derived from the draped cloak back (puffed along grid normals), lying folded on the upper back. | 4,604 tris |
| Hair | Scalp shell, 47 swept locks (top, crown, nape, temple strands), 3-strand braid over the left shoulder with tie and tail. | 30,736 tris |
| Face | MakeHuman high-poly eyes fitted to the eye helpers, painted hazel-green iris with limbal ring, clearcoat cornea. Ribbon lashes. Painted brows, lips, blush, freckles. | |
| Look dev | Every map painted in UV space by a numpy rasteriser over per-texel 3D positions: skin, tunic with gold music-staff and vine embroidery, cloak with gold leaf border and lining frieze, leather, hair, knit, wood. Principled BSDF: BaseColor + Normal + ORM, skin subsurface, cloak and tunic sheen. | 16 materials, 22 maps |
| Skinning | Data transfer from the body, then per-part rules (tunic legs → pelvis, cloak legs → spine, rigid hair/eyes/props, braid chain). Smoothed, 4 influences, normalised. | 128 skinned parts |
| Animation | Analytic FK on the rest axes with a per-frame foot ground solve. Face expressions from the MakeHuman CC0 face pose units. | `Elara_Idle` 4.0 s loop, `Elara_Walk` 1.067 s loop (1.25 m/s), `Elara_Wave` 3.0 s |

## 3. Numbers

| | Hero GLB | Runtime GLB | Proxy GLB | V1 Elara (before) |
| --- | --- | --- | --- | --- |
| Triangles | 100,980 | 37,442 | 20,256 | 24,086 |
| Materials | 16 | 16 | 7 | 10 |
| Textures | 22 (four 2048², rest ≤ 1024²) | 22 (four 1024², rest ≤ 512²) | 0 | 0 |
| GPU texture memory (RGBA8 + mips) | 149.3 MiB | 41.3 MiB | 0 | 0 |
| Skeleton | 163 joints, one skin | 163 joints, one skin | none | 6 rigid joints |
| Clips | 3 (idle, walk, wave) | 3 | none | 4 rigid-joint review clips |
| File size | 9.5 MB | 3.9 MB | 0.4 MB | 0.7 MB |
| Validator | pass | pass | pass | n/a |

Editable source: `elara_cf1.blend` (~45 MB, textures packed). It is kept in
project storage with its digest in `recipe.json`, not in git.

## 4. Validation (glb_validate.py)

All checks pass for the hero, runtime and proxy profiles: buffer bounds, Y-up
height (1.767 m to the top of the hair; the body is 1.72 m plus 14 mm soles),
ground contact (min Y = 0), centring, triangle budget, opaque materials,
JPEG/PNG only, texture size cap, texture memory, PBR channels present, one skin,
inverse bind matrices, 163-joint structure, weights normalised (max error
0.0000), ≤ 4 influences, joint indices in range, every mesh node skinned, clips
finite and monotonic, the three required clips present. Reports:
`glb-check-hero.json`, `glb-check-runtime.json`, `glb-check-proxy.json`.

Two export defects were caught and fixed by the validator during this run: the
scene ran at 24 fps, which stretched every clip by 25 %, and the first runtime
pass was 43,175 triangles and 93 MiB of textures. The exporter now sets 30 fps,
iterates the decimation to the budget and caps textures per profile.

The motion review then caught two rig defects, both fixed in code and in the
delivered `.blend`:

- **Tunic dragged by the arm.** Nearest-surface weight transfer gave the tunic
  flanks forearm and hand weights, so the raised arm in `Elara_Wave` pulled the
  side panel up into a green tube. `elara_skin.tunic_arm_rule` now moves
  forearm and hand weights to the chest and fades upper-arm weights out below
  the armpit (the sleeves are separate objects).
- **Frame 0 of each clip held the previous clip's pose.** The first depsgraph
  update in a clip's frame loop re-evaluated the earlier NLA tracks, so
  `Elara_Walk` frame 0 held an idle pose (a pop at the loop seam) and
  `Elara_Wave` frame 0 a walk pose. `elara_anim._new_action` now mutes earlier
  tracks and flushes the depsgraph before keying. The walk now loops exactly
  (frame 0 = frame 32).

The delivered `.blend` was patched with `patch_tunic_skin.py` and
`patch_clips.py` (re-running exactly those two stages) rather than rebuilt, to
keep the reviewed cloth drape. A clean `build_elara.py` run now produces the
same result, apart from cloth-solver noise.

A round trip (the runtime GLB re-imported into a clean scene and rendered with
the same camera) is in `renders/runtime_glb_neutral_front.png`. The decimated
asset holds its look.

## 5. Known weaknesses (honest list)

1. **Hair** reads somewhat like a sculpted helmet. The front edge is hard, a
   dark notch shows at the centre part, and the temple strands separate from the
   head in the three-quarter close-up.
2. **Face appeal.** The face is realistic and neutral. The vision art is
   painterly and warmer. Under the production (AgX) rig the skin washes out
   pale, and the `warm_smile` expression is too subtle to read at bust framing.
3. **Cloak shoulders** are slightly bulky, and the cloak is not simulated at
   runtime, so the hem can clip the trailing calf in the walk.
4. **Leggings knit** reads as a fine mesh at 512² in the runtime profile.
5. **Walk** is analytic, not mocap: correct contact and timing, little weight.
6. **No sculpted secondary detail.** Folds and seams come from normal maps.

Items 1 and 2 are the highest-value polish for CF1.1. Items 5 and 6 need the
capabilities listed in [CF0-TOOLCHAIN-EVALUATION](CF0-TOOLCHAIN-EVALUATION.md).

## 6. Provenance

Only CC0 MakeHuman assets and original CF code and textures. No commercial,
copyrighted or AI-generated geometry. Full digests in `recipe.json`
(`finalverse.character-foundry.recipe/v1`, `approval.status: candidate`).
