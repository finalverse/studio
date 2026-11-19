# V1 → V2 handoff

V1 ran end to end on the Mac: reviewed Studio founders, Genesis ingest, owner
authorization, SpatialDB/PostGIS publication with readback, rebinding of the
seven existing identities on a copied E1 world, restart persistence, and native
Infinity rendering. See [V1 acceptance](V1-ACCEPTANCE.md) and the
[quality review](V1-QUALITY-REVIEW.md). Only Kai reaches Q2, borderline. No
merge or deployment occurred. Codex owns V2 native rendering; V1 did not change
the Infinity renderer.

## Exact baseline

| Item | Value |
| --- | --- |
| Studio | `feat/studio-v1` (this commit; packages built from template commit `c1628e4e3f7`) |
| Core | `feat/e1-studio-generator-20261104` at `6ba5af4` |
| Infinity (local only, not pushed) | `feat/v1-founders-20261104` at `7afa69b`, from E1 `eb3cd4a`; renderer FinalStorm `05c79b3` unchanged |
| SpatialDB | `bc510bda5310beecd8455ccece0ca5d3e3c43248`, fixture namespace `studio-v1-20261104` |
| Package authoring | upstream Blender 5.2.2 LTS (`d13f752e3b9c`, OpenVDB on) |
| Private V1 root | `/Users/wenyan/Finalverse/dev/v1-20261104/v1-root` (`generated/`, `world/`); E1 original untouched |

## For V2 (art and runtime)

1. **Faces.** Humanoid eyes are dots, and Lumi's eyes regressed below E1's
   large expressive eyes. Template fix: eye size from canon (Lumi ≥ 2.5× current
   iris), brows and mouth that read at the focus camera.
2. **Secondary forms.** Elara's cloak should read from the front (wider shoulder
   drape, visible hem), Auren's lapels, Ignis's plume scale, Terra's moss.
3. **Scale and framing.** The Melody Sprite (0.26 m) and Lumi are small at
   their focus cameras. Infinity's focus framing is not subject-centred for every
   index.
4. **Runtime (Codex/V2).** The E1 character path has no UVs/textures, no GPU
   skinning, no morph targets and no blending (V0 matrix). Q3 requires that work.
   Studio already emits skinned, animated GLBs and per-clip data that a richer
   runtime path can consume.
5. **Template iteration loop.** A founder rebuild re-runs packaging →
   ingest → authorize → check → publish → rebind (r4) → restart → capture.
   Rebind needs a strictly higher revision, so the next pass is r4 on a fresh
   copy of this V1 world or of the E1 world.
6. **Maple.** It still does not resolve. Planner runs stay on local
   gemma4:e4b.

## Rules that still hold

Identities, entities, memories, capabilities and resources are reused, never
recreated. Studio bodies enter only through `admit_studio_package`.
Publication needs owner authorization plus SpatialDB readback. Lumi never walks
and has no skeleton. Acceptance is judged in Infinity.
