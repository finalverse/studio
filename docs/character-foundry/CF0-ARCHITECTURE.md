# CF0: Finalverse Character Foundry architecture

The Character Foundry (FCF) turns a canonical character specification into an
animation-ready, visually consistent 3D character. It replaces "assemble the
character from primitives" (E1/V1 founders) with the disciplines a character
team actually uses: base mesh, garments, hair, look development, rigging,
animation, evidence and review. Every step is a deterministic script running
in headless Blender, so an AI agent can drive it and a reviewer can reproduce
it.

CF1 (Elara Vayne) is the first character through the pipeline. Its code lives
in `finalverse/character_foundry/` on the Studio repository.

## 1. Pipeline

```
CHARACTER CANON (Core E1 spec: name, height_mm, palette)    + vision art (canonical reference)
      │
      ▼
DESIGN BRIEF  (CF1-ELARA-DESIGN.md: silhouette, layers, palette, motifs, do/don't)
      │
      ▼
BASE MESH SELECTION ─── human ──────► MakeHuman hm08 (CC0) + CC0 targets
      │                 synthetic ───► human base + hard-surface shell (Kai, planned CF2)
      │                 non-humanoid ► archetype base (Lumi/Terra/Ignis/Melody, planned)
      ▼
BODY            targets → height fit → light stylisation → authoring rest pose
RIG             MakeHuman default skeleton (163 bones incl. face), CC0 skin weights
GARMENTS        cross-section lofts (tunic, sleeves), body re-material (leggings),
                offset shells (boots), sweeps (belt, straps), props (satchel, flute)
CLOTH           Blender cloth solver drapes the cloak; hood follows the draped cloak
HAIR            sculpted lock clumps over a scalp shell, true 3-strand braid
LOOKDEV         numpy-painted BaseColor / Normal / ORM maps (3D-space for skin and eyes,
                UV-space for fabric, embroidery, leather, hair) + Principled materials
SKINNING        weight transfer from the body + per-garment rules (skirt→pelvis,
                cloak→spine, hair→head, braid chain, lashes→lid bones)
ANIMATION       analytic FK clips with per-frame ground solve; CC0 face pose units
                for expressions and blinks
EVIDENCE        Cycles turnarounds under two lighting rigs, facial close-ups, motion
                frames, identical-camera before/after
EXPORT          hero GLB · runtime GLB (budgeted) · static proxy GLB (Genesis subset)
VALIDATION      glb_validate.py (coordinate system, hierarchy, channels, textures,
                skeleton, weights, clips, integrity)
RECIPE          finalverse.character-foundry.recipe/v1 (inputs, tools, digests, approval)
      │
      ▼
ASSET INTELLIGENCE (S3-A, GC3 quality gates)  →  VISUAL EVALUATION (GC4 render evidence)
      │
      ▼
HUMAN ART REVIEW (mandatory for hero characters)  →  RUNTIME EXPORT  →  INFINITY (Codex)
```

## 2. Module layout (`finalverse/character_foundry/`)

