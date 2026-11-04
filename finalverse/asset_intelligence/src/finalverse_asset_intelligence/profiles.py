"""Runtime compatibility profiles derived from actual Finalverse admission code.

Each profile reproduces, rule by rule and in the same order, an admission routine
found in a Finalverse repository.  The original routines stop at their first
error; so do these, and rules after the first failure are ``not_evaluated``.

Sources (GitHub state inspected for S3-A):

* finalverse/finalverse @ 3cd0e93  crates/ec/src/geometry.rs        ``validate_glb``
* finalverse/finalverse @ 3cd0e93  crates/embodiment/src/lib.rs     ``Asset::load``
* finalverse/infinity   @ 664445f  src/entry.rs                     ``decode_parts``

Reproduction is in f64 Python; the originals use f32 for some geometric tests,
so values within ~1e-6 of a threshold can be classified differently.  The
differential harness in docs/S3A-TESTING.md compares against the Rust originals.
"""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import mathutil as mu
from .accessors import is_int, is_num

EC_SRC = {
    "repository": "finalverse/finalverse",
    "commit": "3cd0e93",
    "path": "crates/ec/src/geometry.rs",
    "symbol": "validate_glb",
}
E0_SRC = {
    "repository": "finalverse/finalverse",
    "commit": "3cd0e93",
    "path": "crates/embodiment/src/lib.rs",
    "symbol": "Asset::load",
}
E0_DOC = {
    "repository": "finalverse/finalverse",
    "commit": "3cd0e93",
    "path": "docs/genesis/E0-HUMANOID-STANDARD.md",
    "symbol": "Finalverse humanoid v1",
}
INF_SRC = {"repository": "finalverse/infinity", "commit": "664445f", "path": "src/entry.rs", "symbol": "decode_parts"}
INF_E0 = {
    "repository": "finalverse/infinity",
    "commit": "664445f",
    "path": "src/bin/embodiment-render.rs",
    "symbol": "Asset::load (embodiment render path)",
}

E0_JOINTS = (
    "root",
    "pelvis",
    "spine",
    "chest",
    "neck",
    "head",
    "shoulder_l",
    "upper_arm_l",
    "forearm_l",
    "hand_l",
    "shoulder_r",
    "upper_arm_r",
    "forearm_r",
    "hand_r",
    "thigh_l",
    "shin_l",
    "foot_l",
    "thigh_r",
    "shin_r",
    "foot_r",
    "eye_l",
    "eye_r",
    "jaw",
    "tool_l",
    "tool_r",
    "crown",
)
E0_PARENTS = (None, 0, 1, 2, 3, 4, 3, 6, 7, 8, 3, 10, 11, 12, 1, 14, 15, 1, 17, 18, 5, 5, 5, 9, 13, 5)
E0_CLIPS = (
    "idle",
    "walk",
    "turn",
    "greet",
    "listen",
    "speak",
    "point",
    "inspect",
    "explain",
    "converse",
    "sit",
    "stand",
)


class _Fail(Exception):
    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(detail)
        self.rule = rule
        self.detail = detail


@dataclass
class ProfileResult:
    id: str
    title: str
    contract_status: str
    sources: list[dict]
    rules: list[dict]
    status: str = "not_evaluated"
    notes: list[str] = field(default_factory=list)
    material_feature_support: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "contract": {"status": self.contract_status, "sources": self.sources},
            "rules": self.rules,
            "notes": self.notes,
        }
        if self.material_feature_support is not None:
            out["material_feature_support"] = self.material_feature_support
        return out

    @property
    def failed(self) -> list[dict]:
        return [r for r in self.rules if r["outcome"] == "fail"]


class _Seq:
    def __init__(self, rules: list[tuple[str, str]]) -> None:
        self.rules = rules
        self.done: set[str] = set()
        self.unverified: dict[str, str] = {}

    def need(self, rule: str, ok: bool, detail: str) -> None:
        if not ok:
            raise _Fail(rule, detail)

    def finish(self, rule: str) -> None:
        self.done.add(rule)

    def result(self, fail: _Fail | None) -> list[dict]:
        out = []
        for rid, text in self.rules:
            if fail is not None and rid == fail.rule:
                out.append({"rule": rid, "requirement": text, "outcome": "fail", "detail": fail.detail})
            elif rid in self.unverified:
                out.append({"rule": rid, "requirement": text, "outcome": "unverified", "detail": self.unverified[rid]})
            elif rid in self.done:
                out.append({"rule": rid, "requirement": text, "outcome": "pass"})
            else:
                out.append({"rule": rid, "requirement": text, "outcome": "not_evaluated"})
        return out


def _strict_eq(a: Any, b: Any) -> bool:
    """serde_json::Value equality: integers are not floats, booleans are not integers."""
    if isinstance(b, bool) or isinstance(a, bool):
        return type(a) is type(b) and a == b
    if isinstance(b, int):
        return is_int(a) and a == b
    if isinstance(b, float):
        return isinstance(a, float) and a == b
    if isinstance(b, list):
        return isinstance(a, list) and len(a) == len(b) and all(_strict_eq(x, y) for x, y in zip(a, b))
    if isinstance(b, dict):
        return isinstance(a, dict) and a.keys() == b.keys() and all(_strict_eq(a[k], b[k]) for k in b)
    return a == b


