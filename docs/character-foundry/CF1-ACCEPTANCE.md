# CF1: Acceptance

**Decision state: candidate.** Not declared at any tier. Not published. Not
admitted to the authoritative catalogue. Nothing in Infinity, FinalStorm or
Core was changed.

## Deliverables

| Requirement | Status | Evidence |
| --- | --- | --- |
| Repository and toolchain audit | done | CF0-TOOLCHAIN-EVALUATION.md |
| Founder quality assessment ([T]/[A] separated) | done | CF0-FOUNDER-QUALITY-ASSESSMENT.md |
| Pipeline architecture, Path A/B, contract, integration | done | CF0-ARCHITECTURE.md |
| Quality standard (Gate A / Gate B) | done | CF0-CHARACTER-QUALITY-STANDARD.md |
| Elara design brief from canon + vision art | done | CF1-ELARA-DESIGN.md |
| Editable .blend (mesh, materials, textures, rig, clips) | done | `elara_cf1.blend` (project storage, digest in recipe) |
| Neutral pose, idle, walk, gesture | done | `Elara_Idle`, `Elara_Walk`, `Elara_Wave` |
| Runtime GLB | done | `elara_cf1_runtime.glb` |
| Renders: front, ¾, side, rear, face, both rigs | done | `renders/elara_{neutral,production}_*.png` |
| Runtime validation | done, all pass | `glb-check-{hero,runtime,proxy}.json` |
| Codex handoff | done | CF1-INFINITY-HANDOFF.md |
| Before/after comparison, identical framing | done | CF1-VISUAL-COMPARISON.md, `compare/` |
| Versioned recipe with digests, approval status | done | `recipe.json` (`approval.status: candidate`) |
| Independent artistic review | **open** | needs Albert or an artist |
| Gate B Infinity capture | **open** | needs Infinity runtime work (Codex) |

## Gate A, technical items [T]

| Item | Result |
| --- | --- |
| Anatomical base mesh, no primitive limbs | pass (MakeHuman hm08) |
| Quad-dominant body, deforms at joints | pass |
| No floating parts outside accessories | pass |
| Eyeballs, lids, lashes, brows, lips | pass |
| Expression system (smile, blink, + one) | pass (smile, warm smile, curious, blink) |
| ≥ 6 material zones; BaseColor + Normal + ORM on main fabrics, skin, hair | pass (16 materials) |
| Skin subsurface | pass |
| Layered garments with thickness; cloth simulated or folded | pass (cloak simulated) |
| Hair volume, not a painted cap | pass |
| One skeleton, all meshes skinned, ≤ 4 influences, normalised | pass |
| Idle, locomotion, gesture; loops close; feet on ground | pass |
| Neutral render with Infinity tone mapper; both rigs, all views | pass |
| Budgets (hero ≤ 250k / 160 MiB, runtime ≤ 40k / 48 MiB, proxy ≤ 40k / 8 mats) | pass (100,980 / 149.3; 37,442 / 41.3; 20,256 / 7) |

## Gate A, artistic items [A]: for the reviewer

Score each pass / borderline / fail. The generating agent's own view is given
only as a starting point and does not count.

| Item | Agent's view (advisory) |
| --- | --- |
| Readable as Elara from the silhouette at 18 m | likely pass |
| Canon features legible in close-up | pass |
| Proportions coherent with house style | borderline: realistic rather than stylised |
| Face reads as the character, not a mannequin | borderline: a person, but neutral; less warm than the vision |
| Garment detail supports identity | pass |
| Hairstyle distinctive and on-model | borderline: braid good, cap helmet-like |
| Motion character-specific and continuous | borderline: clean but analytic |

## Gate B

Not started. It needs the four Infinity capabilities in
CF1-INFINITY-HANDOFF.md §3 (textured PBR, GPU skinning, clip playback,
tangents). A Blender render never passes Gate B.

## What happens next

1. Albert (or an artist) reviews the renders and scores the [A] rows.
2. If the verdict is "polish first", CF1.1 fixes hair and face appeal (known
   weaknesses 1–2 in the production report) and re-renders.
3. Codex implements Gate B on the Infinity character path and records the captures.
4. Only after 1 and 3 may the owner admit the package (`admit_studio_package`,
   a new revision on a copied world).
