# finalverse.creation/v1

The executable schema is `finalverse_creation.protocol.PLAN_SCHEMA`. Both Studio
and `studio_capabilities` expose the same closed language. No operation accepts
Python, shell commands, arbitrary RNA paths, plugin names, external file paths or
publication authority. A plan contains exactly `schema_version`, `summary` and
`operations`. Duplicate JSON keys, nonfinite numbers, boolean-as-number, unknown
fields, unknown operations and oversized inputs are rejected.

| Operation | Typed arguments | Effect |
| --- | --- | --- |
| `scene.inspect` | none | Snapshot identity/revision and counts |
| `object.create` | ref, name, primitive | Cube, bounded sphere/cylinder or plane |
| `object.transform` | target, location/rotation/scale | Modify an existing object |
| `mesh.bevel` | target, width, segments | Applied bounded geometry modification |
| `material.create` | ref, name, color, roughness, metallic | Principled preset |
| `material.assign` | target, material | Assign a scene material |
| `camera.configure` | ref, name, location, look_at, lens | Create camera and make active |
| `light.configure` | ref, name, location, kind, energy, color | Create AREA/POINT light |
| `animation.keyframe` | target, frame, transform properties | Insert linear transform keys |
| `scene.render` | path, width, height, samples | Isolated Eevee PNG preview |
| `scene.save` | path | Editable `.blend` copy |
| `asset.export` | path | New S0 `.fvasset` candidate directory |

Coordinates use Blender metres, Z-up, Euler radians. GLB conversion remains the
upstream exporter's glTF convention. Positions are bounded to ±1,000, rotation to
±6.284, positive scale 0.001–100, frames 1–240, lens 20–120 mm, light energy at most
5,000, bevel width 0.001–0.5 and segments 1–4. Preview dimensions are 64–1,024 and
samples 1–64. Output names are safe basenames with their prescribed extension;
outputs are new files/directories within the job. Reused output names fail.

`@lower_case_alias` references are local to a plan and must follow creation.
Persisted objects/materials use UUIDs; names are display labels, not identity.
Preflight verifies object/material presence and compatible types. Runtime checks
bound each bevel to 2,000 input vertices / 4,000 polygons, including repeated bevels.

Example:

```json
{"schema_version":"finalverse.creation/v1","summary":"Create a beacon",
 "operations":[
   {"op":"object.create","ref":"@beacon","name":"Beacon","primitive":"cube"},
   {"op":"mesh.bevel","target":"@beacon","width":0.1,"segments":2}
 ]}
```

## Scene index and revisions

The persistent `finalverse.studio-scene/v2` index contains scene/object/material
identities, parent relationships, transforms, mesh digests, material graphs,
animation paths/keys, camera/light data, semantic descriptions and job provenance.
Creation provenance is retained separately from the most recent modifying job;
new objects receive the plan intent as their initial semantic description.
It also records current frame, frame range and background world graph. Revision
digests detect supported scene edits before approval and between operations.
Material creation stays indexed before assignment through job provenance. Unused
unrelated datablocks are excluded.

S1 accepts at most 256 scene objects/materials, 100,000 vertices, 600,000 face
corners and 4,096 keys per object. Its explicit subset is meshes, lights, cameras,
empties, direct Principled materials and a direct Background world. Constraints,
drivers, unapplied modifiers, complex material/world graphs and other object types
require a later profile. It is not a universal Blender scene serialization or
arbitrary add-on state hash. This bounded profile is separate from unrestricted
human authoring in Blender. Stable identities and animation survive save/reopen.

## Execution and recovery

`Proposed → Approved → Applying ↔ Rendering → Completed` is the success path.
Failed, Cancelled and Interrupted are terminal. Request UUID plus exact plan/scene
digest provides duplicate-submit idempotence across connections; conflicting reuse
is rejected. Approval is a short-lived host-session HMAC, unavailable to MCP.

Each applied operation records a result and a new checkpoint. Cancellation stops
future work; previously completed edits remain visible. Interrupted steps are never
automatically retried: a crash between mutation, metadata commit and checkpoint
cannot establish exactly which edit survived. Restart invalidates all approvals
and marks uncertain work Interrupted. The artist may explicitly reopen the last
regular checkpoint with scripts disabled, inspect, and propose a new plan.

Candidate manifests retain the accepted S0 contract, source/GLB hashes and
publication=false. Object extras/source contain creation job and plan digests;
the workspace job receipt links to the actual model receipt. Studio does not
independently certify geometry, authorize Genesis publication or alter MutSea.
