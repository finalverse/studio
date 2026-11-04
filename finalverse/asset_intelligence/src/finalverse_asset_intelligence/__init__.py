"""Finalverse Asset Intelligence (Studio S3-A).

Blender-independent inspection, validation, compatibility assessment, quality
assessment and advisory improvement proposals for glTF 2.0 / GLB assets.

Library API::

    from finalverse_asset_intelligence import inspect_path, report_for_path

    model = inspect_path("body.glb")            # parse + validate, no report
    report = report_for_path("body.glb", embodiment="floating_spirit")
    report["validation"]["status"]              # valid | valid_exceeds_limits | invalid | refused

The package has no third-party dependencies and never imports ``bpy``.
"""

from __future__ import annotations

__version__ = "0.1.0"

from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from .analyze import Model, analyze, load_path  # noqa: E402
from .limits import Limits, RuntimeBudget, load_budget, load_limits  # noqa: E402

__all__ = [
    "Limits",
    "Model",
    "RuntimeBudget",
    "analyze",
    "inspect_bytes",
    "inspect_path",
    "load_budget",
    "load_limits",
    "report",
    "report_for_path",
    "__version__",
]


def inspect_path(path: str | Path, limits: Limits | None = None, budget: RuntimeBudget | None = None) -> Model:
    """Inspect a .glb/.gltf file; local resources resolve only inside its directory."""
    return load_path(path, limits, budget)


def inspect_bytes(
    data: bytes, name: str = "asset", limits: Limits | None = None, budget: RuntimeBudget | None = None
) -> Model:
    """Inspect in-memory bytes; external file references are recorded but never resolved."""
    return analyze(data, name=name, base_dir=None, limits=limits, budget=budget)


def report(model: Model, **kwargs: Any) -> dict[str, Any]:
    """Build a ``finalverse.asset-intelligence/v1`` report (see reporting.build for keyword arguments)."""
    from .reporting import build

    return build(model, **kwargs)


def report_for_path(
    path: str | Path, *, limits: Limits | None = None, budget: RuntimeBudget | None = None, **kwargs: Any
) -> dict[str, Any]:
    return report(inspect_path(path, limits, budget), **kwargs)
