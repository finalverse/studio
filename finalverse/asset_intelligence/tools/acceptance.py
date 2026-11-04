"""Regenerate acceptance evidence by executing the real CLI.

    python tools/acceptance.py           # write acceptance/
    python tools/acceptance.py --check   # verify committed evidence is reproduced exactly

Writes acceptance/reports/*.report.json (full v1 reports), acceptance/transcript.txt
(commands, stdout, exit codes) and acceptance/summary.json.  Every report is produced
by a subprocess running ``python -m finalverse_asset_intelligence`` on the committed
fixtures with a fixed --timestamp, so the evidence is byte-reproducible.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "acceptance"
TS = "2026-11-04T00:00:00Z"
CASES = [
    ("humanoid_walker.glb", ["--embodiment", "biological_humanoid"]),
    ("floating_wisp.glb", ["--embodiment", "floating_spirit"]),
    ("defective_creature.glb", []),
    ("static_prop.glb", ["--target", "finalverse.ec-static-glb/v1"]),
    ("textured_crate.gltf", []),
]


def run(args: list[str]) -> tuple[int, str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONHASHSEED": "0"}
    env.pop("SOURCE_DATE_EPOCH", None)
    p = subprocess.run(
        [sys.executable, "-m", "finalverse_asset_intelligence", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stdout


def generate() -> dict[str, str]:
    files: dict[str, str] = {}
    transcript = []
    summary = []
    for name, extra in CASES:
        asset = f"fixtures/{name}"
        rc, out = run(["report", asset, "--json", "--timestamp", TS, *extra])
        assert rc == 0, (name, rc)
        rep = json.loads(out)
        files[f"reports/{Path(name).stem}.report.json"] = out
        for cmd in (["validate", asset, *extra], ["report", asset, *extra]):
            rc, text = run([*cmd, "--timestamp", TS])
            transcript.append(f"$ finalverse-asset {' '.join(cmd)}\n{text}[exit {rc}]\n")
        summary.append(
            {
                "asset": name,
                "asset_sha256": rep["asset"]["sha256"],
                "status": rep["validation"]["status"],
                "finding_codes": sorted({f["code"] for f in rep["findings"]}),
                "runtime": {r["id"]: r["status"] for r in rep["compatibility"]["runtime"]},
                "embodiment": {e["profile"]: e["status"] for e in rep["compatibility"]["embodiment"]},
                "tier": rep["quality"]["tier"]["certified"],
                "report_digest": rep["report_digest"],
                "report_file_sha256": hashlib.sha256(out.encode()).hexdigest(),
            }
        )
    files["transcript.txt"] = "\n".join(transcript)
    files["summary.json"] = json.dumps({"generated_at": TS, "assets": summary}, indent=2, sort_keys=True) + "\n"
    return files


def main() -> int:
    files = generate()
    if "--check" in sys.argv:
        bad = [k for k, v in files.items() if not (OUT / k).is_file() or (OUT / k).read_text() != v]
        print("acceptance evidence reproduced exactly" if not bad else f"differs: {bad}")
        return 1 if bad else 0
    for k, v in files.items():
        (OUT / k).parent.mkdir(parents=True, exist_ok=True)
        (OUT / k).write_text(v)
        print(f"wrote acceptance/{k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
