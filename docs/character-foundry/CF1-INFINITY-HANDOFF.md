# CF1 → Infinity native integration handoff (for Codex)

CF1 delivers an Elara **candidate**. Evidence and runtime files are in `docs/studio/evidence/cf1/`; code is in `finalverse/character_foundry/`. Nothing in Infinity, FinalStorm or the
authoritative character catalogue was changed. This page states exactly what
the asset contains, what Infinity must do to show it faithfully (Gate B), and
how to test it.

## 1. Files

| File | Use |
| --- | --- |
| `elara_cf1_runtime.glb` | **The runtime candidate.** 37,442 triangles, 22 JPEG textures (four at 1024², the rest 512² or 256², 41.3 MiB on GPU as RGBA8 with mips), 163-bone skin, three clips. 3.9 MB. |
| `elara_cf1.glb` | Hero/authoring profile: 100,980 triangles, four 2048² maps (skin colour and normal, tunic and cloak colour), 149.3 MiB GPU. Use it for cinematic cameras or to compare. 9.5 MB. |
| `elara_cf1_proxy.glb` | Static single-node, single-mesh, 20,256 triangles, 7 factor-only PBR materials. Passes the Genesis import subset (`ec::geometry::validate_glb`) and works on today's E1 static path with zero runtime changes, but at Q2-level fidelity. |
| `elara_rig_map.json` | 163-bone MakeHuman skeleton → `finalverse.humanoid/v1` (26 joints) mapping and weight-collapse rule. |
| `glb-check-*.json` | Validator output (`glb_validate.py`) per file. |
| `renders/elara_neutral_*.png` | Reference frames under the Infinity tone mapper (Khronos PBR Neutral). |

## 2. Conventions (verified by `glb_validate.py`)

| Item | Value |
| --- | --- |
| Axes | glTF Y-up, right-handed, metres. Character faces **−Z** (Blender −Y). |
| Origin | Ground contact between the feet. Min Y ≈ 0 (sole bottom). Height ≈ 1.72 m. |
| Hierarchy | One armature node `Elara_Rig` with 163 joint nodes. 128 mesh nodes (133 primitives), each skinned to the single skin. Mesh nodes are siblings, so no mesh-to-mesh hierarchy needs walking. |
| Skin | `JOINTS_0`/`WEIGHTS_0` only (≤ 4 influences), weights normalised. Rigid parts (hair, eyes, satchel, flute) are single-joint skinned, not parented. |
| Materials | metallic-roughness PBR. `baseColorTexture` (sRGB), `normalTexture` (tangent space, OpenGL +Y; tangents not exported, so generate MikkTSpace), `metallicRoughnessTexture` (G = roughness, B = metallic, R unused = 1). All opaque. Factors are 1.0 when a texture is present. Some materials are factor-only (brass, trim, hair cap, lashes, flower). The exporter also emits the optional `KHR_materials_sheen` (cloak, tunic), `KHR_materials_clearcoat` (eyes) and `KHR_materials_anisotropy` (hair). Infinity may ignore all three; the reference renders still hold without them. |
| Texture transform | The leggings knit uses a 10× UV tile through `KHR_texture_transform` (listed in `extensionsUsed`). Without support the knit reads as a smeared stripe, so implement scale/offset at least. |
| Clips | `Elara_Idle` (4.0 s, loop), `Elara_Walk` (1.067 s, loop, in place, stride 0.667 m, **1.25 m/s**), `Elara_Wave` (3.0 s, one-shot). Sampled every frame at 30 fps, linear. The exporter writes translation, rotation and scale channels for all 163 bones (489 channels per clip). Only `root` translation and the rotations carry motion; scale is constant 1 and translation on other bones is the rest offset, so both can be dropped at import. |
| Face | Expressions are bone-driven (no morph targets): smile, warm smile, curious and blink are baked into the clips. A runtime face layer can drive the face bones from the CC0 pose units (`face-poseunits.bvh`) with the same math as `elara_anim.load_poseunits`. |

## 3. What Infinity needs (Gate B), in priority order

1. **Textured PBR on the character path.** UV0 + three maps per material,
   sRGB/linear handling as above. Today the E1 path is factor-only (V0
   renderer capability matrix). This is the largest visible gap.
2. **GPU skinning** for one skin with ≤ 4 influences. Either the full 163 joints,
   or the 26-joint `finalverse.humanoid/v1` subset after collapsing weights per
   `elara_rig_map.json` (lossy: face and fingers become rigid).
3. **Clip playback** from glTF animations with loop flags. Root translation is
   in-place, so drive locomotion speed from `speed_mps`.
4. **Normal-map tangents.** Generate MikkTSpace on load, or ask CF to export tangents.
5. **Opaque-only** is fine. Nothing in CF1 needs blending. Lashes are geometry, not alpha cards.
6. **Budget.** Runtime profile: 37,442 triangles and 41.3 GPU MiB of textures
   as uncompressed RGBA8 with mips (about 10 MiB if transcoded to BC7/ASTC).
   Draw calls ≈ primitives (133). Merging primitives that share a material at
   import (they all share one skin) cuts this to 16, one per material.

## 4. Test plan

1. `python3 glb_validate.py elara_cf1_runtime.glb --profile runtime`. All checks must pass (they do in the cloud).
2. Load in Infinity at the focus camera. Compare with `renders/elara_neutral_front.png` and `_face.png` (same tone mapper, exposure 1.0). Look for missing textures, hue shift, inverted normals or a mirrored character.
3. Play `Elara_Walk` for 10 s. Check foot contact (the root height curve was solved so the lowest foot touches y = 0), loop seam, and cloak/leg intersections.
4. Play `Elara_Wave` and check that the right arm rises to the side with the forearm vertical and the face smiles.
5. Gathering capture with all seven founders, then the sustained 10-minute run, p95 ≤ 33 ms.
6. Record captures as Gate B evidence. Only then may the owner approve catalogue admission (`admit_studio_package`, new revision on a copied world, as in V1).

## 5. Known asset limitations to watch in Infinity

- The cloak is skinned to the spine and pelvis, without cloth simulation at
  runtime. During the walk the cloak lower edge can clip the trailing calf.
- The hair is rigid on `head`. The braid follows a head→neck→chest chain, with no dynamics.
- Normal maps were authored for Cycles. If they look inverted, check the green channel convention (+Y).
