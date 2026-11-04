"""Inspection safety limits and configurable Finalverse runtime budgets.

Two different things live here and they must not be confused:

* ``Limits`` bound the *inspector itself* (how much untrusted input it will read,
  decode and traverse).  Exceeding one makes the inspection incomplete or refused;
  it says nothing about whether the asset is valid glTF.
* ``RuntimeBudget`` describes what a Finalverse runtime is configured to accept.
  Exceeding one yields ``limit`` findings on an otherwise valid asset
  (validation status ``valid_exceeds_limits``).
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MIB = 1024 * 1024


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 128 * MIB
    max_json_bytes: int = 32 * MIB
    max_json_depth: int = 64
    max_array_length: int = 1_000_000
    max_total_buffer_bytes: int = 256 * MIB
    max_data_uri_bytes: int = 64 * MIB
    max_external_files: int = 256
    max_decoded_components: int = 40_000_000
    max_node_depth: int = 256
    max_report_list_items: int = 512
    time_budget_seconds: float = 60.0
    allow_local_resources: bool = True

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class BudgetValue:
    value: int
    basis: str


def _b(value: int, basis: str) -> BudgetValue:
    return BudgetValue(value, basis)


G0 = "finalverse/finalverse docs/genesis/G0-GENERATOR-CONTRACTS.md (G0 worker budget)"
INF = "finalverse/infinity src/entry.rs decode_parts"
E0 = "finalverse/finalverse crates/embodiment/src/lib.rs Asset::load"
PROV = "provisional S3-A default; no accepted Finalverse contract found"


@dataclass(frozen=True)
class RuntimeBudget:
    """Configured Finalverse runtime limits.  Every value records its basis."""

    name: str = "finalverse.runtime-budget/default-v0"
    max_triangles: BudgetValue = field(default_factory=lambda: _b(100_000, G0))
    max_vertices: BudgetValue = field(default_factory=lambda: _b(100_000, PROV))
    max_file_bytes: BudgetValue = field(default_factory=lambda: _b(4 * MIB, G0))
    max_draw_calls: BudgetValue = field(default_factory=lambda: _b(256, INF))
    max_materials: BudgetValue = field(default_factory=lambda: _b(32, PROV))
    max_joints: BudgetValue = field(default_factory=lambda: _b(128, PROV))
    max_animations: BudgetValue = field(default_factory=lambda: _b(16, E0))
    max_morph_targets: BudgetValue = field(default_factory=lambda: _b(16, PROV))
    max_texture_dimension: BudgetValue = field(default_factory=lambda: _b(4096, PROV))
    max_nodes: BudgetValue = field(default_factory=lambda: _b(1024, PROV))

    METRICS = (
        "max_triangles",
        "max_vertices",
        "max_file_bytes",
        "max_draw_calls",
        "max_materials",
        "max_joints",
        "max_animations",
        "max_morph_targets",
        "max_texture_dimension",
        "max_nodes",
    )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name}
        for m in self.METRICS:
            v: BudgetValue = getattr(self, m)
            out[m] = {"value": v.value, "basis": v.basis}
        return out


def load_budget(path: str | Path) -> RuntimeBudget:
    """Load a budget JSON: {"name": str, "<metric>": int | {"value": int, "basis": str}}."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("budget file must be a JSON object")
    kwargs: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "name":
            if not isinstance(value, str) or not value:
                raise ValueError("budget name must be a non-empty string")
            kwargs["name"] = value
        elif key in RuntimeBudget.METRICS:
            if isinstance(value, dict):
                v, basis = value.get("value"), value.get("basis", f"configured in {Path(path).name}")
            else:
                v, basis = value, f"configured in {Path(path).name}"
            if not isinstance(v, int) or isinstance(v, bool) or v < 0 or not isinstance(basis, str):
                raise ValueError(f"budget {key} must be a non-negative integer")
            kwargs[key] = BudgetValue(v, basis)
        else:
            raise ValueError(f"unknown budget field {key!r}")
    return RuntimeBudget(**kwargs)


def load_limits(path: str | Path) -> Limits:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("limits file must be a JSON object")
    names = {f.name: f for f in dataclasses.fields(Limits)}
    kwargs: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in names:
            raise ValueError(f"unknown limit {key!r}")
        default = getattr(Limits(), key)
        if isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, float):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        else:
            ok = isinstance(value, int) and not isinstance(value, bool) and value > 0
        if not ok:
            raise ValueError(f"invalid value for limit {key!r}")
        kwargs[key] = value
    return Limits(**kwargs)
