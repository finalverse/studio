# S2 Genesis integration

Studio produces **candidates**. S2 changes no Core, Genesis, Civilization,
MutSea, SpatialDB or WorldLine code, and writes to none of their stores. The
authority chain is unchanged: Civilization policy authorizes, MutSea commits,
Genesis and SpatialDB admit and publish, Infinity renders, and WorldLine records.

## Package layout (`<name>.fvpkg/`)

| File | Contract | Purpose |
| --- | --- | --- |
| `manifest.json` | `finalverse.studio-asset-package/v1` | every file's SHA-256/bytes/media type, clips, LODs, evaluation digest, `published:false`, `world_effects:0`, `genesis.admission: required` |
| `candidate.json` | S0 `finalverse.studio-candidate/v1` | `asset.glb` + `source.blend` hashes, so the existing transport gate (`finalverse/validate_candidate.py`) applies unchanged |
| `source.blend` | Blender 5.4 | editable source |
| `asset.glb` | glTF 2.0, Y-up, metres | subject hierarchy, all clips as animations; skin for rigged archetypes |
| `clips/*.glb`, `clips/*.json` | glTF / `finalverse.studio-clip/v1` | one clip each; sampled tracks |
| `previews/*.png` | PNG | sandbox-rendered previews used by the evaluation |
| `body.json` | E1 `finalverse.universal-embodiment/v1` Artifact | characters only: parts per anatomy part and material, two LODs (0 m and 18 m), optional skeleton with pivots, source reference |
| `specification.json` | E1 Specification | name, identity reference, archetype, height |
| `definition.draft.json` | E1 EmbodimentDefinition (draft) | pins the body/specification hashes; locomotion from clip declarations; collision; `teleport_like:false` |
| `evaluation.json` | `finalverse.studio-evaluation/v1` | the gating report |
| `glb-check.json` | — | independent GLB structure results and export consistency |
| `contract-check.json` | — | Python port of E1 rules; generator-admission note |
| `provenance.json` | `finalverse.studio-provenance/v1` | job, plan digest, model receipts, scene revision, evaluation digest, build hash, license note, `authority: none` |

## Contract conformance, measured with the real E1 code

A scratch crate (outside every repository) links the accepted
`finalverse-embodiment` crate from Core E1 `33eb4b0` and runs its own validators
on the package (`Artifact::load`, `Specification::validate`,
`EmbodimentDefinition::validate`):

* **As exported:** E1 rejects the body (`universal asset header/LODs`) and the
  specification (`universal specification bounds`). The only cause is the
  `generator` header: E1 admits only its own reviewed worker
  `blender-universal/1`. Studio labels its output honestly as
  `finalverse-studio-s2/1` instead of impersonating that worker.
* **Structural probe:** the same bytes with only the generator string swapped pass
  `Artifact::load`, and the draft definition passes `EmbodimentDefinition::validate`.
  This holds for skeleton rules (none for the spirit), mesh, material,
  LOD/triangle budgets, locomotion compatibility and collision. The probe is
  never exported.

Admitting Studio as an E1 generator is therefore a Genesis/Core decision, outside
S2 authority, and is listed in the [V1 handoff](S2-V1-HANDOFF.md).

## Not done (by design)

No Genesis job was submitted, nothing was written to Genesis CAS, SpatialDB or
PostGIS, and nothing was bound to a resident or published. The S0 Genesis
adapter smoke pins a bundle ID of `org.finalverse.studio`; the S2 development
app uses `org.finalverse.studio.s2` for safe side-by-side testing, so that smoke
was not rerun against S2.
