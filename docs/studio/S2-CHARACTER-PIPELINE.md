# S2 character pipeline

Studio follows E1's universal embodiment taxonomy (Core `33eb4b0`,
`E1-EMBODIMENT-TAXONOMY.md`). There is no single humanoid skeleton. Archetype is
declared on the export (`asset.package.archetype`, or the loop's archetype), and
`protocol.archetype_rules` enforces it **before approval**:

| Archetype | Body tool | Skeleton | Allowed clip locomotion |
| --- | --- | --- | --- |
| `floating_spirit` (Lumi) | `character.spirit` | **none**: `armature.*`, `action.retarget` and `character.humanoid` refused | hover, fly, drift, none |
| `botanical_sprite` (Melody) | `character.spirit` / primitives | none | fly, hover, drift, none |
| `humanoid` (Elara, Auren) | `character.humanoid` build `human` | `humanoid_basic` 6 joints | walk, run, climb, none |
| `synthetic_humanoid` (Kai) | `character.humanoid` build `synthetic` | `synthetic_basic` | walk, run, climb, none |
| `nature_elemental` (Terra) | `procedural.tree` + parts | `tree_basic` 4 joints (optional) | rooted, walk, climb, none |
| `fire_elemental` (Ignis) | primitives + emissive presets | `fire_basic` | walk, run, hover, none |
| `environment`, `prop` | buildings, trees, scatter, primitives | none | none (`prop` may hover/drift) |

For spirits, any operation or part whose name contains `leg`, `foot` or `walk` is
also refused. This matches E1's `spirit cannot acquire conventional legs` rule.

## Floating spirit (Lumi)

`character.spirit` follows E1's reviewed spirit anatomy: a continuous rounded
body, a rounded crown with a tapered tip, soft crown fins and subtle side fins,
and large eyes with pupils. It has no armature and no leg/foot parts. Its lowest
point sits above the object origin, so the silhouette floats. Parameters are only
height and the body/crown/fin/eye proportions. Lumi's E1 canon text (canon
identity `2c92f74c-…`): *"Soft rounded ethereal luminous body, large expressive
eyes, subtle side fins, continuous floating silhouette; no obvious legs,
conventional humanoid skeleton or walk cycle."* The identity is carried only as a
reference in the package; nothing binds it.

Spirit animation is object-level (location/rotation/scale) clips: hover, drift
and greet in the demo. E1's runtime animates spirits procedurally ("squashes
subtly, brightens and lifts"); Studio clips are authored candidates for that
review, not a replacement for E1's runtime kernel.

## Rigged characters

`character.humanoid` builds named parts (head, torso, pelvis, upper arm, forearm,
hand, thigh, shin, foot, eyes or core lights). `armature.create` places the E1
6-joint template scaled to height. `armature.skin` binds automatically (bone heat)
or by envelope. The evaluator requires every vertex weighted and all template
joints present. Exported GLB carries one skin with the joints. The E1 body maps
each part to its dominant joint. Retargeting copies named bone rotation curves
between armatures and scales root translation by the root-bone length ratio.
It is intentionally simple: same-template rigs only. It is not a general
rest-pose-compensated retargeter.

## What the evaluator enforces for characters

Height 0.1–3.5 m; spirits float ≥ 2 cm above origin and have no skeleton or legs;
rigged characters have their feet at the origin, a skin, the template joints and
no unweighted vertices; clips are finite, 0.25–20 s, archetype-compatible, loop
clips return to their first pose, displacement ≤ 2 m (≤ 0.3 m for
non-locomotion), and scale change ≤ 0.1 (E1 `max_scale_delta`).

## Limits

Anatomy is template-driven and stylised. These are authoring candidates, not
production-quality character art, and there is no facial rig or shape keys. Studio
does not produce Ignis flame particles or Terra foliage behaviour; E1's runtime owns
those. Only Lumi was produced end to end through the model workflow. The other
archetypes are covered by fixture plans and rule tests.
