# S2 creation engine

S2 extends accepted S1 (`5fa8900ee7b`) on `feat/studio-s2`. The closed language
becomes `finalverse.creation/v2`, a strict superset of v1. A v1 plan validates and
runs exactly as before, and a v1 plan cannot name a v2 tool. Results and evidence
are in [S2 acceptance](S2-ACCEPTANCE.md).

## One path for every caller

UI, MCP, model plans, artist drafts and the creation loop all submit the same JSON
envelope. It goes into the same durable store and is approved by the same exact
digest/scene/revision/session approval. It executes one bounded operation per
timer tick on Blender's main thread. Previews render in the S1 deny-default
sandboxed worker. No model code, node graph, bone list, Python or file path is
interpreted. Every v2 operation names a fixed implementation in
`scripts/modules/finalverse_creation/creation2.py`, backed by Blender operators
and data APIs.

## Typed tools

| Area | Operations | Blender backing | Bounds |
| --- | --- | --- | --- |
| Mesh | `mesh.primitive` (uv/ico sphere, cube, cylinder, cone, torus, plane), `mesh.subdivide`, `mesh.deform` (taper/bend/twist/stretch), `object.parent`, v1 `mesh.bevel` | `bpy.ops.mesh.primitive_*`, Subsurf and SimpleDeform modifiers, **applied** | 100,000 vertices per object; levels 1–3; cycle-free parenting |
| Geometry Nodes | `geonodes.scatter` | fixed recipe: Object Info → Distribute Points on Faces (seeded) → Instance on Points (seeded random scale/yaw) → Realize Instances, then the modifier is **applied** | 1–512 instances, result 100,000 vertices; prototype hidden |
| Procedural buildings | `procedural.building` | deterministic BMesh walls, floor bands, window grid, flat parapet or gable roof | 1–20 floors, 2–60 m, 0–16 window columns, seed |
| Vegetation | `procedural.tree` (broadleaf, conifer, shrub) | deterministic BMesh trunk, branches, canopy clusters | 0.3–30 m, 0–12 branches, seed |
| Characters | `character.spirit`, `character.humanoid` (human / synthetic) | reviewed parameter-only anatomy templates with named parts | height 0.3–3.5 m (E1 specification bounds) |
| Materials | `material.preset`, `material.assign_parts`, v1 `material.create/assign` | single Principled BSDF: base colour, roughness ≥ 0.04, metallic, emission colour/strength, alpha | E1 material behaviour bounds |
| Armatures | `armature.create` (`humanoid_basic`, `synthetic_basic`, `fire_basic`, `tree_basic`) | edit bones from the E1 joint templates (`root, head, arm_l, arm_r, leg_l, leg_r`; tree `trunk, branch_l, branch_r, canopy`) | ≤ 64 bones; template only |
| Skinning | `armature.skin` (automatic heat / envelope) | `object.parent_set(ARMATURE_AUTO/ENVELOPE)` | one Armature modifier, unparented target |
| Actions | `action.create` | keyframes on object or pose-bone channels, one NLA track per clip, kind/locomotion/loop metadata | 2–96 keys, frames 1–480, ascending |
| Retargeting | `action.retarget` | maps named bone rotation/scale curves; root translation scaled by bone-length ratio | ≤ 64 mapped bones, all must exist |
| Camera / lights | v1 `camera.configure`, `light.configure`; `light.rig` (three-point, soft key, rim) | area lights aimed at a target | energy ≤ 20,000 W |
| Render | `render.configure`, `preview.render`, v1 `scene.render` | Eevee, frame range, fps, transparent film, world colour, view transform | 64–1024 px, 1–64 samples |
| Export | `asset.package` | see [Genesis integration](S2-GENESIS-INTEGRATION.md) | one package per plan |

Generated meshes are rebuilt canonically: vertices in creation order, each face
rotated to its lowest vertex index, faces sorted by part. We found that BMesh face
storage order is not stable across runs (two identical builds produced different
polygon orders), and the canonical rebuild makes identical inputs produce identical
geometry hashes. Named parts (`finalverse.parts` plus the `fv_part` face attribute)
carry anatomy and material targeting through to export.

## Scene revision coverage

The S1 scene index now also hashes armature bones and pose, vertex-group weights,
the one permitted Armature modifier, NLA clip tracks with their keys and metadata,
part attributes and material indices, viewport/render visibility, and render
settings. Live Geometry Nodes, other modifiers, constraints, drivers and shape
keys are still refused; every S2 tool applies its modifiers. A concurrent edit to
any of these stops a running plan, as in S1.

## Planning with a model

`providers.plan(..., language='v2', context=...)` sends a system prompt whose
operation reference is **generated from the schema** (`grammar_v2`), plus a worked
example that is deliberately not Lumi (a hovering lantern), the current scene
summary and, for revisions, the failed checks. Ollama runs in JSON mode with 3,072
output tokens and a 12,288 context; OpenAI-compatible servers get
`PLAN_SCHEMA_V2` as the strict response schema. Model output is parsed strictly and
validated locally. Invalid output is a visible failed attempt, never repaired.
