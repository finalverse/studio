# S3-A → S2 Integration Handoff (for Codex on the Mac)

S3-A was built in a cloud session that could see only GitHub state. `finalverse/studio`
on GitHub was upstream Blender (`0f5a1ae`); **none of the accepted S0/S1 work and none
of the active S2 work was visible**. S3-A therefore ships as a standalone package plus
this handoff. It has **not** been integrated into Studio S2, and no Studio integration
test has been run.

## 1. What is delivered

Branch `s3a/asset-intelligence`, based on `finalverse/studio@0f5a1ae`, adding only
`finalverse/asset_intelligence/` (no other path in the repository is touched):

| Commit | Content |
|---|---|
| `ba1f3ce5` | library: `src/finalverse_asset_intelligence`, `pyproject.toml`, `README.md`, package `.gitignore` |
| `d10fe0ae` | fixtures, tests, tools (fuzzer, fixture builder, acceptance, bench, schema), generated JSON Schema, acceptance evidence, package `.gitattributes` |
| docs commit | `docs/S3A-*.md` (this commit; its SHA is reported with the delivery) |

Exact SHAs, digests and results: [S3A-ACCEPTANCE.md](S3A-ACCEPTANCE.md).

## 2. Retrieving the work

A cloud-local SHA is not retrievable on its own, so the delivery includes durable artifacts:

* **Git bundle** `s3a-asset-intelligence.bundle` (prerequisite: `0f5a1ae`, upstream
  Blender `main` at the time). In a Studio checkout that contains `0f5a1ae`:
  ```sh
  git bundle verify s3a-asset-intelligence.bundle
  git fetch s3a-asset-intelligence.bundle s3a/asset-intelligence:s3a/asset-intelligence
  ```
* **Patch series** `s3a-patches/*.patch` (`git format-patch --binary`). Applies to *any*
  Studio base because it only adds a new directory, so use this on top of the accepted
  local S1/S2 baseline:
  ```sh
  git switch -c s3a/asset-intelligence <your-accepted-baseline>
  git am --3way s3a-patches/*.patch
  ```
* Or, once Finalverse authorizes it, the branch can be pushed to `finalverse/studio` and
  fetched normally.

**Git LFS:** Studio's `.gitattributes` routes `*.glb/*.gltf/*.bin/*.png` through LFS.
S3-A's fixtures are small and are committed as regular blobs via
`finalverse/asset_intelligence/.gitattributes` (`fixtures/** -filter -diff -merge -text`)
so that bundles and patches carry the real bytes. If Studio policy requires LFS for all
binaries, remove that override and run `git lfs migrate` on the branch.
After retrieval, always run `python tools/build_fixtures.py --check` (it fails if any
fixture is an LFS pointer or differs by a byte). While `git am` applies the test patch,
git-lfs may print "Encountered 7 files that should have been pointers": the override
`.gitattributes` arrives in the same patch, and the resulting tree is identical to the
branch (verified by applying the series onto `0f5a1ae` with LFS active).

## 3. Verify the source before integrating

```sh
cd finalverse/asset_intelligence
python3 -m pip install pytest hypothesis jsonschema ruff   # dev only; the library has no dependencies
FINALVERSE_REPO=~/Finalverse/finalverse python3 -m pytest -q   # expect 89 passed
python3 tools/build_fixtures.py --check && python3 tools/write_schema.py --check && python3 tools/acceptance.py --check
python3 tools/fuzz.py --iterations 20000 --seed 1
```

Then run the Rust differential check described in [S3A-TESTING.md](S3A-TESTING.md)
against your local `finalverse/finalverse`; it could not be executed in the cloud.

## 4. Integration into S2

### Placement in the pipeline

```
S2 AI creation ─▶ Blender build/rig/animate ─▶ glTF export ─▶ S3-A report ─┬─▶ S2 refinement loop (proposals)
                                                                         └─▶ Genesis validation (unchanged) ─▶ SpatialDB ─▶ Infinity
```

S3-A is advisory: it must not replace Genesis/EC admission or the E0 loader, and it never
edits the asset. S2 decides which proposals to act on.

### Using it inside Blender (no install)

