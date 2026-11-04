# S3-A Architecture — Finalverse Asset Intelligence

Status: implemented on branch `s3a/asset-intelligence` of `finalverse/studio`
(see [S3A-ACCEPTANCE.md](S3A-ACCEPTANCE.md) for commits). Version `0.1.0`.

## Purpose and boundary

S3-A gives Finalverse Studio a deterministic way to understand a generated 3D asset:
what it contains, whether it is valid glTF 2.0, whether the Finalverse runtimes can
consume it, which embodiment it is fit for, how complete it is, and what should be
improved. It sits between Blender export (S2) and Genesis validation:

```
Studio S2 (Blender) ── GLB ──▶ S3-A Asset Intelligence ──▶ report + proposals ──▶ S2 refinement
                                         │
                                         └──▶ (unchanged) Genesis validation ──▶ SpatialDB ──▶ Infinity
```

S3-A deliberately does **not**:

* replace Genesis/EC validation or the E0 loader — it *reproduces* their rules so a
  Studio author learns early what they will refuse, and it says so when it cannot verify;
* register, publish or store assets — it is not an asset registry;
* modify assets — every recommendation is advisory (`modifies_asset: false`);
* render — subjective quality needs rendered evidence produced elsewhere (S2/S3-B).

## Evidence base

Inspected GitHub state (S0/S1 commits were **not** on GitHub; `finalverse/studio` `main`
was upstream Blender at `0f5a1ae`):

| Repository | Commit | Used for |
|---|---|---|
| finalverse/finalverse | `3cd0e93` | EC `validate_glb` (G0 static GLB subset), E0 `Asset::load`, `E0-HUMANOID-STANDARD.md`, G0 budgets, 14 real GLBs |
| finalverse/infinity | `664445f` | `src/entry.rs` `decode_parts` (network entry reader), `src/bin/embodiment-render.rs` (E0 path) |
| finalverse/studio | `0f5a1ae` | Blender's bundled Python version (3.13.13) — package targets 3.11+ |

Not available: accepted E1 contracts, FinalStorm's `glb::decode` (Infinity's
`vendor/finalstorm` is a separate repository), SpatialDB. Everything that depends on
them is marked `unverified` or `provisional` — never `supported`/`unsupported` by guess.

## Package layout

```
finalverse/asset_intelligence/
├── pyproject.toml            # no runtime dependencies; console script finalverse-asset
├── src/finalverse_asset_intelligence/
│   ├── container.py          # GLB/glTF container parsing, resource resolution and URI policy
│   ├── jsonstrict.py         # bounded strict JSON (depth pre-scan, duplicates, non-finite)
│   ├── accessors.py          # bufferView/accessor validation and bounded decoding
│   ├── imageinfo.py          # header-only PNG/JPEG/WebP/KTX2 probing (no pixel decode)
│   ├── analyze.py            # the inspector: one pass producing Model + findings
│   ├── findings.py           # stable finding catalogue (codes never renumbered)
│   ├── limits.py             # inspection safety Limits vs. Finalverse RuntimeBudget
│   ├── profiles.py           # runtime profiles reproducing EC, E0 and Infinity admission
│   ├── embodiment.py         # six embodiment profiles (accepted E0 rig + provisional)
│   ├── quality.py            # quality categories, tiers Q0–Q4, visual-evidence loader
│   ├── proposals.py          # typed advisory improvement proposals
│   ├── reporting.py          # finalverse.asset-intelligence/v1 assembly and digest
│   └── cli.py                # finalverse-asset inspect | validate | report | profiles | codes
├── schema/                   # generated JSON Schema of the report
├── fixtures/                 # deterministic synthetic fixtures (tools/build_fixtures.py)
├── tests/                    # unittest/pytest suites
├── tools/                    # fixture builder, fuzzer, acceptance generator, bench, schema
├── acceptance/               # CLI-produced reports and transcript (byte-reproducible)
└── docs/                     # this documentation
```

## Data flow

1. **Container** (`container.py`): GLB header/chunks or UTF-8 JSON. Truncation,
   bad magic/version, misplaced chunks and misalignment are distinct findings.
2. **Strict JSON** (`jsonstrict.py`): nesting depth is measured with a token scan
   *before* `json.loads`, so depth bombs never reach the recursive parser; duplicate keys
   and non-finite numbers (`1e400`, `NaN`) become findings rather than silent values.
3. **Inspector** (`analyze.py`): asset version → extensions → buffers (with the URI
   policy) → bufferViews/accessors → images/samplers/textures → materials → meshes and
   primitives → nodes/hierarchy/transforms → scenes → skins → animations → unused
   resources → bounds → metrics and budget checks. Each step records findings with a
   JSON-pointer component and continues; only container-level failures abort.
4. **Profiles** (`profiles.py`, `embodiment.py`): independent evaluators over the raw
   bytes (runtime) or the inspected model (embodiment).
5. **Quality, proposals, report** (`quality.py`, `proposals.py`, `reporting.py`).

`report()` never mutates the inspected `Model`: report-level findings (target profile,
selected embodiment, evidence) are added to a copy.

## Key design decisions

* **Stdlib only, Python ≥ 3.11.** Blender ships Python 3.13.13 (Studio
  `build_files/build_environment/cmake/versions.cmake`); the package imports cleanly into
  Blender's interpreter, CI, Genesis tooling or a plain venv. NumPy is not required.
* **Two kinds of limits.** `Limits` protect the inspector (refusal ⇒ status `refused`,
  inspection incomplete). `RuntimeBudget` encodes Finalverse runtime limits (exceeding ⇒
  `valid_exceeds_limits`). Each budget value carries its basis (G0 budget, Infinity
  reader, E0 loader, or "provisional").
* **Spec validity ≠ Finalverse compatibility.** `validation.status` speaks only to glTF
  validity, safety and budgets. Runtime/embodiment compatibility is reported separately,
  so a valid asset that EC refuses is still `valid`.
* **Reproduced, not assumed, admission.** Runtime profiles mirror the original Rust
  routines rule-by-rule in their original order with first-failure semantics, including
  serde_json's integer/float distinction. Differences (f64 vs f32 arithmetic near
  thresholds) are documented; a differential harness for the Rust originals is in
  [S3A-TESTING.md](S3A-TESTING.md).
* **Determinism.** Findings are sorted by (severity, code, component); floats are rounded
  to 6 decimals; canonical JSON (sorted keys) is digested excluding only `generated_at`.
  Same bytes in ⇒ same report bytes out, across processes and hash seeds.
* **Honest quality.** Polygon count and file size never raise a quality score. Visual
  reference alignment and artistic coherence remain `not_assessed` unless a
  digest-verified render set with assessments is supplied, and Q2–Q4 are never certified
  without it.

## Extension points

* New runtime profile: add an evaluator to `profiles.RUNTIME_PROFILES`.
* New embodiment profile or E1 replacement: edit `embodiment.PROFILES` (requirements are
  data + small check functions; `basis` records accepted vs provisional).
* New finding: append to `findings.py` (never reuse a code), regenerate the schema with
  `tools/write_schema.py`.
* S3-B (visual evaluation) plugs in by producing `finalverse.visual-evidence/v0` files.
