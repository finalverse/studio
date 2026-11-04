# V0 visual quality standards and Studio–Infinity conformance contract

## Quality tiers (judged in Infinity, not in Studio)

| Tier | Name | Definition (all criteria must hold in an Infinity capture) |
| --- | --- | --- |
| **Q0** | Placeholder | proxy shape (capsule/box), one material; identity readable only from labels |
| **Q1** | Primitive stylized | assembled primitives with visible seams; flat per-part colour; archetype readable at gathering distance; rigid procedural articulation. *(All E1 founders today.)* |
| **Q2** | Production-stylized | continuous, intentional forms with no visible primitive seams at 2 m; canon-defining features legible in a close-up (hair, cloak, eyes, bark, flame, petals); ≥ 4 purposeful material zones with distinct roughness/metallic/emission; readable face or focal feature at the focus camera; character-specific motion through E1-compatible articulation; LOD1 keeps the silhouette at 18 m; within budgets below |
| **Q3** | Production | Q2 plus textured surfaces (albedo/normal/ORM), skinned smooth deformation, authored clips played at runtime, facial expression. **Needs runtime work first** (UVs, textures, GPU skinning in the E1 path) |
| **Q4** | Hero / cinematic | Q3 plus sculpted detail, hair/cloth simulation, bespoke shading, cinematic lighting |

Budgets per character (Infinity, M1): LOD0 ≤ 40,000 triangles (E1 hard cap
100,000), LOD1 ≤ 40% of LOD0, ≤ 48 parts, body ≤ 4 MiB, all seven together
inside the 8 MiB requested-GPU-asset budget, gathering p95 frame wall time
≤ 33 ms on the benchmark.

## Studio → Infinity Visual Conformance Contract

| Area | Contract |
| --- | --- |
| Geometry conventions | metres; glTF/E1 **Y-up, right-handed**; Blender Z-up converted by (x, y, z) → (x, z, −y); front faces −Z in Y-up (−Y in Blender); origin at the ground contact point (floating archetypes: origin at ground, body ≥ 2 cm above); positions within ±8 m; finite normals |
| Hierarchy | one body per character; parts are flat (no runtime hierarchy); a part's motion comes only from its `joint` (rigid) or E1 procedural deformation; part names must not contain `leg`/`foot`/`walking` for spirits |
| Skinning and morphs | none at runtime. A part binds to at most one joint (dominant weight); no morph targets; Studio skin weights are authoring data only |
| PBR channels | per-part factors only: base colour RGBA linear 0–1, metallic 0–1, roughness 0.04–1, emissive RGB 0–8 (linear, pre-tone-map), pulse 0–1. No textures, no UVs |
| Transparency | opaque only for characters; `Blend` is not drawn as translucent. Use emission and shape for glow |
| Emissive | luminous characters keep body emission ≤ 1.5 and base colour ≤ 0.85 so Khronos Neutral does not clip them to white; reserve 3–8 for small accents (eyes, cores, flames) |
| Colour space | author linear; compare Studio previews with **view transform matching Infinity's tone mapper** (Khronos PBR Neutral, exposure 1.0) |
| Animation interpolation | Infinity runs E1 procedural expressions; Studio clips must be reproducible from joint-level rigid motion and are reviewed as clips only. Conformance evidence is the Infinity capture, not Blender playback |
| LOD | exactly two LODs at 0 m and 18 m; LOD1 from the same parts (same names and joints), decimated |
| Budgets | as above; draw calls ≈ parts × actors, so prefer fewer, richer parts |
| Evidence | every V1 asset needs an Infinity close-up at its focus camera and the gathering capture; a Blender render alone never passes |

## Acceptance rule

A V1 asset passes a tier only if its **Infinity capture** meets that tier. If
the Studio render is better than the Infinity capture, the asset is assessed on
the Infinity capture.