def _u64(v: Any) -> int | None:
    return v if is_int(v) and v >= 0 else None


def _glb_parts(data: bytes) -> tuple[int, bytes, bytes] | None:
    """(json_len, json_bytes, bin_bytes) for a two-chunk GLB, else None."""
    if len(data) < 28 or data[:4] != b"glTF":
        return None
    jl = struct.unpack_from("<I", data, 12)[0]
    end = 20 + jl
    if end + 8 > len(data):
        return None
    return jl, data[20:end], data[end + 8 :]


def _strict_json(m, raw: bytes) -> Any | None:
    """Value as Finalverse ``sil::strict_json`` would produce it, or None if it refuses."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    dup = []

    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                dup.append(k)
            d[k] = v
        return d

    bad = []

    def flt(s):
        v = float(s)
        if not math.isfinite(v):
            bad.append(s)
        return v

    def const(s):
        bad.append(s)
        return math.nan

    try:
        v = json.loads(text, object_pairs_hook=pairs, parse_float=flt, parse_constant=const)
    except (ValueError, RecursionError):
        return None
    return None if dup or bad else v


def _forbidden(v: Any, keys: tuple[str, ...], max_array: int, depth: int = 0) -> bool:
    """True when the value is 'safe': no forbidden key, depth <= 16, bounded arrays."""
    if depth > 16:
        return False
    if isinstance(v, dict):
        return all(k not in keys and _forbidden(x, keys, max_array, depth + 1) for k, x in v.items())
    if isinstance(v, list):
        return len(v) <= max_array and all(_forbidden(x, keys, max_array, depth + 1) for x in v)
    return True


def _f32(b: bytes, n: int) -> list[float]:
    return list(struct.unpack_from(f"<{n}f", b, 0)) if n else []


# ----------------------------------------------------------------------------- EC static
EC_RULES = [
    ("EC-01", "Bounded GLB v2 (<= 2 MiB, declared length equals file length, JSON first chunk)"),
    ("EC-02", "JSON chunk 1..262144 bytes, 4-byte aligned, followed by exactly one BIN chunk ending at EOF"),
    ("EC-03", "UTF-8, strict duplicate-free JSON with finite numbers"),
    ("EC-04", "Only reviewed top-level properties; asset.version 2.0; scene 0; scenes [{nodes:[0]}]; nodes [{mesh:0}]"),
    ("EC-05", "No uri, extensions, images, textures, shaders, scripts, animations, skins or morph targets anywhere"),
    ("EC-06", "Exactly one buffer with only byteLength equal to the BIN chunk length"),
    ("EC-07", "At most 256 bufferViews and 256 accessors"),
    ("EC-08", "1..8 materials with only name/pbrMetallicRoughness/emissiveFactor/doubleSided/extras"),
    ("EC-09", "Each material has baseColorFactor[4], metallicFactor, roughnessFactor and emissiveFactor[3] in [0,1]"),
    ("EC-10", "Exactly one mesh with 1..8 indexed-triangle primitives referencing existing materials"),
    ("EC-11", "Attributes exactly POSITION, NORMAL, TEXCOORD_0 (float) with uint32 indices; tightly packed, aligned"),
    ("EC-12", "Equal attribute counts; at most 32768 vertices and 32768 triangles; index count multiple of 3"),
    ("EC-13", "Finite positions |v|<=1000, unit normals (|n|^2 in [0.98,1.02]), finite UVs |v|<=10000"),
    ("EC-14", "POSITION min/max present and within 1e-4 of decoded data"),
    ("EC-15", "Indices inside the vertex buffer and no degenerate triangles"),
    ("EC-16", "Vertex normals lie in the front hemisphere of each triangle (winding agrees with normals)"),
]


def ec_static(m) -> ProfileResult:
    r = ProfileResult(
        "finalverse.ec-static-glb/v1",
        "Finalverse EC static GLB subset (G0 static geometry admission)",
        "accepted",
        [EC_SRC],
        [],
    )
    seq = _Seq(EC_RULES)
    fail = None
    try:
        _ec(m.data, seq)
    except _Fail as e:
        fail = e
    r.rules = seq.result(fail)
    r.status = "incompatible" if fail else "compatible"
    return r


def _ec(b: bytes, s: _Seq) -> None:
    MAXB, MAXV, MAXT = 2 * 1024 * 1024, 32768, 32768
    word = lambda o: struct.unpack_from("<I", b, o)[0]  # noqa: E731
    s.need(
        "EC-01",
        28 <= len(b) <= MAXB and b[:4] == b"glTF" and word(4) == 2 and word(8) == len(b) and b[16:20] == b"JSON",
        "A bounded GLB v2 document is required",
    )
    s.finish("EC-01")
    jl = word(12)
    s.need("EC-02", 0 < jl <= 262144 and jl % 4 == 0 and jl + 28 <= len(b), "Invalid GLB JSON chunk")
    bo = 28 + jl
    s.need(
        "EC-02",
        b[24 + jl : 28 + jl] == b"BIN\x00" and word(20 + jl) + bo == len(b),
        "A single self-contained binary chunk is required",
    )
    s.finish("EC-02")
    doc = None
    try:
        doc = _strict_json(None, b[20 : 20 + jl].decode("utf-8").encode("utf-8"))
    except UnicodeDecodeError:
        pass
    s.need("EC-03", doc is not None, "Strict, duplicate-free JSON required")
    s.finish("EC-03")
    allowed = {
        "asset",
        "scene",
        "scenes",
        "nodes",
        "meshes",
        "materials",
        "buffers",
        "bufferViews",
        "accessors",
        "extras",
    }
    s.need(
        "EC-04",
        isinstance(doc, dict)
        and set(doc) <= allowed
        and isinstance(doc.get("asset"), dict)
        and _strict_eq(doc["asset"].get("version"), "2.0")
        and _strict_eq(doc.get("scene"), 0)
        and _strict_eq(doc.get("scenes"), [{"nodes": [0]}])
        and _strict_eq(doc.get("nodes"), [{"mesh": 0}]),
        "Only the reviewed static single-node mesh subset is supported",
    )
    s.finish("EC-04")
    s.need(
        "EC-05",
        _forbidden(
            doc,
            (
                "uri",
                "extensions",
                "extensionsRequired",
                "extensionsUsed",
                "images",
                "textures",
                "shaders",
                "scripts",
                "animations",
                "skins",
                "targets",
            ),
            4096,
        ),
        "External references, executable content, extensions and unsupported resources are refused",
    )
    s.finish("EC-05")
    bufs = doc.get("buffers")
    s.need("EC-06", isinstance(bufs, list), "Buffers required")
    s.need(
        "EC-06",
        len(bufs) == 1
        and isinstance(bufs[0], dict)
        and len(bufs[0]) == 1
        and _u64(bufs[0].get("byteLength")) == len(b) - bo,
        "Binary buffer length differs",
    )
    s.finish("EC-06")
    views, accs = doc.get("bufferViews"), doc.get("accessors")
    s.need("EC-07", isinstance(views, list), "Buffer views required")
    s.need("EC-07", isinstance(accs, list), "Accessors required")
    s.need("EC-07", len(views) <= 256 and len(accs) <= 256, "Too many buffer views or accessors")
    s.finish("EC-07")
    mats = doc.get("materials")
    s.need("EC-08", isinstance(mats, list), "Material table required")
    s.need("EC-08", 1 <= len(mats) <= 8, "Material count exceeds budget")
    for mt in mats:
        s.need(
            "EC-08",
            isinstance(mt, dict)
            and set(mt) <= {"name", "pbrMetallicRoughness", "emissiveFactor", "doubleSided", "extras"},
            "Unsupported material field",
        )
        pbr = mt.get("pbrMetallicRoughness")
        s.need(
            "EC-08",
            isinstance(pbr, dict) and set(pbr) <= {"baseColorFactor", "roughnessFactor", "metallicFactor"},
            "Unreviewed material features refused",
        )
        unit = lambda v: is_num(v) and math.isfinite(v) and 0.0 <= v <= 1.0  # noqa: E731
        bc = pbr.get("baseColorFactor")
        s.need("EC-09", isinstance(bc, list) and len(bc) == 4 and all(unit(x) for x in bc), "Invalid base color")
        s.need("EC-09", unit(pbr.get("roughnessFactor")) and unit(pbr.get("metallicFactor")), "Invalid PBR scalar")
        ef = mt.get("emissiveFactor")
        s.need("EC-09", isinstance(ef, list) and len(ef) == 3 and all(unit(x) for x in ef), "Invalid emissive factor")
    s.finish("EC-08")
    s.finish("EC-09")

    def read(ai, comps, ct, kind):
        a = accs[ai] if is_int(ai) and 0 <= ai < len(accs) else None
        s.need("EC-11", isinstance(a, dict), "Unknown accessor")
        s.need(
            "EC-11",
            _strict_eq(a.get("componentType"), ct)
            and _strict_eq(a.get("type"), kind)
            and "sparse" not in a
            and "normalized" not in a,
            "Unsupported accessor encoding",
        )
        count = _u64(a.get("count"))
        s.need("EC-11", count is not None and 0 < count <= MAXT * 3, "Accessor count exceeds budget")
        vi = a.get("bufferView")
        v = views[vi] if is_int(vi) and 0 <= vi < len(views) and isinstance(views[vi], dict) else None
        s.need("EC-11", v is not None, "Unknown buffer view")
        off = v.get("byteOffset", 0)
        off = off if _u64(off) is not None else 0
        ln = _u64(v.get("byteLength"))
        s.need("EC-11", ln is not None, "Missing view length")
        aoff = a.get("byteOffset", 0)
        aoff = aoff if _u64(aoff) is not None else 0
        req = count * comps * 4
        s.need(
            "EC-11",
            _strict_eq(v.get("buffer"), 0)
            and "byteStride" not in v
            and off <= MAXB
            and ln <= MAXB
            and aoff <= ln
            and req <= ln - aoff
            and off + ln <= len(b) - bo
            and (off + aoff) % 4 == 0,
            "Invalid accessor range or unsupported stride",
        )
        o = bo + off + aoff
        return b[o : o + req], count, a

    meshes = doc.get("meshes")
    s.need("EC-10", isinstance(meshes, list), "Meshes required")
    s.need("EC-10", len(meshes) == 1, "Exactly one bounded mesh is required")
    prims = meshes[0].get("primitives") if isinstance(meshes[0], dict) else None
    s.need("EC-10", isinstance(prims, list) and 1 <= len(prims) <= 8, "Primitive count exceeds limit")
    tv = tt = 0
    for p in prims:
        s.need(
            "EC-10",
            isinstance(p, dict)
            and _strict_eq(p.get("mode"), 4)
            and _u64(p.get("material")) is not None
            and p["material"] < len(mats),
            "Indexed triangle mode and known material are required",
        )
        at = p.get("attributes")
        s.need(
            "EC-11",
            isinstance(at, dict) and len(at) == 3 and all(k in at for k in ("POSITION", "NORMAL", "TEXCOORD_0")),
            "Positions, normals and UVs are required",
        )
        pos, count, pacc = read(at["POSITION"], 3, 5126, "VEC3")
        nrm, ncount, _ = read(at["NORMAL"], 3, 5126, "VEC3")
        uv, ucount, _ = read(at["TEXCOORD_0"], 2, 5126, "VEC2")
        ind, icount, _ = read(p.get("indices"), 1, 5125, "SCALAR")
        s.need(
            "EC-12", count == ncount == ucount and count <= MAXV and icount % 3 == 0, "Attribute/index counts differ"
        )
        tv += count
        tt += icount // 3
        s.need("EC-12", tv <= MAXV and tt <= MAXT, "Mesh exceeds vertex/triangle budget")
        P, N, U = _f32(pos, count * 3), _f32(nrm, count * 3), _f32(uv, count * 2)
        lo, hi = [math.inf] * 3, [-math.inf] * 3
        for i in range(count):
            pt, n = P[3 * i : 3 * i + 3], N[3 * i : 3 * i + 3]
            sq = n[0] * n[0] + n[1] * n[1] + n[2] * n[2]
            s.need(
                "EC-13",
                all(math.isfinite(x) and abs(x) <= 1000 for x in pt)
                and all(math.isfinite(x) for x in n)
                and 0.98 <= sq <= 1.02
                and all(math.isfinite(x) and abs(x) <= 10000 for x in U[2 * i : 2 * i + 2]),
                "Nonfinite, unbounded coordinates or invalid normals/UVs",
            )
            for k in range(3):
                lo[k], hi[k] = min(lo[k], pt[k]), max(hi[k], pt[k])
        for key, exp in (("min", lo), ("max", hi)):
            v = pacc.get(key)
            s.need(
                "EC-14",
                isinstance(v, list)
                and len(v) == 3
                and all(is_num(x) and math.isfinite(x) and abs(x - e) <= 1e-4 for x, e in zip(v, exp)),
                "Declared position bounds differ from decoded positions",
            )
        tri_idx = struct.unpack_from(f"<{icount}I", ind, 0)
        for t in range(0, icount - icount % 3, 3):
            ids = tri_idx[t : t + 3]
            s.need("EC-15", all(x < count for x in ids), "Triangle index outside vertex buffer")
            a, b2, c = (P[3 * x : 3 * x + 3] for x in ids)
            u = [b2[k] - a[k] for k in range(3)]
            w = [c[k] - a[k] for k in range(3)]
            cr = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
            s.need("EC-15", sum(x * x for x in cr) > 1e-20, "Degenerate triangle refused")
            s.need(
                "EC-16",
                all(sum(cr[k] * N[3 * x + k] for k in range(3)) > 0 for x in ids),
                "Vertex normals disagree with triangle winding",
            )
    for rid in ("EC-10", "EC-11", "EC-12", "EC-13", "EC-14", "EC-15", "EC-16"):
        s.finish(rid)


# ----------------------------------------------------------------------------- E0 humanoid
E0_RULES = [
    ("E0-01", "GLB of 28 bytes .. 4 MiB (byte identity is additionally pinned by the embodiment Definition)"),
    ("E0-02", "GLB header and chunks: magic, version 2, exact length, JSON chunk then BIN chunk to EOF"),
    ("E0-03", "UTF-8, strict duplicate-free JSON with finite numbers"),
    ("E0-04", "No uri, extensions, scripts, textures, images or morph targets anywhere; depth <= 16"),
    (
        "E0-05",
        "Exactly the top-level properties asset, scene, scenes, nodes, skins, meshes, materials, animations, "
        "buffers, bufferViews, accessors",
    ),
    ("E0-06", "asset has exactly version 2.0 and generator 'Finalverse blender-humanoid/1'; one embedded buffer"),
    ("E0-07", "27 nodes, one skin, one mesh; scene roots [0, 26]; node 26 holds only mesh 0, skin 0 and name"),
    ("E0-08", "Skin joints are nodes 0..25 in canonical order with 26 float MAT4 inverse binds"),
    (
        "E0-09",
        "Joint nodes carry only name/translation/children; canonical names, bounded translations, canonical "
        "hierarchy, identity rest rotation",
    ),
    ("E0-10", "Inverse bind matrices equal the inverse global rest transforms within 1e-4"),
    ("E0-11", "1..8 triangle primitives (explicit mode 4) without morph targets"),
    (
        "E0-12",
        "POSITION/NORMAL/WEIGHTS_0 float, JOINTS_0 uint16, uint32 indices; packed, aligned, explicit view offset",
    ),
    ("E0-13", "At most 20000 vertices per primitive, equal counts, complete triangles, indices in range"),
    ("E0-14", "Positions within 3 m, unit normals, joint indices < 26, weights in [0,1] summing to 1"),
    ("E0-15", "Each primitive has a material with baseColorFactor in [0,1]"),
    ("E0-16", "1..16 animations named from the 12 canonical clips, no duplicates"),
    ("E0-17", "Each clip: 1..26 rotation-only channels on distinct joints with explicit LINEAR interpolation"),
    ("E0-18", "Key times: 2..256 keys starting at 0, strictly increasing, ending <= 10 s; unit quaternion keys"),
]


def e0_humanoid(m) -> ProfileResult:
    r = ProfileResult(
        "finalverse.humanoid/v1",
        "Finalverse humanoid v1 strict E0 embodiment admission",
        "accepted",
        [E0_SRC, E0_DOC, INF_E0],
        [],
    )
    seq = _Seq(E0_RULES)
    fail = None
    try:
        _e0(m.data, seq)
    except _Fail as e:
        fail = e
    r.rules = seq.result(fail)
    r.status = "incompatible" if fail else "compatible"
    r.notes.append(
        "Infinity renders E0 bodies through this same loader (src/bin/embodiment-render.rs); renderer "
        "behaviour beyond the loader is not verified by S3-A."
    )
    if not fail:
        r.notes.append("A Definition must also pin geometry_sha256 to this asset's digest before runtime admission.")
    return r


def _e0(b: bytes, s: _Seq) -> None:
    s.need("E0-01", 28 <= len(b) <= 4 * 1024 * 1024, "GLB hash/size")
    s.finish("E0-01")
    u = lambda i: struct.unpack_from("<I", b, i)[0]  # noqa: E731
    s.need("E0-02", b[:4] == b"glTF" and u(4) == 2 and u(8) == len(b) and b[16:20] == b"JSON", "GLB header")
    end = 20 + u(12)
    s.need(
        "E0-02", end + 8 <= len(b) and b[end + 4 : end + 8] == b"BIN\x00" and u(end) == len(b) - end - 8, "GLB chunks"
    )
    s.finish("E0-02")
    try:
        d = _strict_json(None, b[20:end].decode("utf-8").encode("utf-8"))
    except UnicodeDecodeError:
        d = None
    s.need("E0-03", d is not None, "strict JSON")
    s.finish("E0-03")
    s.need(
        "E0-04",
        _forbidden(d, ("uri", "extensions", "scripts", "textures", "images", "targets"), 100000),
        "external/unsupported content",
    )
    s.finish("E0-04")
    allowed = (
        "asset",
        "scene",
        "scenes",
        "nodes",
        "skins",
        "meshes",
        "materials",
        "animations",
        "buffers",
        "bufferViews",
        "accessors",
    )
    s.need(
        "E0-05",
        isinstance(d, dict) and len(d) == len(allowed) and all(k in allowed for k in d),
        "unknown GLB profile fields",
    )
    s.finish("E0-05")
    bin_ = b[end + 8 :]
    s.need("E0-06", isinstance(d["asset"], dict) and len(d["asset"]) == 2, "asset metadata profile")
    bufs = d["buffers"]
    s.need(
        "E0-06",
        _strict_eq(d["asset"].get("version"), "2.0")
        and _strict_eq(d["asset"].get("generator"), "Finalverse blender-humanoid/1")
        and isinstance(bufs, list)
        and len(bufs) == 1
        and isinstance(bufs[0], dict)
        and "uri" not in bufs[0]
        and _strict_eq(bufs[0].get("byteLength"), len(b) - end - 8),
        "GLB profile/buffer",
    )
    s.finish("E0-06")
    accs = d["accessors"] if isinstance(d["accessors"], list) else []
    views = d["bufferViews"] if isinstance(d["bufferViews"], list) else []

    def data(rule, ai, ct, kind, width):
        a = accs[ai] if is_int(ai) and 0 <= ai < len(accs) else None
        s.need(rule, isinstance(a, dict), "accessor index")
        s.need(
            rule,
            _strict_eq(a.get("componentType"), ct)
            and _strict_eq(a.get("type"), kind)
            and "sparse" not in a
            and "normalized" not in a,
            "accessor encoding",
        )
        count = _u64(a.get("count"))
        s.need(rule, count is not None and 0 < count <= 100_000, "accessor budget")
        vi = _u64(a.get("bufferView"))
        v = views[vi] if vi is not None and vi < len(views) and isinstance(views[vi], dict) else None
        s.need(rule, v is not None, "buffer view")
        s.need(
            rule, _strict_eq(v.get("buffer"), 0) and "byteStride" not in v, "interleaved/external buffer unsupported"
        )
        vo = _u64(v.get("byteOffset"))
        s.need(rule, vo is not None, "integer index required (bufferView.byteOffset)")
        rel = a.get("byteOffset", 0) if _u64(a.get("byteOffset", 0)) is not None else 0
        start = vo + rel
        ln = _u64(v.get("byteLength"))
        s.need(rule, ln is not None, "integer index required (bufferView.byteLength)")
        n = count * width
        s.need(rule, rel + n <= ln and start % 4 == 0, "accessor range/alignment")
        s.need(rule, start + n <= len(bin_), "buffer overrun")
        return bin_[start : start + n], count

    def floats(rule, ai, kind, n):
        raw, count = data(rule, ai, 5126, kind, n * 4)
        vals = list(struct.unpack(f"<{count * n}f", raw))
        s.need(rule, all(math.isfinite(x) for x in vals), "nonfinite accessor")
        return vals

    nodes, skins, meshes = d["nodes"], d["skins"], d["meshes"]
    s.need(
        "E0-07",
        isinstance(nodes, list)
        and len(nodes) == 27
        and isinstance(skins, list)
        and len(skins) == 1
        and isinstance(meshes, list)
        and len(meshes) == 1
        and isinstance(d["scenes"], list)
        and d["scenes"]
        and isinstance(d["scenes"][0], dict)
        and _strict_eq(d["scenes"][0].get("nodes"), [0, 26])
        and isinstance(nodes[26], dict)
        and _strict_eq(nodes[26].get("mesh"), 0)
        and _strict_eq(nodes[26].get("skin"), 0),
        "rig scene topology",
    )
    s.need("E0-07", all(k in ("mesh", "skin", "name") for k in nodes[26]), "mesh node transform unsupported")
    s.finish("E0-07")
    sk = skins[0] if isinstance(skins[0], dict) else {}
    s.need("E0-08", _strict_eq(sk.get("joints"), list(range(26))), "joint order")
    inv = floats("E0-08", sk.get("inverseBindMatrices"), "MAT4", 16)
    s.need("E0-08", len(inv) == 26 * 16, "inverse bind count")
    s.finish("E0-08")
    globals_: list[list[float]] = []
    for i in range(26):
        n = nodes[i]
        s.need(
            "E0-09", isinstance(n, dict) and all(k in ("name", "translation", "children") for k in n), "joint fields"
        )
        t = n.get("translation")
        s.need("E0-09", isinstance(t, list) and len(t) == 3 and all(is_num(x) for x in t), "joint translation")
        s.need(
            "E0-09",
            _strict_eq(n.get("name"), E0_JOINTS[i]) and all(math.isfinite(x) and abs(x) < 3.0 for x in t),
            "canonical joint transform/name",
        )
        ch = n.get("children", [])
        s.need("E0-09", isinstance(ch, list) and all(is_int(c) and c >= 0 for c in ch), "joint children")
        s.need("E0-09", list(ch) == [j for j in range(26) if E0_PARENTS[j] == i], "joint parent hierarchy")
        parent = E0_PARENTS[i]
        g = mu.mul(
            globals_[parent] if parent is not None else mu.IDENTITY,
            mu.from_trs(t, (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0)),
        )
        ib = inv[i * 16 : (i + 1) * 16]
        s.need("E0-10", mu.max_abs_diff(mu.mul(g, ib), mu.IDENTITY) < 1e-4, "inverse bind mismatch")
        globals_.append(g)
    s.finish("E0-09")
    s.finish("E0-10")
    ps = meshes[0].get("primitives") if isinstance(meshes[0], dict) else None
    s.need("E0-11", isinstance(ps, list) and 1 <= len(ps) <= 8, "primitive budget")
    mats = d["materials"] if isinstance(d["materials"], list) else []
    for p in ps:
        s.need("E0-11", isinstance(p, dict) and _strict_eq(p.get("mode"), 4) and "targets" not in p, "triangles only")
        a = p.get("attributes") if isinstance(p.get("attributes"), dict) else {}
        pos = floats("E0-12", a.get("POSITION"), "VEC3", 3)
        nrm = floats("E0-12", a.get("NORMAL"), "VEC3", 3)
        wts = floats("E0-12", a.get("WEIGHTS_0"), "VEC4", 4)
        jr, jc = data("E0-12", a.get("JOINTS_0"), 5123, "VEC4", 8)
        jts = list(struct.unpack(f"<{jc * 4}H", jr))
        ir, ic = data("E0-12", p.get("indices"), 5125, "SCALAR", 4)
        idx = struct.unpack(f"<{ic}I", ir)
        n = len(pos) // 3
        s.need(
            "E0-13",
            n <= 20000
            and len(nrm) // 3 == n
            and len(wts) // 4 == n
            and jc == n
            and len(idx) % 3 == 0
            and all(i < n for i in idx),
            "mesh counts/indices",
        )
        ok = (
            all(abs(x) < 3.0 for x in pos)
            and all(
                abs(math.sqrt(nrm[k] ** 2 + nrm[k + 1] ** 2 + nrm[k + 2] ** 2) - 1.0) < 0.01
                for k in range(0, len(nrm), 3)
            )
            and all(j < 26 for j in jts)
            and all(
                all(0.0 <= x <= 1.0 for x in wts[k : k + 4]) and abs(sum(wts[k : k + 4]) - 1.0) < 1e-4
                for k in range(0, len(wts), 4)
            )
        )
        s.need("E0-14", ok, "mesh bounds/normals/skin weights")
        mi = _u64(p.get("material"))
        s.need("E0-15", mi is not None, "integer index required (material)")
        mat = mats[mi] if mi < len(mats) and isinstance(mats[mi], dict) else {}
        pbr = mat.get("pbrMetallicRoughness") if isinstance(mat.get("pbrMetallicRoughness"), dict) else {}
        col = pbr.get("baseColorFactor")
        s.need("E0-15", isinstance(col, list) and len(col) == 4 and all(is_num(x) for x in col), "material color")
        s.need("E0-15", all(math.isfinite(x) and 0.0 <= x <= 1.0 for x in col), "material range")
    for rid in ("E0-11", "E0-12", "E0-13", "E0-14", "E0-15"):
        s.finish(rid)
    anims = d["animations"]
    s.need("E0-16", isinstance(anims, list) and 1 <= len(anims) <= 16, "animation budget")
    names = set()
    for an in anims:
        s.need("E0-16", isinstance(an, dict) and isinstance(an.get("name"), str), "clip name")
        s.need("E0-16", an["name"] in E0_CLIPS, "unknown clip")
        chans = an.get("channels")
        s.need("E0-17", isinstance(chans, list) and 1 <= len(chans) <= 26, "channel count")
        seen = set()
        samplers = an.get("samplers") if isinstance(an.get("samplers"), list) else []
        for c in chans:
            t = c.get("target") if isinstance(c, dict) and isinstance(c.get("target"), dict) else {}
            s.need("E0-17", _strict_eq(t.get("path"), "rotation"), "rotation channels only")
            j = _u64(t.get("node"))
            s.need("E0-17", j is not None, "integer index required (node)")
            s.need("E0-17", j < 26 and j not in seen, "track joint")
            seen.add(j)
            si = _u64(c.get("sampler"))
            s.need("E0-17", si is not None and si < len(samplers) and isinstance(samplers[si], dict), "sampler")
            smp = samplers[si]
            s.need("E0-17", _strict_eq(smp.get("interpolation"), "LINEAR"), "interpolation")
            times = floats("E0-18", smp.get("input"), "SCALAR", 1)
            s.need(
                "E0-18",
                2 <= len(times) <= 256
                and times[0] == 0.0
                and times[-1] <= 10.0
                and all(y > x for x, y in zip(times, times[1:])),
                "key times",
            )
            q = floats("E0-18", smp.get("output"), "VEC4", 4)
            s.need("E0-18", len(q) == len(times) * 4, "key count")
            s.need(
                "E0-18",
                all(abs(math.sqrt(sum(x * x for x in q[k : k + 4])) - 1.0) < 1e-3 for k in range(0, len(q), 4)),
                "unit quaternion",
            )
        s.need("E0-16", an["name"] not in names, "duplicate clip")
        names.add(an["name"])
    for rid in ("E0-16", "E0-17", "E0-18"):
        s.finish(rid)


# ----------------------------------------------------------------------------- Infinity entry
INF_RULES = [
    ("INF-01", "GLB <= 8 MiB with valid header (magic, version 2, exact length, JSON chunk)"),
    ("INF-02", "JSON chunk <= 65536 bytes and 4-byte aligned"),
    ("INF-03", "JSON parses with finite numbers"),
    ("INF-04", "BIN chunk immediately follows JSON and ends at EOF"),
    ("INF-05", "Exactly one embedded buffer (no uri) not longer than the BIN chunk"),
    ("INF-06", "No required extensions"),
    ("INF-07", "If nodes are present: exactly one node, mesh 0, no transform or children"),
    ("INF-08", "Exactly one mesh with 1..256 primitives, no primitive extensions"),
    ("INF-09", "Each primitive passes the FinalStorm strict primitive decoder (finalstorm_spatialdb::glb::decode)"),
    ("INF-10", "Referenced materials exist; baseColorFactor and emissiveFactor (if present) are finite and in [0,1]"),
]
INF_CONSUMED = {"baseColorFactor", "emissiveFactor"}


def infinity_entry(m) -> ProfileResult:
    r = ProfileResult(
        "infinity.entry-glb/observed",
        "Infinity network entry GLB reader (observed from source)",
        "observed",
        [INF_SRC],
        [],
    )
    seq = _Seq(INF_RULES)
    fail = None
    try:
        _inf(m.data, seq)
    except _Fail as e:
        fail = e
    r.rules = seq.result(fail)
    if fail:
        r.status = "incompatible"
    else:
        r.status = "unverified"
        r.notes.append(
            "All entry-layer rules pass. The inner FinalStorm decoder (vendor/finalstorm, separate "
            "repository) was not available to S3-A, so final acceptance is unverified."
        )
    support: dict[str, str] = {}
    for mat in (m.doc.get("materials") or []) if isinstance(m.doc, dict) else []:
        if not isinstance(mat, dict):
            continue
        keys = (
            set(mat) | {f"pbrMetallicRoughness.{k}" for k in (mat.get("pbrMetallicRoughness") or {})}
            if isinstance(mat.get("pbrMetallicRoughness") or {}, dict)
            else set(mat)
        )
        for k in sorted(keys):
            if k in ("name", "pbrMetallicRoughness", "extras"):
                continue
            leaf = k.split(".")[-1]
            support[k] = "consumed_by_entry_reader" if leaf in INF_CONSUMED else "not_consumed_by_entry_reader"
    r.material_feature_support = dict(sorted(support.items()))
    return r


def _inf(b: bytes, s: _Seq) -> None:
    def word(o):
        s.need(rule_now[0], o + 4 <= len(b), "Truncated GLB")
        return struct.unpack_from("<I", b, o)[0]

    rule_now = ["INF-01"]
    s.need(
        "INF-01",
        len(b) <= 8 * 1024 * 1024
        and word(0) == 0x46546C67
        and word(4) == 2
        and word(8) == len(b)
        and word(16) == 0x4E4F534A,
        "Invalid GLB header",
    )
    s.finish("INF-01")
    rule_now[0] = "INF-02"
    n = word(12)
    s.need("INF-02", n <= 65536 and n % 4 == 0, "GLB JSON budget refused")
    s.need("INF-02", 20 + n <= len(b), "Truncated GLB JSON")
    s.finish("INF-02")
    try:
        doc = json.loads(b[20 : 20 + n].decode("utf-8"))
        ok = _finite_json(doc)
    except (ValueError, RecursionError):
        doc, ok = None, False
    s.need("INF-03", ok, "Invalid GLB JSON")
    s.finish("INF-03")
    rule_now[0] = "INF-04"
    je = 20 + n
    bl = word(je)
    s.need("INF-04", word(je + 4) == 0x004E4942 and je + 8 + bl == len(b), "Invalid GLB binary chunk")
    s.finish("INF-04")
    d = doc if isinstance(doc, dict) else {}
    bufs = d.get("buffers")
    s.need("INF-05", isinstance(bufs, list), "Missing GLB buffer")
    s.need(
        "INF-05",
        len(bufs) == 1
        and isinstance(bufs[0], dict)
        and "uri" not in bufs[0]
        and _u64(bufs[0].get("byteLength")) is not None
        and bufs[0]["byteLength"] <= bl,
        "External or invalid GLB buffer",
    )
    s.finish("INF-05")
    er = d.get("extensionsRequired")
    s.need("INF-06", not (isinstance(er, list) and er), "Required GLB extension unsupported")
    s.finish("INF-06")
    nodes = d.get("nodes")
    if isinstance(nodes, list):
        s.need(
            "INF-07",
            len(nodes) == 1
            and isinstance(nodes[0], dict)
            and _strict_eq(nodes[0].get("mesh"), 0)
            and not any(k in nodes[0] for k in ("matrix", "translation", "rotation", "scale", "children")),
            "Nontrivial GLB node transforms unsupported",
        )
    s.finish("INF-07")
    meshes = d.get("meshes")
    s.need("INF-08", isinstance(meshes, list), "Missing GLB meshes")
    s.need("INF-08", len(meshes) == 1, "One bounded GLB mesh required")
    prims = meshes[0].get("primitives") if isinstance(meshes[0], dict) else None
    s.need("INF-08", isinstance(prims, list), "Missing GLB primitives")
    s.need("INF-08", 1 <= len(prims) <= 256, "GLB primitive budget exceeded")
    mats = d.get("materials") if isinstance(d.get("materials"), list) else []
    for p in prims:
        s.need("INF-08", not (isinstance(p, dict) and "extensions" in p), "Primitive extensions unsupported")
        s.unverified["INF-09"] = "finalstorm_spatialdb::glb::decode source is not in the inspected repositories"
        mi = p.get("material") if isinstance(p, dict) else None
        if is_int(mi) and mi >= 0:
            s.need("INF-10", mi < len(mats), "Invalid material index")
            mt = mats[mi] if isinstance(mats[mi], dict) else {}
            pbr = mt.get("pbrMetallicRoughness") if isinstance(mt.get("pbrMetallicRoughness"), dict) else {}
            c = pbr.get("baseColorFactor")
            if isinstance(c, list):
                s.need(
                    "INF-10",
                    len(c) == 4 and all(is_num(v) and math.isfinite(v) and 0 <= v <= 1 for v in c),
                    "Invalid material color",
                )
            e = mt.get("emissiveFactor")
            if isinstance(e, list):
                s.need(
                    "INF-10",
                    len(e) == 3 and all(is_num(v) and math.isfinite(v) and 0 <= v <= 1 for v in e),
                    "Invalid emissive factor",
                )
    s.finish("INF-08")
    s.finish("INF-10")


def _finite_json(v: Any) -> bool:
    stack = [v]
    while stack:
        x = stack.pop()
        if isinstance(x, float) and not math.isfinite(x):
            return False
        if isinstance(x, dict):
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return True


RUNTIME_PROFILES: dict[str, Callable] = {
    "finalverse.ec-static-glb/v1": ec_static,
    "finalverse.humanoid/v1": e0_humanoid,
    "infinity.entry-glb/observed": infinity_entry,
}


def evaluate_runtime(m, selected: list[str] | None = None) -> list[ProfileResult]:
    if m.aborted or not m.data:
        return [
            ProfileResult(
                pid,
                fn.__doc__ or pid,
                "n/a",
                [],
                [],
                status="not_evaluated",
                notes=["Inspection did not complete; profile not evaluated."],
            )
            for pid, fn in RUNTIME_PROFILES.items()
            if not selected or pid in selected
        ]
    out = []
    for pid, fn in RUNTIME_PROFILES.items():
        if selected and pid not in selected:
            continue
        try:
            out.append(fn(m))
        except (struct.error, IndexError, KeyError, TypeError, AttributeError) as e:
            # Malformed input reached a path the original would have refused earlier through a
            # typed error; record it as a failure rather than crash.
            res = ProfileResult(
                pid,
                pid,
                "accepted",
                [],
                [],
                status="incompatible",
                notes=[f"Profile evaluation stopped on malformed input ({type(e).__name__})."],
            )
            out.append(res)
    return out
