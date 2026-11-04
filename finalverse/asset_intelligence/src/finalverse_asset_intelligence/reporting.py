"""Assembly of the versioned ``finalverse.asset-intelligence/v1`` report."""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__, embodiment, profiles, proposals, quality
from .analyze import Model
from .findings import SEVERITIES

SCHEMA = "finalverse.asset-intelligence/v1"
TOOL = "finalverse-asset-intelligence"
EXCLUDED_FROM_DIGEST = ("generated_at", "report_digest")


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def timestamp(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    if sde and sde.isdigit():
        t = _dt.datetime.fromtimestamp(int(sde), _dt.UTC)
    else:
        t = _dt.datetime.now(_dt.UTC)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clip(items: list, limit: int) -> dict[str, Any]:
    return {"items": items[:limit], "total": len(items), "truncated": len(items) > limit}


def _json_safe(v: Any) -> Any:
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return str(v)
        return round(v, 6)
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return v


def _str_or_none(v: Any) -> str | None:
    return v[:256] if isinstance(v, str) else None


def inspection(m: Model) -> dict[str, Any]:
    lim = m.limits.max_report_list_items
    if m.container is None:
        return {"container": None}
    doc = m.doc
    a = doc.get("asset", {}) if isinstance(doc.get("asset"), dict) else {}
    acc = m.acc
    nodes = []
    for i, n in enumerate(m.nodes):
        t = {k: n[k] for k in ("matrix", "translation", "rotation", "scale") if k in n}
        nodes.append(
            {
                "index": i,
                "name": n.get("name") if isinstance(n.get("name"), str) else None,
                "parent": m.parents[i] if i < len(m.parents) else None,
                "children": [c for c in n.get("children", []) if isinstance(c, int)]
                if isinstance(n.get("children"), list)
                else [],
                "mesh": n.get("mesh"),
                "skin": n.get("skin"),
                "transform": t,
            }
        )
    meshes = []
    raw_meshes = doc.get("meshes") if isinstance(doc.get("meshes"), list) else []
    for mi, prims in sorted(m.mesh_prims.items()):
        mesh = raw_meshes[mi] if mi < len(raw_meshes) and isinstance(raw_meshes[mi], dict) else {}
        extras = mesh.get("extras") if isinstance(mesh.get("extras"), dict) else {}
        meshes.append(
            {
                "index": mi,
                "name": mesh.get("name") if isinstance(mesh.get("name"), str) else None,
                "morph_target_names": extras.get("targetNames")
                if isinstance(extras.get("targetNames"), list)
                else None,
                "primitives": [
                    {
                        "index": p.index,
                        "mode": p.mode,
                        "material": p.material,
                        "vertices": p.vertices,
                        "triangles": p.triangles,
                        "degenerate_triangles": p.degenerate,
                        "morph_targets": p.targets,
                        "bounds": {"min": p.bbox[0], "max": p.bbox[1]} if p.bbox else None,
                        "attributes": {
                            sem: {
                                "accessor": ai,
                                "type": acc.accessors[ai].get("type"),
                                "componentType": acc.accessors[ai].get("componentType"),
                                "count": acc.accessors[ai].get("count"),
                                "normalized": acc.accessors[ai].get("normalized", False),
                            }
                            for sem, ai in sorted(p.attributes.items())
                        },
                    }
                    for p in prims
                ],
            }
        )
    skins = [{k: v for k, v in s.items() if k != "inverse_bind_matrices"} for s in m.skins]
    anims = [{**an, "targets": len(an["targets"])} for an in m.animations]
    caps = {
        "static": not m.skins and not m.animations,
        "skinned": bool(m.skins),
        "animated": bool(m.animations),
        "morph_targets": any(p.targets for p in m.prims),
        "textured": any(mt["textures"] for mt in m.materials),
        "emissive": any(max(mt["emissive_factor"]) > 0 or "emissiveTexture" in mt["textures"] for mt in m.materials),
        "translucent": any(mt["alpha_mode"] in ("MASK", "BLEND") for mt in m.materials),
        "clip_names": sorted(an["name"] for an in m.animations if an["name"]),
    }
    return _json_safe(
        {
            "container": {"kind": m.container.kind, **{k: v for k, v in m.container.layout.items()}},
            "asset": {k: _str_or_none(a.get(k)) for k in ("version", "minVersion", "generator", "copyright") if k in a},
            "extensions": m.extensions,
            "scene": {
                "default": m.scene_index,
                "count": len(doc["scenes"]) if isinstance(doc.get("scenes"), list) else 0,
                "nodes_in_default_scene": len(m.scene_nodes),
            },
            "nodes": _clip(nodes, lim),
            "meshes": _clip(meshes, lim),
            "materials": _clip(m.materials, lim),
            "textures": _clip(m.textures, lim),
            "images": _clip(m.images, lim),
            "skins": _clip(skins, lim),
            "animations": _clip(anims, lim),
            "bounds": m.bounds,
            "dependencies": _clip([r.to_dict() for r in m.resources], lim),
            "capabilities": caps,
        }
    )


def build(
    m: Model,
    *,
    runtime_profiles: list[str] | None = None,
    target: str | None = None,
    embodiment_profile: str | None = None,
    visual_evidence: str | Path | None = None,
    generated_at: str | None = None,
    include_inspection: bool = True,
) -> dict[str, Any]:
    """Build the report. The model is not changed: report-level findings go to a copy."""
    saved = m.ctx.findings
    m.ctx.findings = copy.deepcopy(saved)
    try:
        return _build(
            m, runtime_profiles, target, embodiment_profile, visual_evidence, generated_at, include_inspection
        )
    finally:
        m.ctx.findings = saved


def _build(m, runtime_profiles, target, embodiment_profile, visual_evidence, generated_at, include_inspection):
    if target and runtime_profiles and target not in runtime_profiles:
        runtime_profiles = [*runtime_profiles, target]
    runtime = profiles.evaluate_runtime(m, runtime_profiles)
    if target:
        res = next((r for r in runtime if r.id == target), None)
        if res is not None and res.status == "incompatible":
            for rule in res.failed:
                m.ctx.add(
                    "FVA-CMP-001",
                    f"/compatibility/{target}/{rule['rule']}",
                    f"Target profile {target} refuses the asset",
                    {
                        "profile": target,
                        "rule": rule["rule"],
                        "requirement": rule["requirement"],
                        "detail": rule.get("detail"),
                    },
                )
            if not res.failed:
                m.ctx.add(
                    "FVA-CMP-001",
                    f"/compatibility/{target}",
                    f"Target profile {target} refuses the asset",
                    {"profile": target, "notes": res.notes},
                )
    emb = embodiment.evaluate(m)
    embodiment.emit_findings(m, emb, embodiment_profile)
    evidence = None
    if visual_evidence is not None:
        evidence = quality.load_evidence(visual_evidence, m.sha256)
        if not evidence["valid"]:
            m.ctx.add(
                "FVA-QLT-001",
                "/quality/visual_evidence",
                "Visual evidence rejected",
                {"errors": evidence["errors"][:16]},
            )
    findings = m.findings.all()
    q = quality.assess(m, findings, emb, embodiment_profile, evidence)
    counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
    by_class = {}
    for f in findings:
        by_class[f.meta.cls] = by_class.get(f.meta.cls, 0) + 1
    spec_invalid = any(f.meta.cls == "spec" and f.severity in ("critical", "error") for f in findings)
    security = any(f.meta.cls == "security" for f in findings)
    limits = any(f.meta.cls == "limit" for f in findings)
    if spec_invalid:
        status = "invalid"
    elif security or not m.complete:
        status = "refused"
    elif limits:
        status = "valid_exceeds_limits"
    else:
        status = "valid"
    target_res = next((r for r in runtime if r.id == target), None) if target else None
    rep: dict[str, Any] = {
        "schema": SCHEMA,
        "tool": {"name": TOOL, "version": __version__},
        "generated_at": timestamp(generated_at),
        "asset": {
            "file_name": m.name,
            "media_type": None
            if m.container is None
            else ("model/gltf-binary" if m.container.kind == "glb" else "model/gltf+json"),
            "byte_length": m.byte_length,
            "sha256": m.sha256,
            "identity": f"sha256:{m.sha256}",
            "generator": _str_or_none((m.doc.get("asset") or {}).get("generator"))
            if isinstance(m.doc.get("asset"), dict)
            else None,
        },
        "configuration": {
            "limits": m.limits.to_dict(),
            "budget": m.budget.to_dict(),
            "runtime_profiles": [r.id for r in runtime],
            "target_profile": target,
            "embodiment_profile": embodiment_profile,
        },
        "validation": {
            "status": status,
            "spec_valid": not spec_invalid and m.container is not None,
            "within_limits": not limits,
            "policy_clean": not security,
            "inspection_complete": m.complete,
            "incomplete_reasons": sorted(m.ctx.incomplete_reasons),
            "target_profile_status": target_res.status if target_res else None,
            "finding_counts": counts,
            "finding_counts_by_class": dict(sorted(by_class.items())),
            "suppressed_repeats": m.findings.suppressed,
        },
        "metrics": _json_safe(m.metrics),
        "findings": [_json_safe(f.to_dict()) for f in findings],
        "compatibility": {"runtime": [_json_safe(r.to_dict()) for r in runtime], "embodiment": _json_safe(emb)},
        "quality": _json_safe(q),
        "proposals": _json_safe(proposals.build(findings)),
        "provenance": {
            "inspector": f"{TOOL} {__version__}",
            "inputs": [{"role": "asset", "sha256": m.sha256, "byte_length": m.byte_length}]
            + [
                {
                    "role": f"dependency:{r.kind}",
                    "component": r.pointer,
                    "sha256": d["sha256"],
                    "byte_length": d["byte_length"],
                }
                for r in m.resources
                if r.uri_class == "relative"
                for d in [r.to_dict()]
                if "sha256" in d
            ]
            + ([{"role": "visual-evidence", "file": evidence["path"], "valid": evidence["valid"]}] if evidence else []),
            "contract_sources": sorted({json.dumps(s, sort_keys=True) for r in runtime for s in r.sources}),
            "network_access": "none",
            "modifies_asset": False,
        },
    }
    rep["provenance"]["contract_sources"] = [json.loads(s) for s in rep["provenance"]["contract_sources"]]
    if evidence is not None:
        rep["quality"]["visual_evidence"] = _json_safe(evidence)
    if include_inspection:
        rep["inspection"] = inspection(m)
    rep = _json_safe(rep)  # untrusted values anywhere become finite, JSON-safe data
    rep["report_digest"] = digest(rep)
    return rep


def digest(rep: dict[str, Any]) -> str:
    core = {k: v for k, v in rep.items() if k not in EXCLUDED_FROM_DIGEST}
    return "sha256:" + hashlib.sha256(canonical(core)).hexdigest()


def dumps(rep: dict[str, Any], pretty: bool = True) -> str:
    if pretty:
        return json.dumps(rep, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    return canonical(rep).decode("utf-8") + "\n"


def python_info() -> str:
    return f"{sys.implementation.name} {sys.version_info.major}.{sys.version_info.minor}"
