# S3-A Testing

## Running

```sh
cd finalverse/asset_intelligence
python -m pytest -q                          # 89 tests (pytest config adds src/, tests/, tools/ to the path)
cd tests && python -m unittest discover -s . # stdlib runner, same tests
python tools/build_fixtures.py --check       # fixtures rebuild bit-for-bit
python tools/write_schema.py --check         # report schema is current
python tools/acceptance.py --check           # acceptance evidence reproduces byte-for-byte
python tools/fuzz.py --iterations 50000 --seed 1 --crash-dir /tmp/fva-crashes
python tools/bench.py
ruff check src tests tools && ruff format --check src tests tools
```

Optional dev dependencies: `pytest`, `hypothesis` (property tests; skipped if absent),
`jsonschema` (schema conformance; skipped if absent), `ruff`. The library itself needs none.

Environment knobs: `FINALVERSE_REPO` (path of a `finalverse/finalverse` checkout for the
real-corpus tests; skipped if absent), `FVA_FUZZ_ITERATIONS` (in-suite fuzz budget, default
1500), `FVA_HYPOTHESIS_EXAMPLES` (default 300).

## Required tests → implementation

| Required (S3-A brief §12) | Tests |
|---|---|
| Valid GLB | `test_acceptance_assets` (humanoid, wisp, static prop); 14 real GLBs in `test_real_corpus` |
| Valid glTF | `SupportingFixtures.test_textured_gltf_resolves_local_dependencies` (.gltf + .bin + PNG) |
| Corrupt header | `Containers.test_corrupt_header_version`, `test_not_gltf`, `test_misaligned_chunk`, `test_unsupported_version` |
| Truncated binary | `Containers.test_truncated_binary` (6 cut points), `test_truncated_with_patched_length_hits_chunk_bounds` |
| Invalid accessor | `Accessors.*` — out of bounds, bad component type, misalignment, bad stride, bounds mismatch/missing, view beyond buffer, NaN data, sparse |
| Invalid index | `Accessors.test_invalid_index` (also flips EC admission); defective fixture |
| Missing texture | `Materials.test_missing_local_texture`; texture/sampler references; MIME mismatch |
| Invalid skeleton | `Skeletons.*` — disconnected joints, IBM count, skeleton not ancestor, cycles/multiple parents, bind-pose mismatch, "names alone do not make a humanoid" |
| Invalid animation | `Animations.*` — output count, interpolation/path, duplicate channel, weights without morph targets, empty animation; defective fixture (non-increasing keys, missing node) |
| Unsupported extension | `Extensions.*` — required/used/declared consistency; optional extensions reported as unverified, not unsupported |
| Oversized asset | `Limits_.*` — file size (not read from disk), array length, decode budget (incomplete ⇒ refused), node depth, runtime budget (valid but exceeds limits) |
| Malicious external URI | `HostileUris.*` — 9 remote/traversal/absolute/drive/encoded cases, symlink escape, bytes input never reads files, data URIs |
| Stable report generation | `Determinism.*` (same bytes, cross-process with 3 hash seeds, digest excludes only the timestamp, report does not mutate the model, ordering), `GoldenEvidence.*` |
| Property-based / fuzz | `test_fuzz` (mutation campaign + Hypothesis property over arbitrary glTF-shaped JSON) and `tools/fuzz.py` |

Additional: JSON Schema conformance of every fixture report (`Schema.*`), CLI exit codes and
JSON output (`Cli.*`), no network / no `bpy` / inputs unmodified (`Isolation.*`), visual
evidence gating Q2–Q3 and tamper rejection (`VisualEvidence.*`).

## Real-corpus conformance (`test_real_corpus.py`)

Uses the GLBs committed in `finalverse/finalverse@3cd0e93` (read in place, not copied):

* 7 accepted E0 bodies (`examples/embodiment-e0/assets`) — all pass the reproduced
  `finalverse.humanoid/v1` profile (18 rules), are `biological_humanoid`-compatible and
  `floating_spirit`-incompatible; EC refuses them at `EC-04` as the real EC would.
* 7 M8 generated GLBs (`docs/m8/generated-assets`) — produced by `ec::geometry::generate`,
  which calls `validate_glb`; all pass the reproduced EC profile (16 rules).
* Rule-targeted mutations: 9 E0 rules (E0-04, -05, -06, -07, -09, -10, -11, -16, -17) and
  7 EC rules (EC-04, -05, -08, -09, -10, -11, -16) each fail on exactly the mutated rule.