The package is stdlib-only and Blender-independent; Blender 5.x ships Python 3.13, which
it supports. In the S2 code that runs inside Blender (not in the S1 provider registry,
MCP server or execution bridge, which S3-A has not touched):

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(STUDIO_ROOT, "finalverse/asset_intelligence/src")))
from finalverse_asset_intelligence import report_for_path

bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB")
rep = report_for_path(out_path, embodiment_profile=intended_embodiment,   # e.g. "floating_spirit"
                      target="finalverse.humanoid/v1" if is_e0_body else None)
status = rep["validation"]["status"]          # valid | valid_exceeds_limits | invalid | refused
for p in rep["proposals"]:                    # show or feed into the refinement planner
    print(p["severity"], p["component"], p["action"])
```

Alternatively install it into Blender's Python
(`"$BLENDER_PYTHON" -m pip install ./finalverse/asset_intelligence`) or a separate venv
and call the CLI as a subprocess (`finalverse-asset report out.glb --json`). The
subprocess route also isolates untrusted assets from the Blender process (see
[S3A-SECURITY.md](S3A-SECURITY.md)).

### Suggested gate semantics for S2

| Report | Suggested S2 behaviour |
|---|---|
| `validation.status == "invalid"` | not exportable; refine (proposals of class `spec`) |
| `"refused"` | not exportable; external/remote dependency or inspection incomplete |
| `"valid_exceeds_limits"` | exportable for preview; refine before publication (class `limit`) |
| target profile `incompatible` | refine against the failed rule (`FVA-CMP-001` proposal) before Genesis |
| embodiment `incompatible` | wrong body for the intended resident (`FVA-EMB-001`) |
| `quality.tier.certified` ≥ Q2 | only with S2/S3-B rendered evidence (`--visual-evidence`) |

CLI exit codes for CI: 0 valid, 4 exceeds limits, 1 invalid, 3 refused, 5 `--target`
refuses, 2 usage/I/O.

### Exporter settings that avoid common findings

Export normals (`FVA-GEO-007`), triangulate or let the exporter emit triangles
(`FVA-GEO-010`), apply transforms on skinned meshes (`FVA-SCN-007`), apply the rest pose
before binding (`FVA-SKN-009`, required by `finalverse.humanoid/v1`), limit/normalize
weights to 4 influences (`FVA-SKN-007`), embed textures (GLB) instead of external files
(`FVA-DEP-002`), and keep animation sampler input bounds (the glTF exporter writes them;
the E0 generator script does not — see below).

## 5. Open items for Codex

1. **Run the Rust differential** (EC `validate_glb`, E0 `Asset::load`) over fixtures, the
   corpus and a fuzz sample; report disagreements.
2. **Blender-generated GLBs:** run S2 exports (humanoid, spirit, elemental) through S3-A;
   commit representative ones as additional fixtures if licensing allows.
3. **Infinity:** verify `finalstorm_spatialdb::glb::decode` (vendor/finalstorm) and promote
   rule `INF-09` from `unverified`; run the Blender vs Infinity rendering conformance.
4. **E1:** when E1 contracts are accepted, replace the provisional embodiment requirements
   (each has a `basis` label) and add any E1 loader as a runtime profile.
5. **E0 generator defect (not fixed by S3-A):** `finalverse/finalverse`
   `scripts/embodiment_blender.py` writes animation sampler inputs without `min`/`max`
   (`acc(times, ...)` lacks `minmax=True`). All seven accepted E0 GLBs are therefore
   invalid glTF 2.0 (`FVA-BUF-009`, 38 accessors each) although E0 admits them.
   Fixing it changes the GLB bytes, so the pinned `geometry_sha256` values change too.
6. **Licensing:** the package lives inside the Studio repository (GPL as a whole). It
   neither imports nor links Blender code, and no license header has been added. Finalverse
   should decide its license and add SPDX headers accordingly.
7. **Possible path collision:** if accepted S1/S2 commits already contain
   `finalverse/asset_intelligence/`, keep S3-A's content in that directory and resolve by
   path; S3-A touches nothing else.

## 6. After S3-A

S3-B (visual evaluation and improvement planning) can produce
`finalverse.visual-evidence/v0` files (renders + assessments) that S3-A already
consumes for Q2–Q4 gating, and can rank proposals by budget and expected impact.
