"""Deterministic glTF/GLB writer used to build S3-A fixtures and negative test cases.

This is test tooling, not part of the library.  Output bytes depend only on the
calls made, so fixtures are reproducible bit-for-bit.
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from typing import Any

FMT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
RAW = "__RAW_NUMBER__"


class Builder:
    def __init__(self, generator: str = "Finalverse S3-A fixture builder/1") -> None:
        self.doc: dict[str, Any] = {"asset": {"generator": generator, "version": "2.0"}}
        self.bin = bytearray()
        self.raw_tokens: dict[str, str] = {}

    def add(self, key: str, obj: dict) -> int:
        self.doc.setdefault(key, []).append(obj)
        return len(self.doc[key]) - 1

    def view(self, data: bytes, target: int | None = None) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        v: dict[str, Any] = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target is not None:
            v["target"] = target
        self.bin += data
        return self.add("bufferViews", v)

    def accessor(
        self,
        rows: list,
        ctype: int,
        kind: str,
        minmax: bool = False,
        target: int | None = None,
        normalized: bool = False,
    ) -> int:
        n = WIDTH[kind]
        flat = [x for r in rows for x in (r if isinstance(r, (list, tuple)) else (r,))]
        assert len(flat) == len(rows) * n
        data = struct.pack(f"<{len(flat)}{FMT[ctype]}", *flat)
        a: dict[str, Any] = {
            "bufferView": self.view(data, target),
            "componentType": ctype,
            "count": len(rows),
            "type": kind,
        }
        if normalized:
            a["normalized"] = True
        if minmax:
            cols = [[r[i] if isinstance(r, (list, tuple)) else r for r in rows] for i in range(n)]
            a["min"] = [_num(min(c)) for c in cols]
            a["max"] = [_num(max(c)) for c in cols]
        return self.add("accessors", a)

    def raw(self, token: str) -> str:
        """A placeholder replaced verbatim in the JSON (e.g. an overflowing number)."""
        key = f"{RAW}{len(self.raw_tokens)}"
        self.raw_tokens[key] = token
        return key

    def json_bytes(self, buffers: list[dict]) -> bytes:
        doc = dict(self.doc)
        doc["buffers"] = buffers
        text = json.dumps(doc, separators=(",", ":"), ensure_ascii=True)
        for key, tok in self.raw_tokens.items():
            text = text.replace(f'"{key}"', tok)
        return text.encode("utf-8")

    def glb(self) -> bytes:
        while len(self.bin) % 4:
            self.bin.append(0)
        j = self.json_bytes([{"byteLength": len(self.bin)}] if self.bin else [])
        j += b" " * (-len(j) % 4)
        out = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(j) + (8 + len(self.bin) if self.bin else 0))
        out += struct.pack("<I4s", len(j), b"JSON") + j
        if self.bin:
            out += struct.pack("<I4s", len(self.bin), b"BIN\x00") + bytes(self.bin)
        return out

    def gltf(self, bin_uri: str) -> tuple[bytes, bytes]:
        j = self.json_bytes([{"byteLength": len(self.bin), "uri": bin_uri}])
        return j, bytes(self.bin)


def _num(v):
    return float(v) if isinstance(v, float) else v


def box(cx, cy, cz, sx, sy, sz):
    """Axis-aligned box: 24 vertices with outward face normals, 12 CCW triangles."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    faces = [
        ((1, 0, 0), [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)]),
        ((-1, 0, 0), [(-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, -1, -1)]),
        ((0, 1, 0), [(-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)]),
        ((0, -1, 0), [(-1, -1, 1), (-1, -1, -1), (1, -1, -1), (1, -1, 1)]),
        ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
        ((0, 0, -1), [(1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)]),
    ]
    pos, nrm, uv, idx = [], [], [], []
    for n, quad in faces:
        base = len(pos)
        for k, (x, y, z) in enumerate(quad):
            pos.append((cx + x * hx, cy + y * hy, cz + z * hz))
            nrm.append(n)
            uv.append(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))[k])
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return pos, nrm, uv, idx


def octahedron(cx, cy, cz, r):
    """Flat-shaded octahedron: 8 faces x 3 vertices."""
    v = [(r, 0, 0), (-r, 0, 0), (0, r, 0), (0, -r, 0), (0, 0, r), (0, 0, -r)]
    tris = [(0, 2, 4), (4, 2, 1), (1, 2, 5), (5, 2, 0), (4, 3, 0), (1, 3, 4), (5, 3, 1), (0, 3, 5)]
    pos, nrm, idx = [], [], []
    for a, b, c in tris:
        pa, pb, pc = v[a], v[b], v[c]
        u = [pb[i] - pa[i] for i in range(3)]
        w = [pc[i] - pa[i] for i in range(3)]
        n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        ln = math.sqrt(sum(x * x for x in n))
        n = tuple(x / ln for x in n)
        for p in (pa, pb, pc):
            idx.append(len(pos))
            pos.append((cx + p[0], cy + p[1], cz + p[2]))
            nrm.append(n)
    return pos, nrm, idx


def quat(axis, degrees):
    a = math.radians(degrees) / 2
    s = math.sin(a)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(a))


def png(width: int, height: int, rgba: tuple[int, int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
