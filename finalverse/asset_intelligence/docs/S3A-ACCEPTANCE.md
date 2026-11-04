# S3-A Acceptance — Finalverse Asset Intelligence & Visual Quality Framework

Date: 2026-11-04. Environment: Linux cloud container, CPython 3.13.18 and 3.11.18,
no Blender, no GPU, no network access during inspection.

## Result

S3-A is implemented as a standalone, Blender-independent Python package on branch
`s3a/asset-intelligence` of `finalverse/studio`. All acceptance demonstrations below
were produced by executing the real parser and CLI; none of the reports are hand-written.
Studio S2 integration was **not** performed (S0/S1/S2 were not on GitHub); see
[S3A-S2-INTEGRATION-HANDOFF.md](S3A-S2-INTEGRATION-HANDOFF.md).

## Commits

| Commit | Description | Verified |
|---|---|---|
| base `0f5a1ae` | `finalverse/studio` `main` on GitHub (upstream Blender) | — |
| `ba1f3ce5` | library, CLI, pyproject | lint clean |
| `d10fe0ae` | fixtures, tests, tools, schema, acceptance evidence | fresh-worktree: lint, 89 tests (3.13), unittest (3.11), fixtures/schema/evidence reproduce, 200,000-input fuzz with 0 crashes |
| docs commit | `docs/S3A-*.md` | documentation only |

Dependencies: none at runtime (Python standard library, 3.11+). Development and verification:
pytest 9.2.0, hypothesis 6.170.14, jsonschema 4.26.0, ruff 0.16.9.
Evidence sources: `finalverse/finalverse@3cd0e93`, `finalverse/infinity@664445f`.

## Acceptance demonstration

Reproduce with `python tools/acceptance.py --check` (byte-for-byte), transcript in
[`acceptance/transcript.txt`](../acceptance/transcript.txt), full reports in
[`acceptance/reports/`](../acceptance/reports/).

| Asset (sha256 prefix) | Status | Runtime profiles | Compatible embodiments | Tier | Report digest prefix |
|---|---|---|---|---|---|
| 1. `humanoid_walker.glb` (`0edd4a17`) — animated canonical humanoid, 26 joints, 5 rotation-only clips | valid, 0 findings | E0 refuses only `E0-06` (honest generator label); EC/Infinity entry refuse (skinned, multi-node) | biological humanoid, synthetic humanoid, nature elemental | Q1 (capped: no visual evidence) | `882a8970` |
| 2. `floating_wisp.glb` (`f7fdca3d`) — floating non-humanoid, no skeleton, node bob/spin + morph pulse, emissive, translucent | valid, 0 findings | all refuse (animated multi-node asset) | **floating spirit only**, all recommendations met | Q1 | `4d3159a8` |
| 3. `defective_creature.glb` (`769c8feb`) — intentionally defective | **invalid**, 10 errors, 2 warnings | all refuse | none | none | `526717ca` |
| `static_prop.glb` (`b05b11f3`) — EC-subset static prop | valid | EC **compatible**; Infinity entry `unverified` (FinalStorm decoder unavailable) | none | Q1 | `177751ab` |
| `textured_crate.gltf` (`70b59214`) — .gltf + .bin + PNG | valid, 2 `FVA-DEP-002` warnings | all refuse (not GLB) | none | Q1 | `f308a6ce` |

Defects planted in asset 3, each detected exactly once with a proposal:

| Planted defect | Finding |
|---|---|
| node translation `1e400` | `FVA-CON-008` non-finite JSON number, `FVA-SCN-002` non-finite transform |
| index 99 with 24 vertices | `FVA-GEO-003` |
| repeated-index triangle | `FVA-GEO-006` |
| no NORMAL attribute | `FVA-GEO-007` |
| texture without TEXCOORD_0 | `FVA-GEO-013` |
| baseColorFactor 1.2 | `FVA-MAT-001` |
| `https://` image URI | `FVA-SEC-001` (not fetched; no digest) |
| skin joint 40 (missing) | `FVA-SKN-001` |
| key times 0, 1, 1, 0.5 | `FVA-ANM-003` |
| channel targeting node 99 | `FVA-ANM-001` |
| required `KHR_draco_mesh_compression` | `FVA-EXT-001` |

