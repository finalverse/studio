"""Quality model: deterministic metrics, evidence-based subjective assessment, tiers.

Deterministic categories are computed only from inspection results.  Subjective
categories (visual reference alignment, artistic coherence) are *never* derived
from polygon count, file size or any other proxy: they are ``not_assessed``
unless a visual-evidence file with digest-verified renders is supplied.

Tiers Q2-Q4 cannot be certified without such evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import imageinfo

TIERS = {
    "Q0": "Placeholder",
    "Q1": "Stylized prototype",
    "Q2": "Production stylized",
    "Q3": "Cinematic stylized",
    "Q4": "High-fidelity realistic",
}
EVIDENCE_SCHEMA = "finalverse.visual-evidence/v0"
CATEGORY_FINDINGS = {
    "geometry_integrity": {"geometry", "buffer", "scene", "container"},
    "material_completeness": {"material", "dependency"},
    "animation_integrity": {"animation", "skin"},
}
PENALTY = {"critical": 1.0, "error": 0.35, "warning": 0.1, "info": 0.0}


def effective_category(f) -> str:
    """Accessor findings caused by an animation sampler count against animation integrity."""
    if str(f.evidence.get("used_by", "")).startswith("/animations"):
        return "animation"
    return f.meta.category


def _penalized(findings, cats: set[str]) -> tuple[float, list[str]]:
    """Penalize each distinct defect (code) once at its worst severity; repeats do not compound."""
    rel = [f for f in findings if effective_category(f) in cats and f.severity != "info"]
    worst: dict[str, str] = {}
    for f in rel:
        if f.code not in worst or PENALTY[f.severity] > PENALTY[worst[f.code]]:
            worst[f.code] = f.severity
    score = 1.0 - sum(PENALTY[sev] for sev in worst.values())
    if any(sev in ("critical", "error") for sev in worst.values()):
        score = min(score, 0.5)
    return round(max(0.0, min(1.0, score)), 4), sorted(worst)


def _cat(score, status, method, explanation, basis=None) -> dict[str, Any]:
    return {"score": score, "status": status, "method": method, "explanation": explanation, "basis": basis or []}


def assess(
    m, findings, embodiment: list[dict], selected_embodiment: str | None, evidence: dict | None
) -> dict[str, Any]:
    cats: dict[str, Any] = {}
    if m.aborted:
        for k in (
            "geometry_integrity",
            "material_completeness",
            "animation_integrity",
            "embodiment_compatibility",
            "runtime_complexity",
            "visual_reference_alignment",
            "artistic_coherence",
        ):
            cats[k] = _cat(None, "not_assessed", "deterministic", "Inspection did not complete.")
        return {"categories": cats, "tier": _tiers(m, cats, findings, None)}

    s, basis = _penalized(findings, CATEGORY_FINDINGS["geometry_integrity"])
    cats["geometry_integrity"] = _cat(
        s,
        "assessed",
        "deterministic",
        "1.0 minus a penalty per distinct geometry/buffer/scene/container defect code "
        "(critical 1.0, error 0.35, warning 0.1); capped at 0.5 when any error is present.",
        basis,
    )

    checklist = _material_checklist(m, findings)
    ratio = sum(1 for v in checklist.values() if v) / len(checklist) if checklist else 0.0
    pen, basis = _penalized(findings, CATEGORY_FINDINGS["material_completeness"])
    score = round(min(ratio, pen), 4)
    cats["material_completeness"] = _cat(
        score,
        "assessed",
        "deterministic",
        "Fraction of the material checklist satisfied, capped by material findings.",
        basis,
    )
    cats["material_completeness"]["checklist"] = checklist

    if not m.animations:
        cats["animation_integrity"] = _cat(None, "not_applicable", "deterministic", "The asset has no animations.")
    else:
        valid = sum(1 for a in m.animations if a["valid"]) / len(m.animations)
        pen, basis = _penalized(findings, CATEGORY_FINDINGS["animation_integrity"])
        cats["animation_integrity"] = _cat(
            round(min(valid, pen), 4),
            "assessed",
            "deterministic",
            "Fraction of valid animations, capped by animation/skin findings.",
            basis,
        )

    if selected_embodiment:
        e = next((x for x in embodiment if x["profile"] == selected_embodiment), None)
        if e is None or e["status"] == "unverified":
            cats["embodiment_compatibility"] = _cat(
                None, "not_assessed", "deterministic", "Selected embodiment could not be verified."
            )
        else:
            rec = [r for r in e["requirements"] if r["level"] == "recommended"]
            met = sum(1 for r in rec if r["outcome"] == "pass")
            sc = 0.0 if e["status"] == "incompatible" else round(0.6 + 0.4 * (met / len(rec) if rec else 1.0), 4)
            cats["embodiment_compatibility"] = _cat(
                sc,
                "assessed",
                "deterministic",
                "0 when a required rule fails; otherwise 0.6 + 0.4 x fraction of recommendations met.",
                [f"{selected_embodiment}"],
            )
    else:
        fit = [x["profile"] for x in embodiment if x["status"] == "compatible"]
        cats["embodiment_compatibility"] = _cat(
            None,
            "not_assessed",
            "deterministic",
            "No embodiment selected (--embodiment). Compatible profiles: " + (", ".join(fit) or "none") + ".",
        )

    worst, detail = _budget_ratio(m)
    sc = 1.0 if worst <= 0.5 else max(0.0, 1.0 - (worst - 0.5) / 1.5)
    cats["runtime_complexity"] = _cat(
        round(sc, 4),
        "assessed",
        "deterministic",
        "1.0 up to 50% of the tightest budget, falling linearly to 0 at 200%.",
        [f"{k}={v}" for k, v in detail],
    )

    ev = evidence if evidence and evidence.get("valid") else None
    for key in ("visual_reference_alignment", "artistic_coherence"):
        if ev is None:
            cats[key] = _cat(
                None,
                "not_assessed",
                "evidence",
                "Subjective category: requires rendered visual evidence (--visual-evidence). "
                "Not inferred from geometry statistics.",
            )
        else:
            vals = [a[key] for a in ev["assessments"]]
            cats[key] = _cat(
                round(sum(vals) / len(vals), 4),
                "assessed",
                "evidence",
                f"Mean of {len(vals)} assessment(s) over digest-verified renders.",
                [a["assessor"] for a in ev["assessments"]],
            )
    return {"categories": cats, "tier": _tiers(m, cats, findings, ev)}


def _material_checklist(m, findings) -> dict[str, bool]:
    codes = {f.code for f in findings}
    prims = m.prims
    used = sorted({p.material for p in prims if p.material is not None})
    mats = [m.materials[i] for i in used if i < len(m.materials)]
    tri = [p for p in prims if p.mode in (4, 5, 6)]
    return {
        "explicit_material_on_every_primitive": bool(prims) and all(p.material is not None for p in prims),
        "base_color_defined": bool(mats)
        and all("baseColorFactor" in mt["explicit"] or "baseColorTexture" in mt["textures"] for mt in mats),
        "metallic_roughness_defined": bool(mats)
        and all(
            ("metallicFactor" in mt["explicit"] and "roughnessFactor" in mt["explicit"])
            or "metallicRoughnessTexture" in mt["textures"]
            for mt in mats
        ),
        "vertex_normals_present": bool(tri) and all("NORMAL" in p.attributes for p in tri),
        "texture_dependencies_complete": not codes
        & {"FVA-MAT-004", "FVA-MAT-005", "FVA-DEP-001", "FVA-SEC-001", "FVA-SEC-002"},
        "uv_sets_present_for_textures": "FVA-GEO-013" not in codes,
    }


def _budget_ratio(m) -> tuple[float, list[tuple[str, float]]]:
    b, mt = m.budget, m.metrics
    pairs = [
        ("triangles", b.max_triangles),
        ("vertices", b.max_vertices),
        ("file_bytes", b.max_file_bytes),
        ("draw_calls", b.max_draw_calls),
        ("materials", b.max_materials),
        ("joints", b.max_joints),
        ("nodes", b.max_nodes),
        ("max_texture_dimension", b.max_texture_dimension),
    ]
    ratios = [(k, round(mt.get(k, 0) / v.value, 4) if v.value else 0.0) for k, v in pairs]
    ratios.sort(key=lambda kv: (-kv[1], kv[0]))
    return (ratios[0][1] if ratios else 0.0), ratios[:3]


def _tiers(m, cats, findings, ev) -> dict[str, Any]:
    def score(k):
        return cats[k]["score"]

    spec_ok = not m.aborted and not any(
        f.meta.cls in ("spec", "security") and f.severity in ("critical", "error") for f in findings
    )
    complete = m.complete
    within = not any(f.meta.cls == "limit" for f in findings)
    anim = cats["animation_integrity"]
    anim_ok = anim["status"] == "not_applicable" or (anim["score"] or 0) >= 0.8
    renders = len(ev["renders"]) if ev else 0
    humans = sum(1 for a in ev["assessments"] if a["kind"] == "human") if ev else 0
    style = ev.get("style") if ev else None
    textured = any(mt["textures"] for mt in m.materials)
    pbr_tex = any(
        {"baseColorTexture", "normalTexture", "metallicRoughnessTexture"} <= set(mt["textures"]) for mt in m.materials
    )
    va, ac = (score("visual_reference_alignment"), score("artistic_coherence"))

    criteria = {
        "Q0": [("inspection complete", complete), ("glTF 2.0 valid and policy-clean", spec_ok)],
        "Q1": [
            ("within configured runtime budget", within),
            ("geometry integrity >= 0.8", (score("geometry_integrity") or 0) >= 0.8),
            ("material completeness >= 0.6", (score("material_completeness") or 0) >= 0.6),
            ("animation integrity >= 0.8 (if animated)", anim_ok),
        ],
        "Q2": [
            ("visual evidence supplied (>= 2 verified renders)", renders >= 2),
            ("geometry integrity >= 0.95", (score("geometry_integrity") or 0) >= 0.95),
            ("material completeness >= 0.8", (score("material_completeness") or 0) >= 0.8),
            ("visual reference alignment >= 0.6", (va or 0) >= 0.6),
            ("artistic coherence >= 0.6", (ac or 0) >= 0.6),
        ],
        "Q3": [
            (">= 4 verified renders", renders >= 4),
            (">= 1 human assessment", humans >= 1),
            ("material completeness = 1.0", (score("material_completeness") or 0) >= 1.0),
            ("textured materials", textured),
            ("visual reference alignment >= 0.75", (va or 0) >= 0.75),
            ("artistic coherence >= 0.75", (ac or 0) >= 0.75),
        ],
        "Q4": [
            (">= 6 verified renders", renders >= 6),
            ("declared style 'realistic'", style == "realistic"),
            ("PBR texture set (base colour, normal, metallic-roughness)", pbr_tex),
            ("visual reference alignment >= 0.9", (va or 0) >= 0.9),
            ("artistic coherence >= 0.9", (ac or 0) >= 0.9),
        ],
    }
    certified = None
    blockers: list[str] = []
    for tier in ("Q0", "Q1", "Q2", "Q3", "Q4"):
        unmet = [name for name, ok in criteria[tier] if not ok]
        if unmet:
            blockers = unmet
            break
        certified = tier
    ceiling = None
    for tier in ("Q0", "Q1"):
        if all(ok for _, ok in criteria[tier]):
            ceiling = tier
        else:
            break
    return {
        "certified": certified,
        "certified_name": TIERS.get(certified) if certified else None,
        "deterministic_ceiling": ceiling,
        "next_tier": None if certified == "Q4" else ("Q0" if certified is None else f"Q{int(certified[1]) + 1}"),
        "next_tier_blockers": blockers,
        "visual_evidence": "verified" if ev else "absent",
        "criteria": {t: [{"criterion": n, "met": bool(ok)} for n, ok in c] for t, c in criteria.items()},
        "policy": "Q2-Q4 are never certified without digest-verified rendered evidence; Q3+ need a human assessment.",
    }


def load_evidence(path: str | Path, asset_sha256: str) -> dict[str, Any]:
    """Validate a ``finalverse.visual-evidence/v0`` file. Returns {valid, errors, ...}."""
    p = Path(path)
    errors: list[str] = []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"valid": False, "errors": [f"unreadable evidence file: {type(e).__name__}"], "path": p.name}
    if not isinstance(raw, dict) or raw.get("schema") != EVIDENCE_SCHEMA:
        return {"valid": False, "errors": [f"schema must be {EVIDENCE_SCHEMA}"], "path": p.name}
    if raw.get("asset_sha256") != asset_sha256:
        errors.append("asset_sha256 does not match the inspected asset")
    renders = []
    root = p.parent.resolve()
    for i, r in enumerate(raw.get("renders") or []):
        if not isinstance(r, dict) or not isinstance(r.get("path"), str) or not isinstance(r.get("sha256"), str):
            errors.append(f"renders[{i}] needs path and sha256")
            continue
        f = (root / r["path"]).resolve()
        if root not in f.parents or not f.is_file():
            errors.append(f"renders[{i}] file missing or outside the evidence directory")
            continue
        data = f.read_bytes()
        if hashlib.sha256(data).hexdigest() != r["sha256"]:
            errors.append(f"renders[{i}] sha256 mismatch")
            continue
        info = imageinfo.probe(data)
        if info is None:
            errors.append(f"renders[{i}] is not a recognized image")
            continue
        renders.append(
            {
                "sha256": r["sha256"],
                "view": str(r.get("view", ""))[:64],
                "renderer": str(r.get("renderer", ""))[:128],
                "width": info["width"],
                "height": info["height"],
            }
        )
    digests = {r["sha256"] for r in renders}
    assessments = []
    for i, a in enumerate(raw.get("assessments") or []):
        if not isinstance(a, dict):
            errors.append(f"assessments[{i}] must be an object")
            continue
        ok = isinstance(a.get("assessor"), str) and a.get("kind") in ("human", "model")
        for k in ("visual_reference_alignment", "artistic_coherence"):
            v = a.get(k)
            ok = ok and isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0
        refs = a.get("renders")
        ok = ok and isinstance(refs, list) and bool(refs) and all(x in digests for x in refs)
        if not ok:
            errors.append(f"assessments[{i}] invalid (assessor, kind, scores in [0,1], verified render digests)")
            continue
        assessments.append(
            {
                "assessor": a["assessor"][:128],
                "kind": a["kind"],
                "visual_reference_alignment": float(a["visual_reference_alignment"]),
                "artistic_coherence": float(a["artistic_coherence"]),
                "renders": sorted(refs),
            }
        )
    if not assessments:
        errors.append("no valid assessment")
    style = raw.get("style") if raw.get("style") in ("stylized", "realistic") else None
    out = {
        "valid": not errors,
        "errors": errors,
        "path": p.name,
        "style": style,
        "renders": sorted(renders, key=lambda r: r["sha256"]),
        "assessments": sorted(assessments, key=lambda a: (a["assessor"], a["kind"])),
    }
    if not out["valid"]:
        out["renders"], out["assessments"] = [], []
    return out
