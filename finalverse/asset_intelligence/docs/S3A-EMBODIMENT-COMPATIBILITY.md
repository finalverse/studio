# S3-A Embodiment and Runtime Compatibility

Two independent families of profiles are evaluated for every asset:

* **Runtime profiles** — can a specific Finalverse runtime admit these bytes? They
  reproduce actual admission code.
* **Embodiment profiles** — is this body fit for a kind of resident? Humanoid profiles
  build on the accepted E0 rig; spirit, sprite and elemental profiles are provisional.

## Contract status

| Contract | Status in inspected GitHub state | S3-A treatment |
|---|---|---|
| `finalverse.humanoid/v1` (E0) | **accepted** 2026-11-03 — `finalverse/finalverse@3cd0e93` `docs/genesis/E0-HUMANOID-STANDARD.md`, `crates/embodiment` | reproduced exactly (runtime profile) and used as the humanoid rig requirement |
| EC static GLB subset (G0) | **accepted** — `crates/ec/src/geometry.rs` `validate_glb` | reproduced exactly |
| Infinity network entry reader | **observed** in code — `finalverse/infinity@664445f` `src/entry.rs` `decode_parts`; no contract document | entry rules reproduced; inner FinalStorm decoder **unverified** |
| E1 universal embodiment | **not present** on GitHub | non-humanoid profiles are **provisional** S3-A proposals, labelled per requirement |

Nothing is labelled "unsupported" by assumption: where the consuming code was not
available the outcome is `unverified`.

## Runtime profiles

`status`: `compatible` (all rules pass), `incompatible` (a rule fails; later rules are
`not_evaluated`, mirroring the original first-error behaviour), `unverified` (all
reproducible rules pass but part of the real admission path could not be inspected).

#### `finalverse.ec-static-glb/v1`

| Rule | Requirement |
|---|---|
| EC-01 | Bounded GLB v2 (<= 2 MiB, declared length equals file length, JSON first chunk) |
| EC-02 | JSON chunk 1..262144 bytes, 4-byte aligned, followed by exactly one BIN chunk ending at EOF |
| EC-03 | UTF-8, strict duplicate-free JSON with finite numbers |
| EC-04 | Only reviewed top-level properties; asset.version 2.0; scene 0; scenes [{nodes:[0]}]; nodes [{mesh:0}] |
| EC-05 | No uri, extensions, images, textures, shaders, scripts, animations, skins or morph targets anywhere |
| EC-06 | Exactly one buffer with only byteLength equal to the BIN chunk length |
| EC-07 | At most 256 bufferViews and 256 accessors |
| EC-08 | 1..8 materials with only name/pbrMetallicRoughness/emissiveFactor/doubleSided/extras |
| EC-09 | Each material has baseColorFactor[4], metallicFactor, roughnessFactor and emissiveFactor[3] in [0,1] |
| EC-10 | Exactly one mesh with 1..8 indexed-triangle primitives referencing existing materials |
| EC-11 | Attributes exactly POSITION, NORMAL, TEXCOORD_0 (float) with uint32 indices; tightly packed, aligned |
| EC-12 | Equal attribute counts; at most 32768 vertices and 32768 triangles; index count multiple of 3 |
| EC-13 | Finite positions |v|<=1000, unit normals (|n|^2 in [0.98,1.02]), finite UVs |v|<=10000 |
| EC-14 | POSITION min/max present and within 1e-4 of decoded data |
| EC-15 | Indices inside the vertex buffer and no degenerate triangles |
| EC-16 | Vertex normals lie in the front hemisphere of each triangle (winding agrees with normals) |

#### `finalverse.humanoid/v1`

