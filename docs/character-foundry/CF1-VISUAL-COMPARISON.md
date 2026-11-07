# CF1: Visual comparison, V1 Elara vs CF1 Elara

Same camera, same lights, same tone mapper (neutral rig, Khronos PBR Neutral,
exposure 1.0). "Before" is the V1 package `elara.fvpkg/asset.glb` rebuilt from
Studio `feat/studio-v1` @ `57ed216c`. "After" is the CF1 `.blend`.

Images (in `docs/studio/evidence/cf1/`):

- `compare/v1_vs_cf1_front.png`
- `compare/v1_vs_cf1_three_quarter.png`
- `compare/v1_vs_cf1_face.png`
- `compare/sheet_neutral.png`, `compare/sheet_production.png` (CF1 turnarounds)
- `motion/sheet_walk.png`, `motion/sheet_wave.png`, `motion/sheet_face.png`

[T] marks a measurable fact, [A] an artistic judgment by the generating agent
(not an independent review).

| Area | V1 (before) | CF1 (after) |
| --- | --- | --- |
| Silhouette | [A] Mannequin with a stepped blue panel behind. No cloak triangle, no braid line. | [A] Cloak triangle open at the front, braid over the left shoulder, crossbody strap and satchel, tall boots. All five silhouette cues in the brief read. |
| Face | [T] Sphere eyes, bar mouth, no lids, lashes or nose structure. | [T] Anatomical face, fitted eyeballs with painted iris and clearcoat, lids, ribbon lashes, brows, lips, freckles. Bone-driven expressions (smile, warm smile, curious, blink). [A] Reads as a person. Still more neutral and realistic than the vision art. |
| Clothing | [T] Body-colour zones. No tunic hem, no layering. | [T] Layered tunic over leggings, sleeves with rolled cuffs, belt, simulated cloak with lining and hood, boots with cuffs and laces. |
| Materials | [T] 10 flat factor materials, no textures. | [T] 16 materials, 22 painted maps (BaseColor, Normal, ORM), skin subsurface, cloth sheen, gold embroidery and leaf border. |
| Rig | [T] 6 rigid joints, parts bound to one joint each. | [T] 163-bone skeleton with face bones, one skin, ≤ 4 smooth influences. Mapping to `finalverse.humanoid/v1` provided. |
| Animation | [T] Rigid-joint review clips, not played at runtime. | [T] Idle (breathing, blinks), in-place walk with ground solve, wave with smile. |
| Rendering | [T] Neutral only. | [T] Neutral and production rigs, five views plus face close-ups. |
| Polycount | [T] 24,086 | [T] 100,980 hero / 37,442 runtime |
| Texture memory | [T] 0 | [T] 149.3 MiB hero / 41.3 MiB runtime (RGBA8 + mips) |
| Runtime suitability | [T] Works on today's E1 path (factor-only, rigid joints). | [T] Runtime GLB validates against the M1 budget, but Infinity must add textured PBR, GPU skinning and clip playback (Gate B). The static proxy works on today's path at Q2 fidelity. |

## Against the vision art

[A] Matches: palette discipline (green, blue, auburn with gold), braid line,
belted tunic with gold embroidery, crossbody satchel and flute, cloak with gold
border, laced boots, hazel eyes and freckles.

[A] Misses: the vision's painterly warmth and stylised, larger-eyed face; the
loose, airy hair (CF1 hair is tighter and helmet-like); softer cloak drape at the
shoulders. The hummingbirds and glowing flora are out of scope by the brief.
