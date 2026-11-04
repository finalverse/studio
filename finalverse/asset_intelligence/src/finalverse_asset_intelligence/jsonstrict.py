"""Strict, bounded JSON parsing for untrusted glTF documents.

* nesting depth is measured *before* parsing (no recursion exhaustion);
* duplicate object keys and non-finite numbers are reported, not silently accepted;
* array lengths are bounded after parsing.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .context import Ctx

_TOKENS = re.compile(r'"(?:[^"\\]|\\.)*"|[\[\]{}]', re.S)


def max_depth(text: str, limit: int) -> int:
    depth = peak = 0
    for m in _TOKENS.finditer(text):
        t = m.group()
        if t in "[{":
            depth += 1
            if depth > peak:
                peak = depth
                if peak > limit:
                    return peak
        elif t in "]}":
            depth -= 1
    return peak


def parse(raw: bytes, ctx: Ctx, pointer: str = "/") -> Any:
    lim = ctx.limits
    if len(raw) > lim.max_json_bytes:
        raise ctx.abort(
            "FVA-RES-002",
            pointer,
            "JSON exceeds the maximum inspected size",
            {"byte_length": len(raw), "max_json_bytes": lim.max_json_bytes},
        )
    if raw.startswith(b"\xef\xbb\xbf"):
        ctx.add("FVA-CON-006", pointer, "JSON must not start with a UTF-8 byte-order mark", severity="error")
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ctx.abort("FVA-CON-006", pointer, "JSON is not valid UTF-8", {"offset": e.start}) from None
    depth = max_depth(text, lim.max_json_depth)
    if depth > lim.max_json_depth:
        raise ctx.abort(
            "FVA-RES-002", pointer, "JSON nesting exceeds the maximum depth", {"max_json_depth": lim.max_json_depth}
        )

    duplicates: list[str] = []
    nonfinite: list[str] = []

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in items:
            if k in out:
                duplicates.append(k)
            out[k] = v
        return out

    def const(name: str) -> float:
        nonfinite.append(name)
        return math.nan

    def flt(s: str) -> float:
        v = float(s)
        if not math.isfinite(v):
            nonfinite.append(s[:32])
        return v

    try:
        doc = json.loads(text, object_pairs_hook=pairs, parse_constant=const, parse_float=flt)
    except RecursionError:
        raise ctx.abort("FVA-RES-002", pointer, "JSON nesting exceeds the parser's recursion limit") from None
    except ValueError as e:
        raise ctx.abort("FVA-CON-006", pointer, "JSON syntax error", {"detail": str(e)[:200]}) from None
    if duplicates:
        ctx.add(
            "FVA-CON-007",
            pointer,
            "JSON contains duplicate object keys",
            {"keys": sorted(set(duplicates))[:32], "count": len(duplicates)},
        )
    if nonfinite:
        ctx.add(
            "FVA-CON-008",
            pointer,
            "JSON contains non-finite numbers",
            {"tokens": sorted(set(nonfinite))[:16], "count": len(nonfinite)},
        )

    stack = [doc]
    while stack:
        v = stack.pop()
        if isinstance(v, list):
            if len(v) > lim.max_array_length:
                raise ctx.abort(
                    "FVA-RES-002",
                    pointer,
                    "JSON array exceeds the maximum length",
                    {"length": len(v), "max_array_length": lim.max_array_length},
                )
            stack.extend(x for x in v if isinstance(x, (list, dict)))
        elif isinstance(v, dict):
            stack.extend(x for x in v.values() if isinstance(x, (list, dict)))
    return doc
