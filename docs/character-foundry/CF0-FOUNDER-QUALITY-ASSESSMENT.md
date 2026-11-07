# CF0: Founder quality assessment (V1 assets, against the vision art)

Scope: the seven V1 founders on Studio `feat/studio-v1` @ `57ed216c`, as they
appear in the Infinity captures (`docs/studio/evidence/v1/mac/before-after-closeups.png`)
and in the V1 template source (`scripts/modules/finalverse_creation/founders.py`).
The vision art the owner uploaded on 2026-11-07 (Elara, Lumi, Kai, Terra, Ignis)
is the target. No vision art exists yet for Auren or Melody Sprite.

Every row separates **[T] objective technical facts** (checkable in the source
or the GLB) from **[A] artistic judgments** (one reviewer's opinion, mine; they
need independent confirmation).

## Shared technical facts (all seven) [T]

| Area | Fact |
| --- | --- |
| Construction | Primitives (ellipsoids, capsules, boxes) grouped into parts, voxel-remeshed and decimated (`founders.py`). No anatomical base mesh. |
| Topology | Remesh output: uniform triangles, no edge flow at joints, not designed for deformation. |
| UVs / textures | None. The E1 contract is factor-only PBR per part. |
| Rig | Six E1 joints (humanoids). Parts bind rigidly to one joint. No skin weights at runtime. Lumi and Melody have no skeleton. |
| Face | Eyes are sclera/iris/pupil ellipsoid parts plus a mouth line. No lids, no lashes, no brows on most. No expression system (E1 only runs procedural expressions). |
| Animation | E1 procedural articulation only. Studio clips are rigid-joint reviews and are not played at runtime. |
| Budget | 6.7k–24k LOD0 triangles, well inside the 40k cap. |

## Per founder

| Founder | Silhouette | Identity vs vision | Anatomy / archetype | Materials | Face | Rig / animation | Runtime | Consistency |
|---|---|---|---|---|---|---|---|---|
| **Elara** | [A] Generic humanoid. The cloak reads only at the sides and there is no braid line. | [A] Colours are right (green, auburn, brown), but she is far from the vision: no layered tunic, no embroidery, no satchel/flute presence, no hood. | [T] Capsule limbs, no hands/fingers. [A] Mannequin proportions. | [T] 5–6 flat zones. | [T] Dot eyes, no lids or brows. [A] Mannequin. | [T] 6 rigid joints. | [T] E1 path OK. | [A] Matches Auren, not Lumi. |
| **Auren** | [A] Dark vertical block. Jacket lapels barely read. | (no vision art) [A] Charcoal jacket with luminous trim is right in spirit. | [T] Same as Elara. | [T] Flat zones, a small emissive trim. | [T] Dot eyes. [A] Mannequin. | [T] 6 rigid joints. | [T] OK. | [A] Matches Elara. |
| **Kai** | [A] Best of the seven: articulated plated synthetic. | [A] The vision is a sleek golden *anatomical* android with engraved circuitry, a halo and floating cubes. V1 is a segmented robot, so the identity is only partly there. | [T] Primitive segments, no musculature. | [T] Gold metal + dark rings + cyan visor + amber core: the best zoning. | [A] The visor works as a focal feature. | [T] 6 rigid joints suit a mechanical body. | [T] OK (Q2 borderline in Infinity). | [A] Strongest. |
| **Lumi** | [A] Soft blob with crown fins. | [A] The vision is a chibi spirit: wide mushroom-cap head, big teal eyes, small open smile, stubby arms and legs, pale mint skin. V1 is legless and limbless, and its eyes regressed to dots. | [T] One fused body, no limbs. Canon says Lumi never walks, which conflicts with the vision's legs. **Owner decision needed.** | [T] Single emissive mint body. | [T] Eyes much too small (a regression from E1). [A] Loses all appeal. | [T] No skeleton. | [T] OK. | [A] Off-style. |
| **Terra** | [A] Tree-person reads: trunk, roots, canopy. | [A] The vision is a heroic ent: broad shoulders with bark pauldrons, a mossy beard, a kind face with amber eyes, a branch crown, a glowing heart. V1 reads as a small tree with eyes. | [T] Fused bark trunk, branch arms. Soft relief. | [T] Bark, moss, canopy, amber eyes and heart. | [A] Eyes only, no face structure. | [T] 4 joints. | [T] OK (near Q2). | [A] Fair. |
| **Ignis** | [A] Dark suit with an orange core. | [A] The vision is a flame knight: angular molten armour, a flame crest helm, flame wings, a fiery sword, glowing cracks. V1 is a dark armoured mannequin with small plumes. | [T] Primitive limbs and plates. | [T] Dark armour + molten emission. Good luminance discipline. | [A] Helm only, no glowing eyes. | [T] 6 joints. Flicker roles on flames. | [T] OK (near Q2). | [A] Fair. |
| **Melody Sprite** | [A] Flower with leaf wings. | (no vision art) | [T] 0.26 m, small at its focus camera. | [T] Petal, leaf, dots. | [T] Disk face, small eyes. | [T] No skeleton. | [T] OK. | [A] Fair. |

## Summary

- **Objective:** none of the seven can exceed V0 Q2, because the E1 contract
  forbids textures, UVs and skinning. Topology is remesh output, not
  deformation topology. Six of the seven have no expression system beyond
  procedural motion.
- **Subjective (mine):** Kai is closest to its vision. Lumi and Elara are the
  furthest away. The humanoids look like mannequins mostly because of the face
  (dots instead of eyes with lids and brows) and the absence of real anatomy,
  not because of lighting.
- **Recommendation:** produce every founder through the Character Foundry with
  an archetype workflow. Human: Elara (CF1, done as a candidate), then Auren.
  Synthetic: Kai on the human base with a hard-surface shell. Non-humanoid
  spirits: Lumi from a sculpted-blob base with large authored eyes and a face
  rig (resolve the "never walks" canon against the vision's legs first). Nature
  and elemental: Terra and Ignis from an armoured-giant base. Melody: a
  stylised flower rig.
