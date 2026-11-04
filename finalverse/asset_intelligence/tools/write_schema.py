"""Generate schema/finalverse.asset-intelligence.v1.schema.json from the code catalogue.

python tools/write_schema.py          # write
python tools/write_schema.py --check  # fail if the committed schema is stale
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from finalverse_asset_intelligence.embodiment import PROFILES  # noqa: E402
from finalverse_asset_intelligence.findings import CATALOGUE, CLASSES, SEVERITIES  # noqa: E402
from finalverse_asset_intelligence.profiles import RUNTIME_PROFILES  # noqa: E402

OUT = ROOT / "schema" / "finalverse.asset-intelligence.v1.schema.json"
NUM_OR_NULL = {"type": ["number", "null"]}
STR_OR_NULL = {"type": ["string", "null"]}


def obj(props: dict, required: list | None = None, extra: bool = False) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": required if required is not None else list(props),
        "additionalProperties": extra,
    }


def schema() -> dict:
    sev = {"enum": list(SEVERITIES)}
    finding = obj(
        {
            "id": {"type": "string", "pattern": r"^FVA-[A-Z]{3}-\d{3}:/"},
            "code": {"enum": sorted(CATALOGUE)},
            "name": {"type": "string"},
            "category": {"type": "string"},
            "class": {"enum": list(CLASSES)},
            "severity": sev,
            "component": {"type": "string", "pattern": "^/"},
            "message": {"type": "string"},
            "evidence": {"type": "object"},
        }
    )
    proposal = obj(
        {
            "id": {"type": "string", "pattern": "^P-FVA-"},
            "finding_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "severity": sev,
            "category": {"type": "string"},
            "class": {"enum": list(CLASSES)},
            "component": {"type": "string"},
            "components": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "object"},
            "action": {"type": "string", "minLength": 1},
            "expected_impact": {"type": "string", "minLength": 1},
            "confidence": {"enum": ["high", "medium", "low"]},
            "required_validation": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "advisory": {"const": True},
            "modifies_asset": {"const": False},
        }
    )
    rule = obj(
        {
            "rule": {"type": "string"},
            "requirement": {"type": "string"},
            "outcome": {"enum": ["pass", "fail", "unverified", "not_evaluated"]},
            "detail": {"type": "string"},
        },
        ["rule", "requirement", "outcome"],
    )
    runtime = obj(
        {
            "id": {"enum": sorted(RUNTIME_PROFILES)},
            "title": {"type": "string"},
            "status": {"enum": ["compatible", "incompatible", "unverified", "not_evaluated"]},
            "contract": obj(
                {"status": {"enum": ["accepted", "observed", "provisional", "n/a"]}, "sources": {"type": "array"}}
            ),
            "rules": {"type": "array", "items": rule},
            "notes": {"type": "array", "items": {"type": "string"}},
            "material_feature_support": {
                "type": "object",
                "additionalProperties": {"enum": ["consumed_by_entry_reader", "not_consumed_by_entry_reader"]},
            },
        },
        ["id", "title", "status", "contract", "rules", "notes"],
    )
    req = obj(
        {
            "requirement": {"type": "string"},
            "level": {"enum": ["required", "recommended"]},
            "basis": {"type": "string"},
            "text": {"type": "string"},
            "outcome": {"enum": ["pass", "fail", "unverified"]},
            "detail": {"type": "string"},
        }
    )
    emb = obj(
        {
            "profile": {"enum": sorted(PROFILES)},
            "title": {"type": "string"},
            "status": {"enum": ["compatible", "incompatible", "unverified", "not_evaluated"]},
            "skeleton": {"type": "string"},
            "contract_status": {"type": "string"},
            "e0_body_types": {"type": "array"},
            "recommendations_unmet": {"type": "array"},
            "requirements": {"type": "array", "items": req},
            "derived": {"type": "object"},
        },
        ["profile", "title", "status", "requirements"],
    )
    category = obj(
        {
            "score": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "status": {"enum": ["assessed", "not_assessed", "not_applicable"]},
            "method": {"enum": ["deterministic", "evidence"]},
            "explanation": {"type": "string"},
            "basis": {"type": "array"},
            "checklist": {"type": "object"},
        },
        ["score", "status", "method", "explanation", "basis"],
    )
    tier_id = {"enum": ["Q0", "Q1", "Q2", "Q3", "Q4", None]}
    counts = obj({s: {"type": "integer", "minimum": 0} for s in SEVERITIES})
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://finalverse.ai/schemas/finalverse.asset-intelligence/v1.json",
        "title": "finalverse.asset-intelligence/v1",
        "description": "Report produced by finalverse-asset-intelligence. Generated by tools/write_schema.py.",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema",
            "tool",
            "generated_at",
            "asset",
            "configuration",
            "validation",
            "metrics",
            "findings",
            "compatibility",
            "quality",
            "proposals",
            "provenance",
            "report_digest",
        ],
        "properties": {
            "schema": {"const": "finalverse.asset-intelligence/v1"},
            "tool": obj({"name": {"const": "finalverse-asset-intelligence"}, "version": {"type": "string"}}),
            "generated_at": {"type": "string"},
            "report_digest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "asset": obj(
                {
                    "file_name": {"type": "string"},
                    "media_type": {"enum": ["model/gltf-binary", "model/gltf+json", None]},
                    "byte_length": {"type": "integer", "minimum": 0},
                    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "identity": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "generator": STR_OR_NULL,
                }
            ),
            "configuration": obj(
                {
                    "limits": {"type": "object"},
                    "budget": {"type": "object"},
                    "runtime_profiles": {"type": "array"},
                    "target_profile": STR_OR_NULL,
                    "embodiment_profile": STR_OR_NULL,
                }
            ),
            "validation": obj(
                {
                    "status": {"enum": ["valid", "valid_exceeds_limits", "invalid", "refused"]},
                    "spec_valid": {"type": "boolean"},
                    "within_limits": {"type": "boolean"},
                    "policy_clean": {"type": "boolean"},
                    "inspection_complete": {"type": "boolean"},
                    "incomplete_reasons": {"type": "array", "items": {"type": "string"}},
                    "target_profile_status": STR_OR_NULL,
                    "finding_counts": counts,
                    "finding_counts_by_class": {"type": "object"},
                    "suppressed_repeats": {"type": "object"},
                }
            ),
            "metrics": {"type": "object"},
            "findings": {"type": "array", "items": finding},
            "compatibility": obj(
                {"runtime": {"type": "array", "items": runtime}, "embodiment": {"type": "array", "items": emb}}
            ),
            "quality": obj(
                {
                    "categories": obj(
                        {
                            k: category
                            for k in (
                                "geometry_integrity",
                                "material_completeness",
                                "animation_integrity",
                                "embodiment_compatibility",
                                "runtime_complexity",
                                "visual_reference_alignment",
                                "artistic_coherence",
                            )
                        }
                    ),
                    "tier": obj(
                        {
                            "certified": tier_id,
                            "certified_name": STR_OR_NULL,
                            "deterministic_ceiling": tier_id,
                            "next_tier": tier_id,
                            "next_tier_blockers": {"type": "array"},
                            "visual_evidence": {"enum": ["verified", "absent"]},
                            "criteria": {"type": "object"},
                            "policy": {"type": "string"},
                        }
                    ),
                    "visual_evidence": {"type": "object"},
                },
                ["categories", "tier"],
            ),
            "proposals": {"type": "array", "items": proposal},
            "provenance": obj(
                {
                    "inspector": {"type": "string"},
                    "inputs": {"type": "array"},
                    "contract_sources": {"type": "array"},
                    "network_access": {"const": "none"},
                    "modifies_asset": {"const": False},
                }
            ),
            "inspection": {"type": "object"},
        },
        "$defs": {"finding": finding, "proposal": proposal, "runtime_profile": runtime, "embodiment": emb},
    }


def main() -> int:
    text = json.dumps(schema(), indent=2, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        ok = OUT.is_file() and OUT.read_text() == text
        print("schema up to date" if ok else "schema is stale: run tools/write_schema.py")
        return 0 if ok else 1
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