| Rule | Requirement |
|---|---|
| E0-01 | GLB of 28 bytes .. 4 MiB (byte identity is additionally pinned by the embodiment Definition) |
| E0-02 | GLB header and chunks: magic, version 2, exact length, JSON chunk then BIN chunk to EOF |
| E0-03 | UTF-8, strict duplicate-free JSON with finite numbers |
| E0-04 | No uri, extensions, scripts, textures, images or morph targets anywhere; depth <= 16 |
| E0-05 | Exactly the top-level properties asset, scene, scenes, nodes, skins, meshes, materials, animations, buffers, bufferViews, accessors |
| E0-06 | asset has exactly version 2.0 and generator 'Finalverse blender-humanoid/1'; one embedded buffer |
| E0-07 | 27 nodes, one skin, one mesh; scene roots [0, 26]; node 26 holds only mesh 0, skin 0 and name |
| E0-08 | Skin joints are nodes 0..25 in canonical order with 26 float MAT4 inverse binds |
| E0-09 | Joint nodes carry only name/translation/children; canonical names, bounded translations, canonical hierarchy, identity rest rotation |
| E0-10 | Inverse bind matrices equal the inverse global rest transforms within 1e-4 |
| E0-11 | 1..8 triangle primitives (explicit mode 4) without morph targets |
| E0-12 | POSITION/NORMAL/WEIGHTS_0 float, JOINTS_0 uint16, uint32 indices; packed, aligned, explicit view offset |
| E0-13 | At most 20000 vertices per primitive, equal counts, complete triangles, indices in range |
| E0-14 | Positions within 3 m, unit normals, joint indices < 26, weights in [0,1] summing to 1 |
| E0-15 | Each primitive has a material with baseColorFactor in [0,1] |
| E0-16 | 1..16 animations named from the 12 canonical clips, no duplicates |
| E0-17 | Each clip: 1..26 rotation-only channels on distinct joints with explicit LINEAR interpolation |
| E0-18 | Key times: 2..256 keys starting at 0, strictly increasing, ending <= 10 s; unit quaternion keys |

#### `infinity.entry-glb/observed`

| Rule | Requirement |
|---|---|
| INF-01 | GLB <= 8 MiB with valid header (magic, version 2, exact length, JSON chunk) |
| INF-02 | JSON chunk <= 65536 bytes and 4-byte aligned |
| INF-03 | JSON parses with finite numbers |
| INF-04 | BIN chunk immediately follows JSON and ends at EOF |
| INF-05 | Exactly one embedded buffer (no uri) not longer than the BIN chunk |
| INF-06 | No required extensions |
| INF-07 | If nodes are present: exactly one node, mesh 0, no transform or children |
| INF-08 | Exactly one mesh with 1..256 primitives, no primitive extensions |
| INF-09 | Each primitive passes the FinalStorm strict primitive decoder (finalstorm_spatialdb::glb::decode) |
| INF-10 | Referenced materials exist; baseColorFactor and emissiveFactor (if present) are finite and in [0,1] |

Notes:

* The E0 profile admits only bodies whose `asset.generator` is
  `Finalverse blender-humanoid/1`. The S3-A humanoid fixture is honestly labelled as an
  S3-A fixture, so strict E0 admission fails it on exactly `E0-06` while its rig passes
  every structural rule; the seven real E0 bodies pass all 18 rules.
* E0 also pins `geometry_sha256` in an embodiment *Definition*; that file-identity check
  is outside a single-GLB inspection and is reported as a note.
