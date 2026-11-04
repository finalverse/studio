"""Minimal column-major 4x4 matrix helpers (glTF convention)."""

from __future__ import annotations

import math
from collections.abc import Sequence

Mat4 = list[float]
IDENTITY: Mat4 = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def mul(a: Sequence[float], b: Sequence[float]) -> Mat4:
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = (
                a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3]
            )
    return out


def from_trs(t: Sequence[float], q: Sequence[float], s: Sequence[float]) -> Mat4:
    x, y, z, w = q
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz, wx, wy, wz = x * y, x * z, y * z, w * x, w * y, w * z
    return [
        (1 - 2 * (yy + zz)) * s[0],
        (2 * (xy + wz)) * s[0],
        (2 * (xz - wy)) * s[0],
        0.0,
        (2 * (xy - wz)) * s[1],
        (1 - 2 * (xx + zz)) * s[1],
        (2 * (yz + wx)) * s[1],
        0.0,
        (2 * (xz + wy)) * s[2],
        (2 * (yz - wx)) * s[2],
        (1 - 2 * (xx + yy)) * s[2],
        0.0,
        t[0],
        t[1],
        t[2],
        1.0,
    ]


def apply(m: Sequence[float], p: Sequence[float]) -> tuple[float, float, float]:
    x, y, z = p
    return (
        m[0] * x + m[4] * y + m[8] * z + m[12],
        m[1] * x + m[5] * y + m[9] * z + m[13],
        m[2] * x + m[6] * y + m[10] * z + m[14],
    )


def det3(m: Sequence[float]) -> float:
    return (
        m[0] * (m[5] * m[10] - m[9] * m[6]) - m[4] * (m[1] * m[10] - m[9] * m[2]) + m[8] * (m[1] * m[6] - m[5] * m[2])
    )


def inverse(m: Sequence[float]) -> Mat4 | None:
    """Gauss-Jordan inverse; None if singular or non-finite."""
    a = [[m[c * 4 + r] for c in range(4)] + [1.0 if r == k else 0.0 for k in range(4)] for r in range(4)]
    for col in range(4):
        piv = max(range(col, 4), key=lambda r: abs(a[r][col]))
        if not math.isfinite(a[piv][col]) or abs(a[piv][col]) < 1e-12:
            return None
        a[col], a[piv] = a[piv], a[col]
        p = a[col][col]
        a[col] = [v / p for v in a[col]]
        for r in range(4):
            if r != col:
                f = a[r][col]
                if f:
                    a[r] = [x - f * y for x, y in zip(a[r], a[col])]
    return [a[r][4 + c] for c in range(4) for r in range(4)]


def max_abs_diff(a: Sequence[float], b: Sequence[float]) -> float:
    return max(abs(x - y) for x, y in zip(a, b))


def finite(values) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)
