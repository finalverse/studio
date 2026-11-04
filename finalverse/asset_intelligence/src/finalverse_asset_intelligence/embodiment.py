"""Embodiment compatibility profiles.

Humanoid profiles build on the *accepted* E0 contract ``finalverse.humanoid/v1``
(finalverse/finalverse docs/genesis/E0-HUMANOID-STANDARD.md, crates/embodiment).
Spirit, sprite and elemental profiles are *provisional*: no accepted E1 contract
was present in the inspected GitHub state, so their requirements are S3-A
proposals, explicitly marked, and must be replaced by E1 contracts when accepted.

Non-humanoid profiles never require a humanoid skeleton.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .profiles import E0_CLIPS, E0_JOINTS, E0_PARENTS

ACCEPTED = "accepted:finalverse.humanoid/v1"
PROVISIONAL = "provisional:s3a (no accepted E1 contract available)"


@dataclass(frozen=True)
class Req:
    id: str
    level: str  # required | recommended
    basis: str
    text: str
    check: Callable[[Facts], tuple[str, Any]]


class Facts:
    """Derived, deterministic facts about a model used by embodiment rules."""

    def __init__(self, m) -> None:
        self.m = m
        b = m.bounds
        self.size = b["size"] if b else None
        self.min = b["min"] if b else None
        self.extent = max(self.size) if self.size else None
        self.height = self.size[1] if self.size else None
        self.anims = [a for a in m.animations if a["valid"]]
        self.names = {a["name"] for a in self.anims if a["name"]}
        used = {p.material for p in m.prims if p.material is not None}
        mats = [m.materials[i] for i in sorted(used) if i < len(m.materials)]
        self.emissive_materials = [
            mt
            for mt in mats
            if (max(mt["emissive_factor"]) * mt["emissive_strength"] > 0) or "emissiveTexture" in mt["textures"]
        ]
        self.emissive = bool(self.emissive_materials)
        self.translucent = [mt for mt in mats if mt["alpha_mode"] in ("BLEND", "MASK")]
        self.rig = self._rig()

    def _rig(self) -> tuple[bool, str, dict | None]:
        m = self.m
        for sk in m.skins:
            if len(sk["joints"]) != 26:
                continue
            names = tuple(sk["joint_names"])
            if names != E0_JOINTS:
                continue
            idx = sk["joints"]
            pos = {n: k for k, n in enumerate(idx)}
            for k, j in enumerate(idx):
                parent = m.parents[j]
                want = E0_PARENTS[k]
                if (want is None and parent in pos) or (want is not None and parent != idx[want]):
                    return False, f"joint '{E0_JOINTS[k]}' has a non-canonical parent", sk
                node = m.nodes[j]
                if (
                    "matrix" in node
                    or "scale" in node
                    or ("rotation" in node and any(abs(a - b) > 1e-6 for a, b in zip(node["rotation"], (0, 0, 0, 1))))
                ):
                    return False, f"joint '{E0_JOINTS[k]}' has a non-identity rest rotation/scale", sk
            if sk["rest_consistent"] is not True:
                return False, "inverse bind matrices do not match the rest pose", sk
            return True, "canonical 26-joint hierarchy, identity rest rotations, consistent inverse binds", sk
        if any(len(s["joints"]) == 26 for s in m.skins):
            return False, "26-joint skin found but joint names/order differ from finalverse.humanoid/v1", None
        return False, "no skin with the 26 canonical finalverse.humanoid/v1 joints", None


def _range(lo: float, hi: float, attr: str = "extent"):
    def f(x: Facts):
        v = getattr(x, attr)
        if v is None:
            return "unverified", "no finite geometric bounds"
        return ("pass" if lo <= v <= hi else "fail"), f"{attr} {round(v, 4)} m (expected {lo}..{hi} m)"

    return f


def _grounded(x: Facts):
    if x.min is None:
        return "unverified", "no finite geometric bounds"
    return ("pass" if abs(x.min[1]) <= 0.05 else "fail"), f"lowest point y = {round(x.min[1], 4)} m"


def _hover(x: Facts):
    if x.min is None:
        return "unverified", "no finite geometric bounds"
    return ("pass" if x.min[1] > 0.05 else "fail"), f"lowest point y = {round(x.min[1], 4)} m"


def _motion(x: Facts):
    if not x.anims:
        return "fail", "no valid animation"
    kinds = sorted({k for a in x.anims for k in a["kinds"]})
    return "pass", f"{len(x.anims)} valid animation(s); kinds: {', '.join(kinds) or 'none'}"


def _loops(x: Facts):
    loops = [a["loops"] for a in x.anims if a["loops"] is not None]
    if not loops:
        return "unverified", "no loop-evaluable animation"
    return ("pass" if all(loops) else "fail"), f"{sum(loops)}/{len(loops)} animation(s) return to their first key"


def _rig(x: Facts):
    ok, detail, _ = x.rig
    return ("pass" if ok else "fail"), detail


def _clips(x: Facts):
    if not x.anims:
        return "fail", "no valid animation"
    unknown = sorted(n for n in (a["name"] or "<unnamed>" for a in x.anims) if n not in E0_CLIPS)
    non_rot = sorted({a["name"] or "<unnamed>" for a in x.anims if set(a["paths"]) - {"rotation"}})
    if unknown or non_rot:
        return "fail", f"non-canonical clips {unknown[:6]}; non-rotation channels in {non_rot[:6]}"
    return "pass", f"clips: {', '.join(sorted(x.names))}"


def _has(*clips: str):
    def f(x: Facts):
        missing = [c for c in clips if c not in x.names]
        return ("fail" if missing else "pass"), (
            f"missing clip(s): {', '.join(missing)}" if missing else f"has {', '.join(clips)}"
        )

    return f


def _face(x: Facts):
    ok, _, sk = x.rig
    if not ok or sk is None:
        return "unverified", "requires the canonical rig"
    m = x.m
    want = {sk["joints"][E0_JOINTS.index(n)] for n in ("eye_l", "eye_r", "jaw")}
    palette = {k: j for k, j in enumerate(sk["joints"])}
    found = set()
    for pr in m.prims:
        if pr.joints is None or pr.weights is None:
            continue
        for j, w in zip(pr.joints.values, pr.weights.values):
            if w > 0 and palette.get(j) in want:
                found.add(palette[j])
    return ("pass" if found == want else "fail"), f"{len(found)}/3 facial joints (eyes, jaw) influence vertices"


def _emissive(x: Facts):
    return ("pass" if x.emissive else "fail"), (
        "a used material emits light" if x.emissive else "no used material has emission"
    )


def _warm(x: Facts):
    em = [mt for mt in x.emissive_materials]
    if not em:
        return "fail", "no emissive material"
    cool = [
        mt["index"]
        for mt in em
        if not (mt["emissive_factor"][0] >= mt["emissive_factor"][1] >= mt["emissive_factor"][2])
    ]
    return ("fail" if cool else "pass"), (
        f"non-warm emissive materials {cool}" if cool else f"{len(em)} warm emissive material(s)"
    )


def _glow(x: Facts):
    blend = any(mt["alpha_mode"] == "BLEND" for mt in x.translucent)
    ok = x.emissive or blend
    return ("pass" if ok else "fail"), f"emissive={x.emissive}, alpha BLEND={blend}"


def _blend(x: Facts):
    ok = any(mt["alpha_mode"] == "BLEND" for mt in x.translucent)
    return ("pass" if ok else "fail"), ("translucent (BLEND) material present" if ok else "no BLEND material")


def _cards(x: Facts):
    if not x.translucent:
        return "pass", "no alpha-tested/blended materials"
    single = [mt["index"] for mt in x.translucent if not mt["double_sided"]]
    return ("fail" if single else "pass"), (
        f"single-sided translucent materials {single}" if single else "translucent materials are double-sided"
    )


def _humanoid(prefix: str, facial: bool) -> list[Req]:
    reqs = [
        Req(
            f"{prefix}-01",
            "required",
            ACCEPTED,
            "Canonical finalverse.humanoid/v1 rig (structure, not names only)",
            _rig,
        ),
        Req(
            f"{prefix}-02",
            "required",
            ACCEPTED,
            "Standing height 1.4..2.1 m (E0 height_mm 1400..2100)",
            _range(1.4, 2.1, "height"),
        ),
        Req(
            f"{prefix}-03", "required", ACCEPTED, "Origin under the feet (lowest point within 0.05 m of y=0)", _grounded
        ),
        Req(f"{prefix}-04", "required", ACCEPTED, "At least one clip; all clips canonical and rotation-only", _clips),
        Req(f"{prefix}-05", "recommended", PROVISIONAL, "Locomotion capability (walk, turn)", _has("walk", "turn")),
        Req(f"{prefix}-06", "recommended", PROVISIONAL, "Social capability (greet, speak)", _has("greet", "speak")),
        Req(f"{prefix}-07", "recommended", PROVISIONAL, "Idle capability (idle)", _has("idle")),
    ]
    if facial:
        reqs.append(
            Req(f"{prefix}-08", "recommended", PROVISIONAL, "Eyes and jaw influence geometry (expressive face)", _face)
        )
    return reqs


PROFILES: dict[str, dict[str, Any]] = {
    "biological_humanoid": {
        "title": "Biological humanoid",
        "skeleton": "required: finalverse.humanoid/v1",
        "e0_body_types": ["human", "stylized_humanoid"],
        "contract_status": "accepted (rig) + provisional (capabilities)",
        "requirements": _humanoid("BH", facial=True),
    },
    "synthetic_humanoid": {
        "title": "Synthetic humanoid (droid, android)",
        "skeleton": "required: finalverse.humanoid/v1",
        "e0_body_types": ["droid"],
        "contract_status": "accepted (rig) + provisional (capabilities)",
        "requirements": _humanoid("SH", facial=False),
    },
    "floating_spirit": {
        "title": "Floating spirit",
        "skeleton": "optional (any or none)",
        "e0_body_types": [],
        "contract_status": "provisional",
        "requirements": [
            Req("FS-01", "required", PROVISIONAL, "Finite extent 0.1..4 m", _range(0.1, 4.0)),
            Req(
                "FS-02",
                "required",
                PROVISIONAL,
                "Ambient motion: at least one valid animation (node, skeletal or morph)",
                _motion,
            ),
            Req(
                "FS-03",
                "required",
                PROVISIONAL,
                "Hovers: lowest point above 0.05 m (no ground contact assumed)",
                _hover,
            ),
            Req("FS-04", "recommended", PROVISIONAL, "Luminous or translucent appearance (emission or BLEND)", _glow),
            Req("FS-05", "recommended", PROVISIONAL, "Ambient motion loops seamlessly", _loops),
        ],
    },
    "botanical_sprite": {
        "title": "Botanical sprite",
        "skeleton": "optional (any or none)",
        "e0_body_types": [],
        "contract_status": "provisional",
        "requirements": [
            Req("BS-01", "required", PROVISIONAL, "Finite extent 0.05..1.5 m", _range(0.05, 1.5)),
            Req("BS-02", "required", PROVISIONAL, "Ambient motion (sway): at least one valid animation", _motion),
            Req(
                "BS-03", "required", PROVISIONAL, "Rooted on its origin (lowest point within 0.05 m of y=0)", _grounded
            ),
            Req("BS-04", "recommended", PROVISIONAL, "Alpha-tested/blended foliage materials are double-sided", _cards),
            Req("BS-05", "recommended", PROVISIONAL, "Ambient motion loops seamlessly", _loops),
        ],
    },
    "nature_elemental": {
        "title": "Nature elemental",
        "skeleton": "optional (any or none)",
        "e0_body_types": [],
        "contract_status": "provisional",
        "requirements": [
            Req("NE-01", "required", PROVISIONAL, "Finite extent 0.5..8 m", _range(0.5, 8.0)),
            Req("NE-02", "required", PROVISIONAL, "Motion: at least one valid animation", _motion),
            Req(
                "NE-03",
                "required",
                PROVISIONAL,
                "Grounded on its origin (lowest point within 0.05 m of y=0)",
                _grounded,
            ),
            Req("NE-04", "recommended", PROVISIONAL, "Motion loops seamlessly", _loops),
        ],
    },
    "fire_elemental": {
        "title": "Fire elemental",
        "skeleton": "optional (any or none)",
        "e0_body_types": [],
        "contract_status": "provisional",
        "requirements": [
            Req("FE-01", "required", PROVISIONAL, "Finite extent 0.2..6 m", _range(0.2, 6.0)),
            Req("FE-02", "required", PROVISIONAL, "Emissive: a used material emits light", _emissive),
            Req("FE-03", "required", PROVISIONAL, "Warm emission: every emissive material has R >= G >= B", _warm),
            Req("FE-06", "required", PROVISIONAL, "Motion (flicker): at least one valid animation", _motion),
            Req("FE-04", "recommended", PROVISIONAL, "Translucent flame material (alpha BLEND)", _blend),
            Req("FE-05", "recommended", PROVISIONAL, "Motion loops seamlessly", _loops),
        ],
    },
}


def evaluate(m, selected: str | None = None) -> list[dict[str, Any]]:
    if m.aborted:
        return [
            {"profile": pid, "title": p["title"], "status": "not_evaluated", "requirements": []}
            for pid, p in PROFILES.items()
            if selected in (None, pid)
        ]
    facts = Facts(m)
    out = []
    for pid, p in PROFILES.items():
        if selected not in (None, pid):
            continue
        rows = []
        for r in p["requirements"]:
            outcome, detail = r.check(facts)
            rows.append(
                {
                    "requirement": r.id,
                    "level": r.level,
                    "basis": r.basis,
                    "text": r.text,
                    "outcome": outcome,
                    "detail": detail,
                }
            )
        req = [x for x in rows if x["level"] == "required"]
        if any(x["outcome"] == "fail" for x in req):
            status = "incompatible"
        elif any(x["outcome"] == "unverified" for x in req):
            status = "unverified"
        else:
            status = "compatible"
        entry = {
            "profile": pid,
            "title": p["title"],
            "status": status,
            "skeleton": p["skeleton"],
            "contract_status": p["contract_status"],
            "e0_body_types": p["e0_body_types"],
            "recommendations_unmet": [
                x["requirement"] for x in rows if x["level"] == "recommended" and x["outcome"] == "fail"
            ],
            "requirements": rows,
        }
        if pid.endswith("humanoid") and facts.size:
            radius = round(max(facts.size[0], facts.size[2]) / 2, 4)
            entry["derived"] = {
                "collision_capsule": {"radius_m": radius, "height_m": round(facts.size[1], 4)},
                "within_e0_definition_bounds": 0.15 <= radius <= 0.5 and 1.4 <= facts.size[1] <= 2.1,
            }
        out.append(entry)
    return out


def emit_findings(m, results: list[dict[str, Any]], selected: str | None) -> None:
    if not selected:
        return
    for res in results:
        if res["profile"] != selected:
            continue
        for row in res["requirements"]:
            if row["outcome"] != "fail":
                continue
            code = "FVA-EMB-001" if row["level"] == "required" else "FVA-EMB-002"
            m.ctx.add(
                code,
                f"/embodiment/{selected}/{row['requirement']}",
                f"{row['text']}: {row['detail']}",
                {"profile": selected, "requirement": row["requirement"], "basis": row["basis"]},
            )