| Module | Discipline | Notes |
| --- | --- | --- |
| `cf_mh.py` | base mesh | Reads hm08 OBJ, targets, `default.mhskel`, `default_weights.mhw`. Converts MH Y-up decimetres to Blender Z-up metres. Uses CC0 data only, no AGPL MakeHuman code. |
| `cf_rig.py` | rigging | World-axis posing, apply-pose-as-rest, weight transfer, smoothing, 4-influence normalisation. |
| `cf_geo.py` | modelling | 2D hulls, ring lofts with UVs, parallel-transport sweeps, BVH helpers, Laplacian relax. |
| `cf_tex.py` | texturing | UV-space rasteriser (per-texel 3D position and normal), noise, normal-from-height, image I/O. |
| `cf_render.py` | look dev / evidence | Neutral rig (Khronos PBR Neutral, Infinity's tone mapper) and production rig (AgX). |
| `elara_*.py` | CF1 character | body, garments, props, cloak, hair, face, lookdev, skin, anim. |
| `build_elara.py` | orchestration | One command builds the editable `.blend` from nothing. |
| `elara_export.py` | export | hero, runtime and proxy GLBs. |
| `glb_validate.py` | validation | Runtime-side checks (no Blender). |
| `render_final.py`, `r_anim.py`, `render_compare.py` | evidence | Turnarounds, motion frames, identical-camera comparison. |

Each character gets its own `<name>_*.py` stage modules on top of the shared
`cf_*` libraries. The libraries are character-agnostic. Auren reuses
`elara_body`/`elara_skin`/`elara_anim` almost unchanged (different targets,
garments and hair).

## 3. Two creation paths, one contract

**Path A, professional source assets.** Licensed base meshes, rigs, garments
and animation. CF1 uses MakeHuman's CC0 hm08 mesh, skeleton, weights and face
pose units. Any future source must pass the licence audit in
[CF0-TOOLCHAIN-EVALUATION](CF0-TOOLCHAIN-EVALUATION.md) and be recorded in the
recipe with its digest.

**Path B, AI-generated originals.** A model proposes design parameters
(palette, garment cut, hair flow, motif), or edits the stage scripts. It never
writes geometry directly into the catalogue. Proposals run through the same
build, the same validators and the same human review.

Both paths converge on the **character asset contract**:

| Artifact | Contract |
| --- | --- |
| `elara_cf1.blend` | editable source: every object named `Elara_*`, procedural materials, painted textures packed, rig with NLA clips |
| `elara_cf1.glb` | hero profile: skinned (one skin), ≤ 4 influences, BaseColor/Normal/ORM, clips `Elara_Idle`, `Elara_Walk`, `Elara_Wave` |
| `elara_cf1_runtime.glb` | runtime profile: ≤ 40,000 triangles, textures ≤ 1024², same skeleton and clips |
| `elara_cf1_proxy.glb` | Genesis static subset: one node, one mesh, ≤ 8 factor-only materials |
| `textures/*.png` | lossless masters |
| `recipe.json` | `finalverse.character-foundry.recipe/v1` |
| `glb-check-*.json` | validator reports |
| `renders/` | evidence |

## 4. Integration points

- **Core E1 canon.** The design brief starts from the E1 specification
  (`height_mm` 1720, palette fields) and the vision art. The E1 identity stays
  `Elara`. CF does not create identities. A replacement body enters only
  through `admit_studio_package` after review.
- **Genesis Cloud GC3.** Class `humanoid_embodiment`. The proxy GLB is the GC
  static import subset. Rig mapping to `finalverse.humanoid/v1` (26 joints) is
  published in `elara_rig_map.json`.
- **GC4 visual evolution.** CF renders use the GC4 view names (`front`, `side`,
  `rear`, `three_quarter`, `close_up`) and the lighting names (`neutral`,
  `production`). A hero candidate can be attached as a `studio.render/1`
  evidence source. GC4 already makes human approval mandatory
  (`require_human_approval: false` → 422). CF keeps that rule.
- **S3-A Asset Intelligence.** `glb_validate.py` reports are shaped to be
  ingested as runtime-compatibility evidence. S3-A lives only on the Studio
  branch `s3a/asset-intelligence` (281dbe1), not on main. Wiring the CF report
  into S3-A is a CF2 task.
- **Infinity (Codex).** See [CF1-INFINITY-HANDOFF](CF1-INFINITY-HANDOFF.md).
  CF never edits the native renderer.

## 5. Publication policy

Hero replacements are never published automatically. The recipe's
`approval.status` starts as `candidate`. It needs (1) all validator checks
green, (2) an independent artistic review recorded with reviewer identity, and
(3) an Infinity capture judged against [CF0-CHARACTER-QUALITY-STANDARD](CF0-CHARACTER-QUALITY-STANDARD.md)
Gate B. Only then may the asset be admitted to the authoritative catalogue.
Self-approval by the generating agent is not accepted.
