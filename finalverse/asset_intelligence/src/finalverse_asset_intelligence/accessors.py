"""Bounded validation and decoding of glTF buffers, bufferViews and accessors."""

from __future__ import annotations

import math
import struct
from array import array
from dataclasses import dataclass
from typing import Any

from .context import Ctx

COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
COMPONENT_NAME = {
    5120: "BYTE",
    5121: "UNSIGNED_BYTE",
    5122: "SHORT",
    5123: "UNSIGNED_SHORT",
    5125: "UNSIGNED_INT",
    5126: "FLOAT",
}
TYPE = {
    "SCALAR": (1, 1),
    "VEC2": (2, 1),
    "VEC3": (3, 1),
    "VEC4": (4, 1),
    "MAT2": (2, 2),
    "MAT3": (3, 3),
    "MAT4": (4, 4),
}  # (rows, columns)
NORMALIZE_DIV = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}


def is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def hkey(v: Any) -> Any:
    """Return v if it can be safely used as a lookup key (hashable JSON scalar, not bool), else None."""
    return v if isinstance(v, (str, int, float)) and not isinstance(v, bool) else None


def list_len(v: Any) -> int:
    return len(v) if isinstance(v, list) else 0


def is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


@dataclass
class Decoded:
    values: list[float] | list[int]  # flat, n * components
    count: int
    components: int
    component_type: int
    normalized: bool

    def element(self, i: int):
        c = self.components
        return self.values[i * c : (i + 1) * c]

    def elements(self):
        c = self.components
        v = self.values
        if c == 1:
            return list(v)
        return [v[i : i + c] for i in range(0, len(v), c)]


def element_layout(component_type: int, type_name: str) -> tuple[int, int, int]:
    """(element_size, column_stride, rows) honouring glTF matrix column padding."""
    rows, cols = TYPE[type_name]
    size = COMPONENT[component_type][1]
    col_stride = rows * size
    if cols > 1 and size < 4:
        col_stride = (col_stride + 3) // 4 * 4
    return col_stride * cols if cols > 1 else rows * size, col_stride, rows