* Infinity renders E0 bodies through the same `Asset::load` (`src/bin/embodiment-render.rs`);
  static entry assets go through `decode_parts`. For the latter S3-A also reports
  `material_feature_support`: only `baseColorFactor` and `emissiveFactor` are consumed by
  the entry reader; other material features are `not_consumed_by_entry_reader` (the
  FinalStorm decoder's own handling is unverified).

## Embodiment profiles

`status`: `compatible` (all *required* requirements pass), `incompatible`, or
`unverified` (a required requirement could not be evaluated, e.g. no finite bounds).
Unmet *recommended* requirements are listed in `recommendations_unmet`. With
`--embodiment <profile>`, failures become findings (`FVA-EMB-001` required,
`FVA-EMB-002` recommended/missing capability) and proposals.

Non-humanoid profiles **never** require a humanoid skeleton: they accept any skeleton or
none, and motion may be node, skeletal or morph-target animation.

#### `biological_humanoid` (Biological humanoid)

Skeleton: required: finalverse.humanoid/v1. Contract: accepted (rig) + provisional (capabilities).

| Id | Level | Basis | Requirement |
|---|---|---|---|
| BH-01 | required | accepted:finalverse.humanoid/v1 | Canonical finalverse.humanoid/v1 rig (structure, not names only) |
| BH-02 | required | accepted:finalverse.humanoid/v1 | Standing height 1.4..2.1 m (E0 height_mm 1400..2100) |
| BH-03 | required | accepted:finalverse.humanoid/v1 | Origin under the feet (lowest point within 0.05 m of y=0) |
| BH-04 | required | accepted:finalverse.humanoid/v1 | At least one clip; all clips canonical and rotation-only |
| BH-05 | recommended | provisional:s3a | Locomotion capability (walk, turn) |
| BH-06 | recommended | provisional:s3a | Social capability (greet, speak) |
| BH-07 | recommended | provisional:s3a | Idle capability (idle) |
| BH-08 | recommended | provisional:s3a | Eyes and jaw influence geometry (expressive face) |

#### `synthetic_humanoid` (Synthetic humanoid (droid, android))

Skeleton: required: finalverse.humanoid/v1. Contract: accepted (rig) + provisional (capabilities).

| Id | Level | Basis | Requirement |
|---|---|---|---|
| SH-01 | required | accepted:finalverse.humanoid/v1 | Canonical finalverse.humanoid/v1 rig (structure, not names only) |
| SH-02 | required | accepted:finalverse.humanoid/v1 | Standing height 1.4..2.1 m (E0 height_mm 1400..2100) |
| SH-03 | required | accepted:finalverse.humanoid/v1 | Origin under the feet (lowest point within 0.05 m of y=0) |
| SH-04 | required | accepted:finalverse.humanoid/v1 | At least one clip; all clips canonical and rotation-only |
| SH-05 | recommended | provisional:s3a | Locomotion capability (walk, turn) |
| SH-06 | recommended | provisional:s3a | Social capability (greet, speak) |
| SH-07 | recommended | provisional:s3a | Idle capability (idle) |

#### `floating_spirit` (Floating spirit)

Skeleton: optional (any or none). Contract: provisional.

| Id | Level | Basis | Requirement |
|---|---|---|---|
| FS-01 | required | provisional:s3a | Finite extent 0.1..4 m |
| FS-02 | required | provisional:s3a | Ambient motion: at least one valid animation (node, skeletal or morph) |
| FS-03 | required | provisional:s3a | Hovers: lowest point above 0.05 m (no ground contact assumed) |
| FS-04 | recommended | provisional:s3a | Luminous or translucent appearance (emission or BLEND) |
| FS-05 | recommended | provisional:s3a | Ambient motion loops seamlessly |

#### `botanical_sprite` (Botanical sprite)

Skeleton: optional (any or none). Contract: provisional.

| Id | Level | Basis | Requirement |
|---|---|---|---|
| BS-01 | required | provisional:s3a | Finite extent 0.05..1.5 m |
| BS-02 | required | provisional:s3a | Ambient motion (sway): at least one valid animation |
| BS-03 | required | provisional:s3a | Rooted on its origin (lowest point within 0.05 m of y=0) |
| BS-04 | recommended | provisional:s3a | Alpha-tested/blended foliage materials are double-sided |
| BS-05 | recommended | provisional:s3a | Ambient motion loops seamlessly |

#### `nature_elemental` (Nature elemental)

Skeleton: optional (any or none). Contract: provisional.

| Id | Level | Basis | Requirement |
|---|---|---|---|
| NE-01 | required | provisional:s3a | Finite extent 0.5..8 m |
| NE-02 | required | provisional:s3a | Motion: at least one valid animation |
| NE-03 | required | provisional:s3a | Grounded on its origin (lowest point within 0.05 m of y=0) |
| NE-04 | recommended | provisional:s3a | Motion loops seamlessly |

#### `fire_elemental` (Fire elemental)

Skeleton: optional (any or none). Contract: provisional.

| Id | Level | Basis | Requirement |
|---|---|---|---|
| FE-01 | required | provisional:s3a | Finite extent 0.2..6 m |
| FE-02 | required | provisional:s3a | Emissive: a used material emits light |
| FE-03 | required | provisional:s3a | Warm emission: every emissive material has R >= G >= B |
| FE-06 | required | provisional:s3a | Motion (flicker): at least one valid animation |
| FE-04 | recommended | provisional:s3a | Translucent flame material (alpha BLEND) |
| FE-05 | recommended | provisional:s3a | Motion loops seamlessly |

### How the E0 contract maps

| E0 artefact | S3-A use |
|---|---|
| 26 `JOINTS`, `PARENTS`, identity rest rotations, inverse binds = inverse rest globals (1e-4) | `BH-01`/`SH-01` structural rig check (names alone never suffice) and runtime rules E0-07..E0-10 |
| `Specification.height_mm` 1400..2100 | `BH-02`/`SH-02` |
| frame `finalverse.body-eus-metres/v1`, origin under the feet | `BH-03`/`SH-03` (0.05 m tolerance is an S3-A choice) |
| 12 canonical clips, rotation-only LINEAR | `BH-04`/`SH-04`, E0-16..E0-18 |
| `BodyType` human/stylized_humanoid/droid | biological vs synthetic humanoid (`e0_body_types`) |
| `Capsule` radius 0.15..0.5, height 1.4..2.1 | `derived.collision_capsule` suggestion and `within_e0_definition_bounds` |

### Replacing provisional rules with E1

When E1 contracts are accepted: replace or re-label the provisional requirements in
`embodiment.PROFILES` (each carries `basis`), add E1 runtime admission as a runtime
profile if E1 has a loader, and keep requirement ids stable where meaning is unchanged.