**Finding from the corpus:** all seven accepted E0 bodies omit `min`/`max` on animation
sampler input accessors, which glTF 2.0 requires (`FVA-BUF-009`, 38 per body). Cause:
`scripts/embodiment_blender.py` writes sampler inputs with `acc(times, ...)` without
`minmax=True`. E0's own loader does not require the bounds, so E0 admission passes while
strict glTF validators fail. This is reported, not fixed (the repository is not S3-A's).

## Differential check against the Rust originals (for Codex)

The cloud session could not compile and run code from the other repositories, so the
reproduced profiles were validated against the corpus and its acceptance evidence rather
than by executing the Rust admission code. To run the differential check locally, create
a scratch crate next to a `finalverse/finalverse` checkout:

```toml
# Cargo.toml
[package]
name = "fva-oracle"
version = "0.0.0"
edition = "2024"
publish = false
[dependencies]
ec = { path = "../finalverse/crates/ec" }
finalverse-embodiment = { path = "../finalverse/crates/embodiment" }
serde_json = "1"
sha2 = "0.10"
[workspace]
```

```rust
// src/main.rs — prints one JSON line per GLB: the real EC and E0 verdicts
use sha2::{Digest, Sha256};
fn main() {
    for path in std::env::args().skip(1) {
        let bytes = std::fs::read(&path).expect("read");
        let digest = format!("{:x}", Sha256::digest(&bytes));
        let ec = ec::geometry::validate_glb(&bytes).err().map(|d| format!("{d:?}"));
        let e0 = finalverse_embodiment::Asset::load(&bytes, &digest).err();
        println!("{}", serde_json::json!({"path": path, "ec_error": ec, "e0_error": e0}));
    }
}
```

Then compare with S3-A over the fixtures, the corpus and a fuzz-mutated sample:

```sh
cargo run --release -- ../studio/finalverse/asset_intelligence/fixtures/*.glb > rust.jsonl
python - <<'EOF'
import json, sys
sys.path.insert(0, "../studio/finalverse/asset_intelligence/src")
from finalverse_asset_intelligence import report_for_path
for line in open("rust.jsonl"):
    r = json.loads(line); rep = report_for_path(r["path"])
    st = {p["id"]: p["status"] for p in rep["compatibility"]["runtime"]}
    ok = ((r["ec_error"] is None) == (st["finalverse.ec-static-glb/v1"] == "compatible")
          and (r["e0_error"] is None) == (st["finalverse.humanoid/v1"] == "compatible"))
    print("agree" if ok else "DISAGREE", r["path"])
EOF
```

Known source of possible disagreement: S3-A computes in f64; EC/E0 use f32 for some
geometric thresholds (degenerate area 1e-20, normal length, inverse-bind tolerance), so a
value within ~1e-6 of a threshold may classify differently.

## Fuzzing

`tools/fuzz.py` mutates the fixtures at byte level (header words, chunk lengths, flips,
truncation, insertion, cross-fixture splicing) and structurally (random JSON edits with
the BIN chunk preserved, injecting hostile values: huge integers, `1e308`, wrong types,
URIs, nested containers). Every input must produce a complete, `allow_nan=False`
serializable report with a known status.

| Campaign | Code | Inputs | Crashes |
|---|---|---|---|
| Development (seeds 7–16, iterative) | intermediate source | ~220,000 | 76 in the first 5,000 inputs; every crash class fixed (see S3A-SECURITY.md) |
| Definitive (seeds 201–204) | final source | 200,000 | 0 |
| Committed tree (seeds 301–304) | `d10fe0ae`, fresh worktree | 200,000 | 0 |

Throughput ≈ 320–350 inputs/s per process (CPython 3.13, cloud container).

## Performance (`tools/bench.py`, CPython 3.13, median of 3, inspect + full report)

| Asset | Size | Time |
|---|---|---|
| fixtures (static prop, wisp, defective) | 3–5 KB | 2–3 ms |
| humanoid fixture (26 joints, 5 clips) | 37 KB | 6.5 ms |
| real E0 bodies (26 joints, 12 clips, 2.5k–4.6k triangles) | 0.4–0.75 MB | 147 ms median, 158 ms max |
| real M8 generated assets | ≤ 0.1 MB | 7 ms median |
| generated grid at the G0 triangle budget | 2.8 MB, 100,000 triangles | 197 ms |
