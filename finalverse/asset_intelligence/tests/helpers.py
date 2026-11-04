from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import build_fixtures  # noqa: E402,F401  (tools/, re-exported for tests)
import fuzz  # noqa: E402,F401
from finalverse_asset_intelligence import (  # noqa: E402
    Limits,
    RuntimeBudget,
    cli,
    inspect_bytes,
    inspect_path,
    report,
)
from finalverse_asset_intelligence.findings import CATALOGUE  # noqa: E402
from finalverse_asset_intelligence.limits import BudgetValue  # noqa: E402
from finalverse_asset_intelligence.reporting import digest, dumps  # noqa: E402

FIXTURES = ROOT / "fixtures"
TS = "2026-11-04T00:00:00Z"
FINALVERSE_REPO = Path(os.environ.get("FINALVERSE_REPO", "/home/user/fv-main"))


def rep_bytes(data: bytes, name="t.glb", limits=None, budget=None, **kw):
    m = inspect_bytes(data, name, limits=limits, budget=budget)
    return m, report(m, generated_at=TS, **kw)


def rep_path(path, limits=None, budget=None, **kw):
    m = inspect_path(path, limits, budget)
    return m, report(m, generated_at=TS, **kw)


def codes(rep) -> set[str]:
    return {f["code"] for f in rep["findings"]}


def glb_json(data: bytes) -> dict:
    n = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20 : 20 + n])


def replace_json(data: bytes, doc: dict | str) -> bytes:
    """Re-wrap a GLB with a new JSON chunk, keeping its BIN chunk."""
    n = struct.unpack_from("<I", data, 12)[0]
    rest = data[20 + n :]
    j = (doc if isinstance(doc, str) else json.dumps(doc, separators=(",", ":"))).encode("utf-8")
    j += b" " * (-len(j) % 4)
    body = struct.pack("<I4s", len(j), b"JSON") + j + rest
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def finding(rep, code):
    return [f for f in rep["findings"] if f["code"] == code]


__all__ = [
    "BudgetValue",
    "CATALOGUE",
    "cli",
    "digest",
    "dumps",
    "FIXTURES",
    "FINALVERSE_REPO",
    "Limits",
    "RuntimeBudget",
    "TS",
    "codes",
    "finding",
    "glb_json",
    "rep_bytes",
    "rep_path",
    "replace_json",
]
