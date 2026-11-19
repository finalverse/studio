# V1 cloud continuation (2026-11-04)

V1 is **not accepted**. This records the work done in a Claude cloud session after the Mac session stopped partway through the Studio V1 rebuild.

## Environment

- Upstream `bpy` 5.2.3 LTS on Linux x86_64, 4 vCPU, no GPU. Its build has Remesh, OpenSubdiv and OpenVDB on, so the Mac V1 rebuild was not needed for geometry work.
- Previews use Cycles on the CPU because headless EEVEE has no GPU here. They are Studio authoring evidence, not evidence of how Infinity renders the characters.
- The driver is `finalverse/tests/v1_cloud.py`. Each founder goes through the same steps as the S2 native runner: validate, preflight, apply, preview, package.

## Result

The seven reviewed founder templates (`finalverse/tests/v1_founders.py`) all build headless in 4–7 seconds each. Every one passes deterministic evaluation, the S0 candidate gate and E1 structural checks. See `evidence/v1/v1-cloud-result.json`.

Core `civilization-v1 ingest` then ran on all seven packages:

- It re-admitted each package through the real E1 validator (`admit_studio_package`).
- It stored each package in Genesis CAS.
- It submitted each static proxy as a Genesis import job.

All seven reached **AwaitingAuthorization** (`evidence/v1/v1-genesis-ingest.json`):

| Founder | Archetype | Joints | LOD0 / LOD1 triangles |
|---|---|---|---|
| Elara | humanoid | 6 | 24,086 / 9,152 |
| Auren | humanoid | 6 | 22,124 / 8,406 |
| Kai | synthetic_humanoid | 6 | 13,442 / 5,106 |
| Lumi | floating_spirit | 0 | 6,748 / 2,564 |
| Terra | nature_elemental | 4 | 19,323 / 7,342 |
| Ignis | fire_elemental | 6 | 16,488 / 6,264 |
| Melody Sprite | botanical_sprite | 0 | 9,246 / 3,512 |

## Defects found and fixed

1. **Evaluator crash.** V1 part records have four fields (name, zone, joint, role), but `evaluate.py` unpacked only two.
2. **Dark seams.** The octree "smooth" remesh left holes where primitives overlapped, and these rendered as dark seams. Founders now use voxel remesh whenever OpenVDB exists, and fall back to octree when it doesn't.
3. **Degenerate triangles.** Decimating thin shells (flames, petals) left zero-area triangles. They are now dissolved, and loose vertices are removed so every vertex stays weighted.
4. **No static publication proxy.** Genesis import accepts only the reviewed static single-node GLB subset (`ec::geometry::validate_glb`), so the skinned and animated `asset.glb` was refused. Packages now also emit `proxy.glb`, built from LOD1 with factor-only PBR and at most 8 materials, and the Core driver imports that file. Core tests cover all seven proxies.
5. **Lumi's eyes were too small for canon.** The canon calls for large expressive eyes, and they were dots. They are now scaled up. Ignis's emission was also lowered so the tone mapper keeps the fire hue instead of clipping it.

## Honest visual assessment

See `evidence/v1/v1-before-after.png`.

- **Better:** the geometry. Bodies are fused and smooth, with no visible seams between primitives, and each has 2–5× the triangles of the E1 bodies.
- **Not yet better:** the overall look. In these previews the colours are washed out compared with the in-world E1 renders: Terra's bark reads beige, Auren reads grey, and Ignis's fire reads pale. The humanoids still look like mannequins.
- Part of that difference comes from the preview lighting (bright three-point rig, Khronos PBR Neutral) and part from the art.
- **No founder is claimed at Q2.** The tier has to be judged in Infinity.

## Remaining (Mac only)

- Owner publication authorization, and publication to SpatialDB/PostGIS.
- Rebinding the seven founders on a copy of the private E1 world (`civilization-v1 rebind`, then `restart`), and the restart-persistence check.
- Infinity Metal before/after captures and the sustained performance run.
- Art pass driven by what the characters look like in Infinity: palette saturation, the Elara cloak, the human faces.
