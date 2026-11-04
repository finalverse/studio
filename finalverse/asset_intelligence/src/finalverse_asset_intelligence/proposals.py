"""Advisory improvement proposals derived from findings.

Proposals never modify assets.  Each one references the finding(s) that justify
it, the affected component, a corrective action, the expected impact, a
confidence level and the validation required before the change is accepted.
"""

from __future__ import annotations

from typing import Any

from .findings import SEVERITY_RANK, Finding


def build(findings: list[Finding], include_info: bool = True) -> list[dict[str, Any]]:
    """One proposal per finding code; repeats of the same code are grouped as components.

    Profile (FVA-CMP-*) and embodiment (FVA-EMB-*) findings carry rule-specific actions and
    are never grouped.
    """
    groups: dict[str, list[Finding]] = {}
    order: list[str] = []
    for f in findings:
        if f.severity == "info" and not include_info:
            continue
        key = f.id if f.code.startswith(("FVA-CMP-", "FVA-EMB-")) else f.code
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(f)
    out = []
    for key in order:
        fs = groups[key]
        f = fs[0]
        meta = f.meta
        action = meta.action
        if f.code == "FVA-CMP-001":
            ev = f.evidence
            action = f"{action} Failed rule {ev.get('rule')}: {ev.get('requirement')} ({ev.get('detail')})."
        elif f.code.startswith("FVA-EMB-"):
            action = f"{action} {f.message}."
        severity = min((x.severity for x in fs), key=lambda s: SEVERITY_RANK[s])
        out.append(
            {
                "id": f"P-{f.code}" if len(fs) > 1 or key == f.code else f"P-{f.id}",
                "finding_ids": [x.id for x in fs],
                "severity": severity,
                "category": meta.category,
                "class": meta.cls,
                "component": f.pointer or "/",
                "components": [x.pointer or "/" for x in fs],
                "evidence": {"message": f.message, "occurrences": len(fs), **f.evidence},
                "action": action,
                "expected_impact": meta.impact,
                "confidence": meta.confidence,
                "required_validation": list(meta.validation),
                "advisory": True,
                "modifies_asset": False,
            }
        )
    out.sort(key=lambda p: (SEVERITY_RANK[p["severity"]], p["id"]))
    return out