Demonstrated properties:

* **Successful inspection**: hierarchy, transforms, primitives, attributes, materials,
  textures (PNG 16×16 via header probing), skins with joint names and rest consistency,
  clips with duration, kinds and loop closure, morph targets, bounds, dependencies.
* **Correct defect detection**: table above; 43 negative and hostile-input tests (plus subtests) in `test_negative.py`.
* **Distinct embodiment handling**: the humanoid fits humanoid profiles and is refused as a
  floating spirit (grounded, `FS-03`); the wisp fits only the floating spirit (no skeleton
  required) and is refused as a fire elemental (cool emission, `FE-03`) and as grounded
  beings (`BS-03`, `NE-03`).
* **Machine-readable reports**: JSON Schema 2020-12 conformance tested for every fixture.
* **Deterministic findings**: identical bytes across runs, processes and hash seeds; the
  digest excludes only `generated_at`.
* **No Blender dependency**: the full pipeline runs with `bpy`, `bmesh`, `mathutils`
  and `numpy` imports blocked; no source file imports `bpy`.
* **Reproducible tests**: fixtures, schema and evidence are regenerated and compared in
  the test suite.

## Real Finalverse assets

14 GLBs from `finalverse/finalverse@3cd0e93`:

* 7 accepted E0 bodies: pass the reproduced `finalverse.humanoid/v1` admission (18/18
  rules); `biological_humanoid` compatible; 147 ms median per full report.
* 7 M8 generated assets: pass the reproduced EC static admission (16/16 rules); valid.
* **Defect found:** every E0 body omits animation-sampler input `min`/`max`
  (glTF 2.0 requirement), traced to `scripts/embodiment_blender.py` line 146. Recorded for
  Codex; not changed (repository not owned by S3-A).

## Security and robustness

* Fuzzing: 200,000 inputs on the committed tree, 0 crashes (plus 200,000 on the final
  source before commit, 0 crashes). Development fuzzing found and fixed 5 crash classes,
  including a memory-exhaustion path.
* Remote URIs are never fetched; path traversal and symlink escape are refused;
  oversized files are not read; a socket-blocking test confirms no network access.
* No sandbox is claimed: see [S3A-SECURITY.md](S3A-SECURITY.md).

## Performance

Inspection + full report, CPython 3.13: 2–7 ms for fixtures, 147 ms median for real E0
bodies, 197 ms for a 100,000-triangle mesh (the G0 triangle budget).

## Limitations and deviations

1. **Not integrated into Studio S2**; integration is a handoff (S0/S1/S2 not on GitHub).
2. **Rust oracles not executed**: building/running EC and E0 from `finalverse/finalverse`
   was not permitted in the cloud session. Profiles were validated against the real corpus
   and its acceptance evidence, plus rule-targeted mutations. The differential harness is
   provided for Codex ([S3A-TESTING.md](S3A-TESTING.md)).
3. **Infinity**: entry-reader rules are reproduced; the FinalStorm decoder was unavailable,
   so Infinity entry compatibility is at best `unverified`.
4. **E1**: no accepted E1 contract was available; non-humanoid embodiment requirements and
   humanoid capability recommendations are provisional and labelled as such.
5. **Quality tiers**: thresholds and the visual-evidence format (`v0`) are S3-A proposals
   awaiting review; Q2–Q4 cannot be certified without rendered evidence, by design.
6. **Numerics**: profiles compute in f64; EC/E0 use f32 for some thresholds.
7. **Not pushed or merged**: delivered as commits plus a git bundle and patch series;
   publishing to `finalverse/studio` awaits Finalverse authorization.
8. **Licensing** of the package inside the GPL Studio repository is undecided (no headers added).
