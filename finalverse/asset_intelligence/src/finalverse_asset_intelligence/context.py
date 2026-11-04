"""Per-inspection state: limits, budget, findings, time and decode accounting."""

from __future__ import annotations

import time
from typing import Any

from .findings import Collector
from .limits import Limits, RuntimeBudget


class Abort(Exception):
    """The inspection cannot continue; a critical finding has been recorded."""


class Ctx:
    def __init__(self, limits: Limits, budget: RuntimeBudget) -> None:
        self.limits = limits
        self.budget = budget
        self.findings = Collector()
        self._started = time.monotonic()
        self._ticks = 0
        self.decoded_components = 0
        self.incomplete_reasons: set[str] = set()

    def add(
        self, code: str, pointer: str, message: str, evidence: dict[str, Any] | None = None, severity: str | None = None
    ):
        return self.findings.add(code, pointer, message, evidence, severity)

    def abort(self, code: str, pointer: str, message: str, evidence: dict[str, Any] | None = None) -> Abort:
        self.add(code, pointer, message, evidence)
        self.incomplete_reasons.add(code)
        return Abort(message)

    def tick(self, weight: int = 1) -> None:
        """Cooperative time check, cheap enough for inner loops."""
        self._ticks += weight
        if self._ticks >= 4096:
            self._ticks = 0
            if time.monotonic() - self._started > self.limits.time_budget_seconds:
                raise self.abort(
                    "FVA-RES-004",
                    "/",
                    "Inspection exceeded its time budget and stopped early",
                    {"time_budget_seconds": self.limits.time_budget_seconds},
                )

    def charge(self, components: int, pointer: str) -> bool:
        """Account decoded accessor components. Returns False once the budget is exhausted."""
        if self.decoded_components + components > self.limits.max_decoded_components:
            self.add(
                "FVA-RES-003",
                pointer,
                "Accessor data not decoded: decode budget exhausted",
                {"max_decoded_components": self.limits.max_decoded_components},
            )
            self.incomplete_reasons.add("FVA-RES-003")
            return False
        self.decoded_components += components
        return True