class Accessors:
    def __init__(self, doc: dict, ctx: Ctx, buffers: list[bytes | None]) -> None:
        self.ctx = ctx
        self.doc = doc
        self.buffers = buffers
        self.views: list[dict] = [v if isinstance(v, dict) else {} for v in _arr(doc, "bufferViews", ctx)]
        self.accessors: list[dict] = [a if isinstance(a, dict) else {} for a in _arr(doc, "accessors", ctx)]
        self.view_ok: list[bool] = [self._check_view(i) for i in range(len(self.views))]
        self.acc_ok: list[bool] = [self._check_accessor(i) for i in range(len(self.accessors))]
        self._cache: dict[int, Decoded | None] = {}
        self.decoded_ok: set[int] = set()

    # -- structural checks ---------------------------------------------------------
    def _check_view(self, i: int) -> bool:
        ctx, v, p = self.ctx, self.views[i], f"/bufferViews/{i}"
        b, off, length = v.get("buffer"), v.get("byteOffset", 0), v.get("byteLength")
        if not (is_int(b) and is_int(off) and is_int(length) and off >= 0 and length >= 1):
            ctx.add("FVA-CON-009", p, "bufferView requires integer buffer, byteLength >= 1 and byteOffset >= 0")
            return False
        if not 0 <= b < len(self.buffers):
            ctx.add("FVA-CON-011", p + "/buffer", "bufferView references a missing buffer", {"buffer": b})
            return False
        stride = v.get("byteStride")
        if stride is not None and not (is_int(stride) and 4 <= stride <= 252 and stride % 4 == 0):
            ctx.add(
                "FVA-BUF-004",
                p + "/byteStride",
                "byteStride must be 4..252 and a multiple of 4",
                {"byteStride": stride},
            )
            return False
        declared = self._buffer_length(b)
        if declared is not None and off + length > declared:
            ctx.add(
                "FVA-BUF-003", p, "bufferView exceeds its buffer", {"end": off + length, "buffer_byte_length": declared}
            )
            return False
        return True

    def _buffer_length(self, b: int) -> int | None:
        bl = self.doc.get("buffers", [])
        if isinstance(bl, list) and b < len(bl) and isinstance(bl[b], dict) and is_int(bl[b].get("byteLength")):
            return bl[b]["byteLength"]
        return None

    def _check_accessor(self, i: int) -> bool:
        ctx, a, p = self.ctx, self.accessors[i], f"/accessors/{i}"
        ct, tn, count = hkey(a.get("componentType")), hkey(a.get("type")), a.get("count")
        if ct not in COMPONENT or not isinstance(tn, str) or tn not in TYPE or not is_int(count) or count < 1:
            ctx.add(
                "FVA-BUF-007",
                p,
                "accessor requires a valid componentType, type and count >= 1",
                {"componentType": ct, "type": tn, "count": count},
            )
            return False
        if a.get("normalized") is True and ct in (5125, 5126):
            ctx.add("FVA-BUF-007", p + "/normalized", "normalized is only allowed for 8/16-bit integer components")
            return False
        rows, cols = TYPE[tn]
        if tn.startswith("MAT") and ct not in (5120, 5121, 5122, 5123, 5126):
            ctx.add("FVA-BUF-007", p, "matrix accessors cannot use UNSIGNED_INT")
            return False
        n_comp = rows * cols
        for k in ("min", "max"):
            if k in a and not (isinstance(a[k], list) and len(a[k]) == n_comp and all(is_num(x) for x in a[k])):
                ctx.add("FVA-CON-009", f"{p}/{k}", f"accessor {k} must have {n_comp} numbers")
        aoff = a.get("byteOffset", 0)
        if not is_int(aoff) or aoff < 0:
            ctx.add("FVA-CON-009", p + "/byteOffset", "byteOffset must be a non-negative integer")
            return False
        csize = COMPONENT[ct][1]
        ok = True
        if "bufferView" in a:
            vi = a["bufferView"]
            if not is_int(vi) or not 0 <= vi < len(self.views):
                ctx.add(
                    "FVA-CON-011", p + "/bufferView", "accessor references a missing bufferView", {"bufferView": vi}
                )
                return False
            if not self.view_ok[vi]:
                return False
            v = self.views[vi]
            esize, _, _ = element_layout(ct, tn)
            stride = v.get("byteStride") or esize
            if v.get("byteStride") is not None and v["byteStride"] < esize:
                ctx.add(
                    "FVA-BUF-004",
                    f"/bufferViews/{vi}/byteStride",
                    "byteStride is smaller than the element size",
                    {"byteStride": v["byteStride"], "element_size": esize},
                )
                ok = False
            if aoff % csize or (v.get("byteOffset", 0) + aoff) % csize:
                ctx.add(
                    "FVA-BUF-006", p, "accessor offset is not aligned to its component size", {"component_size": csize}
                )
                ok = False
            need = aoff + stride * (count - 1) + esize
            if need > v["byteLength"]:
                ctx.add(
                    "FVA-BUF-005",
                    p,
                    "accessor data exceeds its bufferView",
                    {"required": need, "buffer_view_byte_length": v["byteLength"]},
                )
                ok = False
        if "sparse" in a:  # a present-but-null sparse is invalid, not absent
            ok = self._check_sparse(i, a, a["sparse"]) and ok
        return ok

    def _check_sparse(self, i: int, a: dict, s: Any) -> bool:
        ctx, p = self.ctx, f"/accessors/{i}/sparse"
        if not isinstance(s, dict) or not is_int(s.get("count")) or not 1 <= s["count"] <= a["count"]:
            ctx.add("FVA-BUF-011", p, "sparse.count must be between 1 and accessor.count")
            return False
        ind, val = s.get("indices"), s.get("values")
        if not isinstance(ind, dict) or not isinstance(val, dict):
            ctx.add("FVA-BUF-011", p, "sparse requires indices and values")
            return False
        if hkey(ind.get("componentType")) not in (5121, 5123, 5125):
            ctx.add("FVA-BUF-011", p + "/indices/componentType", "sparse indices must be unsigned integers")
            return False
        for name, obj in (("indices", ind), ("values", val)):
            vi = obj.get("bufferView")
            if not is_int(vi) or not 0 <= vi < len(self.views) or not self.view_ok[vi]:
                ctx.add("FVA-BUF-011", f"{p}/{name}/bufferView", "sparse data references an invalid bufferView")
                return False
        return True

    # -- decoding ------------------------------------------------------------------
    def _raw_view(self, vi: int) -> bytes | None:
        v = self.views[vi]
        data = self.buffers[v["buffer"]]
        if data is None:
            return None
        off = v.get("byteOffset", 0)
        if off + v["byteLength"] > len(data):
            return None
        return data[off : off + v["byteLength"]]

    def _read(self, raw: bytes, offset: int, stride: int | None, count: int, ct: int, tn: str) -> list:
        fmt, csize = COMPONENT[ct]
        esize, col_stride, rows = element_layout(ct, tn)
        cols = TYPE[tn][1]
        packed = (stride is None or stride == esize) and (cols == 1 or col_stride == rows * csize)
        if packed:
            arr = array(fmt)
            arr.frombytes(raw[offset : offset + esize * count])
            if struct.pack("=H", 1) != struct.pack("<H", 1):
                arr.byteswap()
            return arr.tolist()
        step = stride or esize
        col = struct.Struct("<" + fmt * rows)
        out: list = []
        for e in range(count):
            base = offset + e * step
            for c in range(cols):
                out.extend(col.unpack_from(raw, base + c * col_stride))
            if e & 1023 == 0:
                self.ctx.tick(1024)
        return out

    def get(self, i: Any, pointer: str = "") -> Decoded | None:
        if not is_int(i) or not 0 <= i < len(self.accessors):
            if pointer:
                self.ctx.add("FVA-CON-011", pointer, "reference to a missing accessor", {"accessor": i})
            return None
        if i in self._cache:
            return self._cache[i]
        dec = self._decode(i) if self.acc_ok[i] else None
        self._cache[i] = dec
        return dec

    def _decode(self, i: int) -> Decoded | None:
        ctx, a, p = self.ctx, self.accessors[i], f"/accessors/{i}"
        ct, tn, count = a["componentType"], a["type"], a["count"]
        rows, cols = TYPE[tn]
        n_comp = rows * cols
        if not ctx.charge(count * n_comp, p):
            return None
        if "bufferView" in a:
            raw = self._raw_view(a["bufferView"])
            if raw is None:
                return None
            v = self.views[a["bufferView"]]
            values = self._read(raw, a.get("byteOffset", 0), v.get("byteStride"), count, ct, tn)
        else:
            values = [0] * (count * n_comp) if ct != 5126 else [0.0] * (count * n_comp)
        if "sparse" in a:
            s = a["sparse"]
            ind, val = s["indices"], s["values"]
            ri, rv = self._raw_view(ind["bufferView"]), self._raw_view(val["bufferView"])
            if ri is None or rv is None:
                return None
            try:
                idx = self._read(ri, ind.get("byteOffset", 0), None, s["count"], ind["componentType"], "SCALAR")
                sv = self._read(rv, val.get("byteOffset", 0), None, s["count"], ct, tn)
            except struct.error:
                ctx.add("FVA-BUF-011", p + "/sparse", "sparse data exceeds its bufferView")
                return None
            if len(idx) != s["count"] or len(sv) != s["count"] * n_comp:
                ctx.add("FVA-BUF-011", p + "/sparse", "sparse data exceeds its bufferView")
                return None
            if any(b <= a_ for a_, b in zip(idx, idx[1:])) or any(x >= count for x in idx):
                ctx.add("FVA-BUF-011", p + "/sparse/indices", "sparse indices must be strictly increasing and < count")
                return None
            for k, at in enumerate(idx):
                values[at * n_comp : (at + 1) * n_comp] = sv[k * n_comp : (k + 1) * n_comp]
        normalized = bool(a.get("normalized")) and ct in NORMALIZE_DIV
        if normalized:
            d = NORMALIZE_DIV[ct]
            values = [max(x / d, -1.0) for x in values]
        if ct == 5126 or normalized:
            bad = sum(1 for x in values if not math.isfinite(x))
            if bad:
                ctx.add("FVA-BUF-010", p, "float accessor contains NaN or infinite values", {"nonfinite_values": bad})
        self.decoded_ok.add(i)
        return Decoded(values, count, n_comp, ct, normalized)

    def check_bounds(self, i: int, dec: Decoded, required: bool, pointer: str) -> None:
        """Compare declared min/max with decoded data (spec: MUST be accurate when present)."""
        a = self.accessors[i]
        p = f"/accessors/{i}"
        if "min" not in a or "max" not in a:
            if required:
                self.ctx.add("FVA-BUF-009", p, "accessor min/max are required here", {"used_by": pointer})
            return
        n = dec.components
        if not (isinstance(a["min"], list) and isinstance(a["max"], list) and len(a["min"]) == n == len(a["max"])):
            return
        vals = dec.values
        lo = [math.inf] * n
        hi = [-math.inf] * n
        for k in range(0, len(vals), n):
            for c in range(n):
                x = vals[k + c]
                if x < lo[c]:
                    lo[c] = x
                if x > hi[c]:
                    hi[c] = x
        tol = 1e-4
        for c in range(n):
            if not (math.isfinite(lo[c]) and math.isfinite(hi[c])):
                return
            dmin, dmax = a["min"][c], a["max"][c]
            if not (is_num(dmin) and is_num(dmax)):
                return
            if abs(dmin - lo[c]) > tol * max(1.0, abs(lo[c])) or abs(dmax - hi[c]) > tol * max(1.0, abs(hi[c])):
                self.ctx.add(
                    "FVA-BUF-008",
                    p,
                    "declared accessor min/max differ from the data",
                    {
                        "declared_min": a["min"][:4],
                        "declared_max": a["max"][:4],
                        "actual_min": [round(x, 6) for x in lo][:4],
                        "actual_max": [round(x, 6) for x in hi][:4],
                    },
                )
                return


def _arr(doc: dict, key: str, ctx: Ctx) -> list:
    v = doc.get(key, [])
    if not isinstance(v, list):
        ctx.add("FVA-CON-009", f"/{key}", f"{key} must be an array")
        return []
    for i, x in enumerate(v):
        if not isinstance(x, dict):
            ctx.add("FVA-CON-009", f"/{key}/{i}", f"{key} entries must be objects")
    return v


arr_of = _arr
