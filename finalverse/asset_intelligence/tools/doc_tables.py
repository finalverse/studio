"""Print Markdown tables generated from the source of truth (codes, profiles, rules).

python tools/doc_tables.py codes|runtime|embodiment
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from finalverse_asset_intelligence.embodiment import PROFILES  # noqa: E402
from finalverse_asset_intelligence.findings import CATALOGUE  # noqa: E402
from finalverse_asset_intelligence.profiles import E0_RULES, EC_RULES, INF_RULES  # noqa: E402


def codes() -> str:
    rows = ["| Code | Name | Class | Default severity |", "|---|---|---|---|"]
    rows += [f"| `{c.code}` | {c.name} | {c.cls} | {c.severity} |" for c in CATALOGUE.values()]
    return "\n".join(rows)


def runtime() -> str:
    out = []
    for title, rules in (
        ("`finalverse.ec-static-glb/v1`", EC_RULES),
        ("`finalverse.humanoid/v1`", E0_RULES),
        ("`infinity.entry-glb/observed`", INF_RULES),
    ):
        out += [f"#### {title}", "", "| Rule | Requirement |", "|---|---|"]
        out += [f"| {rid} | {text} |" for rid, text in rules]
        out.append("")
    return "\n".join(out)


def embodiment() -> str:
    out = []
    for pid, p in PROFILES.items():
        out += [f"#### `{pid}` ({p['title']})", "", f"Skeleton: {p['skeleton']}. Contract: {p['contract_status']}.", ""]
        out += ["| Id | Level | Basis | Requirement |", "|---|---|---|---|"]
        out += [f"| {r.id} | {r.level} | {r.basis.split(' ')[0]} | {r.text} |" for r in p["requirements"]]
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    print({"codes": codes, "runtime": runtime, "embodiment": embodiment}[sys.argv[1]]())
