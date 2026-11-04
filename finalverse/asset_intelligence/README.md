# Finalverse Asset Intelligence (Studio S3-A)

Blender-independent inspection, validation, compatibility assessment, quality
assessment and advisory improvement proposals for glTF 2.0 / GLB assets.

* Pure Python 3.11+ standard library; no third-party runtime dependencies; never imports `bpy`.
* Deterministic, versioned JSON reports: `finalverse.asset-intelligence/v1`.
* Runtime profiles reproduce actual Finalverse admission code (EC static GLB, E0 humanoid,
  Infinity entry reader). Embodiment profiles cover humanoids and non-humanoid beings.
* Treats every asset as untrusted: bounded parsing, no network access, contained local reads.
* Recommendations are advisory and never modify assets.

## Use

```sh
pip install ./finalverse/asset_intelligence            # or: PYTHONPATH=finalverse/asset_intelligence/src
finalverse-asset inspect  body.glb
finalverse-asset validate body.glb --embodiment floating_spirit   # exit status reflects validity
finalverse-asset report   body.glb --json --out body.report.json
finalverse-asset profiles | codes
```

```python
from finalverse_asset_intelligence import inspect_path, report

model = inspect_path("body.glb")
rep = report(model, embodiment_profile="biological_humanoid", target="finalverse.humanoid/v1")
rep["validation"]["status"]     # valid | valid_exceeds_limits | invalid | refused
rep["proposals"]                # typed, advisory improvement proposals
```

## Develop

```sh
cd finalverse/asset_intelligence
python -m pytest -q                       # or: cd tests && python -m unittest
python tools/fuzz.py --iterations 50000   # mutation fuzzing
python tools/acceptance.py --check        # acceptance evidence is reproduced byte-for-byte
```

Documentation: [docs/](docs/) — architecture, report schema, embodiment compatibility,
security, testing, acceptance and the S2 integration handoff.
