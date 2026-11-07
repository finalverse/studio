# CF0: Character quality standard

This standard extends the V0 tiers (Q0 to Q4, judged in Infinity) with two
independent gates and a checklist per discipline. Each item is tagged
**[T]** if it is a technical check a machine can verify, or **[A]** if it is
an artistic judgment that needs an independent human reviewer. Passing every
[T] item never implies an artistic tier.

## Gate A: authoring quality (Studio / Blender)

Does the character look professional in Studio, under both standard lighting
rigs (`cf_render.rig_neutral`, `cf_render.rig_production`)?

| Discipline | Requirement |
| --- | --- |
| Identity | [A] Readable as the canonical character from the silhouette alone at 18 m. [A] Canon features legible in a close-up (Elara: auburn braid, green tunic, blue cloak, boots, satchel). |
| Silhouette | [A] Deliberate primary shape (Elara: cloak triangle and braid line). [T] No floating parts (no detached islands outside accessories). |
| Anatomy | [T] Anatomical base mesh or approved archetype base. No primitive-cylinder limbs. [A] Proportions coherent with the house style. |
| Topology | [T] Animation-ready: body is quad-dominant and deforms at the joints. Garments have no zero-area faces. [T] Triangle budget per profile (below). |
| Face | [T] Eyeballs with iris/pupil/sclera, lids, lashes, brows, lips with distinct material response. [T] Expression system: at least smile, blink and one other expression drive the face. [A] Face reads as the character, not a mannequin. |
| Materials | [T] ≥ 6 purposeful material zones. [T] BaseColor + Normal + ORM maps on the main fabrics, skin and hair. No final look made only of flat colours. [T] Skin uses subsurface. |
| Garments | [T] Layered garments with thickness (solidify or modelled). [T] Cloth either simulated or sculpted with folds. [A] Garment detail (trims, embroidery, stitching) supports the identity. |
| Hair | [T] Volume and clumping, not a painted cap. [A] Hairstyle distinctive and on-model. |
| Rig | [T] One skeleton. Every mesh skinned or rigidly bound. ≤ 4 influences per vertex, weights normalised. [T] Face bones or blend shapes for expressions. |
| Animation | [T] Idle, locomotion and at least one gesture. Loops close (first = last frame). Feet contact the ground. [A] Motion is character-specific and continuous. |
| Rendering | [T] Neutral render uses the Infinity tone mapper (Khronos PBR Neutral). [T] Turnaround front, three-quarter, side, rear, plus face close-up, under both rigs. |

## Gate B: runtime quality (native Infinity)

Does the same character look sufficiently similar in Infinity?

| Area | Requirement |
| --- | --- |
| Geometry | [T] glTF Y-up, metres, origin at ground contact, front −Z. [T] Height within 1% of canon. |
| Materials | [T] All three PBR channels load. [T] Colour management matches (sRGB BaseColor, linear Normal/ORM). [A] Side-by-side with the Studio neutral render, same camera: no lost textures, no hue shift. |
| Skinning | [T] GPU skinning of the 163-bone skeleton (or the mapped 26-joint `finalverse.humanoid/v1` subset). [A] No candy-wrapper or collapsing joints in walk/wave. |
| Animation | [T] Clips play at authored length and loop flags. [A] Same motion as the Blender playback. |
| Budget | [T] Runtime profile ≤ 40,000 triangles, ≤ 48 MiB GPU texture memory with mips, gathering p95 frame time ≤ 33 ms on the M1 benchmark. |
| Evidence | [T] Infinity close-up at the focus camera and the gathering capture. A Blender render alone never passes Gate B. |

## Tiers with the gates

| Tier | Gate A | Gate B |
| --- | --- | --- |
| Q2 | continuous forms, ≥ 4 material zones, readable face | V0 Q2 in Infinity |
| Q3 | all Gate A [T] items + textured PBR, skinned deformation, authored clips, facial expression | same in Infinity (needs runtime work: UVs, textures, GPU skinning, clips) |
| Q4 | Q3 + sculpted detail, simulated hair/cloth or equivalent secondary motion, bespoke shading, independent art sign-off | same in Infinity at cinematic camera |

A character is **declared** at a tier only when Gate A and Gate B both hold
and the [A] items are signed off by a reviewer who did not author the asset.
Until then the most it can be is a *candidate* for that tier.

## Budgets

| Profile | Triangles | Textures | Skeleton |
| --- | --- | --- | --- |
| hero (authoring GLB) | ≤ 250,000 | ≤ 2048², ≤ 160 MiB | full (163 bones) |
| runtime (Infinity M1) | ≤ 40,000 | ≤ 1024², ≤ 48 MiB | full or mapped 26 |
| proxy (Genesis static) | ≤ 40,000 | none (factor PBR, ≤ 8 materials) | none |

## Review protocol

1. The generator agent produces renders and validator reports, and records itself as author.
2. An independent reviewer (Albert, an artist, or a second model run whose output
   only holds the asset for human decision) scores every [A] row as pass,
   borderline or fail, with a note.
3. Model judgments are advisory (GC4 `model-judgment/v1`, hold-for-human only).
   A human records the final decision in the recipe's `approval` block.
