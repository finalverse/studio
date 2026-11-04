"""Measure inspection + report time on fixtures and a generated budget-scale mesh.

python tools/bench.py [--triangles 100000] [--repeat 5]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from finalverse_asset_intelligence import inspect_bytes, report  # noqa: E402
from gltf_builder import Builder  # noqa: E402


def grid(triangles: int) -> bytes:
    side = max(1, int((triangles / 2) ** 0.5))
    b = Builder()
    pos, nrm, uv, idx = [], [], [], []
    for z in range(side + 1):
        for x in range(side + 1):
            pos.append((x / side, 0.0, z / side))
            nrm.append((0.0, 1.0, 0.0))
            uv.append((x / side, z / side))
    w = side + 1
    for z in range(side):
        for x in range(side):
            a = z * w + x
            idx += [a, a + w, a + 1, a + 1, a + w, a + w + 1]
    b.add("materials", {"pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.5, 0.5, 1.0]}})
    b.add(
        "meshes",
        {
            "primitives": [
                {
                    "attributes": {
                        "POSITION": b.accessor(pos, 5126, "VEC3", minmax=True),
                        "NORMAL": b.accessor(nrm, 5126, "VEC3"),
                        "TEXCOORD_0": b.accessor(uv, 5126, "VEC2"),
                    },
                    "indices": b.accessor(idx, 5125, "SCALAR"),
                    "material": 0,
                }
            ]
        },
    )
    b.add("nodes", {"mesh": 0})
    b.doc["scenes"], b.doc["scene"] = [{"nodes": [0]}], 0
    return b.glb()


def measure(data: bytes, name: str, repeat: int) -> dict:
    times = []
    for _ in range(repeat):
        t = time.perf_counter()
        report(inspect_bytes(data, name), generated_at="x")
        times.append(time.perf_counter() - t)
    return {"asset": name, "bytes": len(data), "median_ms": round(statistics.median(times) * 1000, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triangles", type=int, default=100_000)
    ap.add_argument("--repeat", type=int, default=5)
    a = ap.parse_args()
    rows = [measure(p.read_bytes(), p.name, a.repeat) for p in sorted((ROOT / "fixtures").glob("*.glb"))]
    rows.append(measure(grid(a.triangles), f"grid_{a.triangles}_triangles.glb", a.repeat))
    print(json.dumps({"python": sys.version.split()[0], "results": rows}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
