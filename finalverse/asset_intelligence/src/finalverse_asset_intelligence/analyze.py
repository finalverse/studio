"""Deterministic glTF 2.0 / GLB inspection and validation.

``analyze`` never executes content, never fetches remote resources and never
modifies the input.  It returns a :class:`Model` holding the extracted inspection
data, metrics and findings, which profiles, quality and reporting consume.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import imageinfo
from . import mathutil as mu
from .accessors import Accessors, Decoded, arr_of, hkey, is_int, is_num, list_len
from .container import Container, Resolver, parse_container
from .context import Abort, Ctx
from .limits import Limits, RuntimeBudget

ATTR_RULES = {
    "POSITION": ({"VEC3"}, {5126}, False),
    "NORMAL": ({"VEC3"}, {5126}, False),
    "TANGENT": ({"VEC4"}, {5126}, False),
    "TEXCOORD": ({"VEC2"}, {5126, 5121, 5123}, True),
    "COLOR": ({"VEC3", "VEC4"}, {5126, 5121, 5123}, True),
    "JOINTS": ({"VEC4"}, {5121, 5123}, False),
    "WEIGHTS": ({"VEC4"}, {5126, 5121, 5123}, True),
}
RESTART = {5121: 0xFF, 5123: 0xFFFF, 5125: 0xFFFFFFFF}
PATHS = {"translation": ("VEC3", 3), "rotation": ("VEC4", 4), "scale": ("VEC3", 3), "weights": ("SCALAR", 1)}
TEXTURE_SLOTS = ("baseColorTexture", "metallicRoughnessTexture", "normalTexture", "occlusionTexture", "emissiveTexture")
IMAGE_EXTENSIONS = {
    "KHR_texture_basisu": "image/ktx2",
    "EXT_texture_webp": "image/webp",
    "EXT_texture_avif": "image/avif",
}


@dataclass
class Prim:
    pointer: str
    mesh: int
    index: int
    mode: int
    attributes: dict[str, int]
    material: int | None
    vertices: int = 0
    triangles: int = 0
    degenerate: int = 0
    positions: Decoded | None = None
    normals: Decoded | None = None
    joints: Decoded | None = None
    weights: Decoded | None = None
    indices: list[int] | None = None
    targets: int = 0
    bbox: tuple[list[float], list[float]] | None = None


@dataclass
class Model:
    name: str
    byte_length: int
    sha256: str
    data: bytes
    limits: Limits
    budget: RuntimeBudget
    ctx: Ctx
    container: Container | None = None
    doc: dict = field(default_factory=dict)
    acc: Accessors | None = None
    resources: list = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    parents: list[int | None] = field(default_factory=list)
    local: list[list[float] | None] = field(default_factory=list)
    world: dict[int, list[float]] = field(default_factory=dict)
    scene_index: int | None = None
    scene_nodes: list[int] = field(default_factory=list)
    prims: list[Prim] = field(default_factory=list)
    mesh_prims: dict[int, list[Prim]] = field(default_factory=dict)
    materials: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    textures: list[dict] = field(default_factory=list)
    skins: list[dict] = field(default_factory=list)
    animations: list[dict] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)
    bounds: dict[str, Any] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    aborted: bool = False

    @property
    def findings(self):
        return self.ctx.findings

    @property
    def complete(self) -> bool:
        return not self.aborted and not self.ctx.incomplete_reasons


def analyze(
    data: bytes,
    *,
    name: str = "asset",
    base_dir: Path | None = None,
    limits: Limits | None = None,
    budget: RuntimeBudget | None = None,
) -> Model:
    limits = limits or Limits()
    budget = budget or RuntimeBudget()
    ctx = Ctx(limits, budget)
    m = Model(
        name=name,
        byte_length=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        data=data,
        limits=limits,
        budget=budget,
        ctx=ctx,
    )
    try:
        if len(data) > limits.max_file_bytes:
            raise ctx.abort(
                "FVA-RES-001",
                "/",
                "Asset exceeds the maximum inspected file size",
                {"byte_length": len(data), "max_file_bytes": limits.max_file_bytes},
            )
        m.container = parse_container(data, ctx)
        if not isinstance(m.container.doc, dict):
            raise ctx.abort("FVA-CON-009", "/", "The glTF document root must be a JSON object")
        m.doc = m.container.doc
        _Inspector(m, base_dir).run()
    except Abort:
        m.aborted = True
    return m


def load_path(path: str | Path, limits: Limits | None = None, budget: RuntimeBudget | None = None) -> Model:
    p = Path(path)
    limits = limits or Limits()
    size = p.stat().st_size
    if size > limits.max_file_bytes:
        # do not read an oversized file into memory; produce the same refusal analyze() would
        ctx = Ctx(limits, budget or RuntimeBudget())
        ctx.abort(
            "FVA-RES-001",
            "/",
            "Asset exceeds the maximum inspected file size",
            {"byte_length": size, "max_file_bytes": limits.max_file_bytes},
        )
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return Model(
            name=p.name,
            byte_length=size,
            sha256=h.hexdigest(),
            data=b"",
            limits=limits,
            budget=budget or RuntimeBudget(),
            ctx=ctx,
            aborted=True,
        )
    data = p.read_bytes()
    return analyze(data, name=p.name, base_dir=p.parent, limits=limits, budget=budget)


class _Inspector:
    def __init__(self, m: Model, base_dir: Path | None) -> None:
        self.m = m
        self.ctx = m.ctx
        self.doc = m.doc
        self.resolver = Resolver(m.ctx, base_dir)
        self.texcoords_needed: dict[int, set[int]] = {}
        self.normal_mapped: set[int] = set()
        self.used_materials: set[int] = set()
        self.used_textures: set[int] = set()
        self.used_images: set[int] = set()

    def arr(self, key: str) -> list[dict]:
        return [x if isinstance(x, dict) else {} for x in arr_of(self.doc, key, self.ctx)]

    def run(self) -> None:
        self.asset()
        self.extensions()
        buffers = self.buffers()
        self.m.acc = Accessors(self.doc, self.ctx, buffers)
        self.images()
        self.textures()
        self.materials()
        self.meshes()
        self.nodes()
        self.scenes()
        self.skins()
        self.animations()
        self.unused()
        self.bounds()
        self.metrics()
        self.m.resources = self.resolver.resources

    # -- asset / extensions -------------------------------------------------------
    def asset(self) -> None:
        a = self.doc.get("asset")
        if not isinstance(a, dict) or not isinstance(a.get("version"), str):
            raise self.ctx.abort("FVA-CON-009", "/asset", "asset.version is required")
        for key in ("version", "minVersion"):
            v = a.get(key)
            if v is None:
                continue
            parts = v.split(".") if isinstance(v, str) else []
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                raise self.ctx.abort("FVA-CON-010", f"/asset/{key}", "Malformed glTF version", {key: str(v)[:16]})
            if key == "version" and parts[0] != "2":
                raise self.ctx.abort("FVA-CON-010", "/asset/version", "Only glTF 2.x is supported", {key: v})
            if key == "minVersion" and (int(parts[0]), int(parts[1])) > (2, 0):
                raise self.ctx.abort(
                    "FVA-CON-010", "/asset/minVersion", "Asset requires a newer glTF version", {key: v}
                )

    def extensions(self) -> None:
        ctx = self.ctx
        used = self.doc.get("extensionsUsed", [])
        req = self.doc.get("extensionsRequired", [])
        for key, v in (("extensionsUsed", used), ("extensionsRequired", req)):
            if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
                ctx.add("FVA-CON-009", f"/{key}", f"{key} must be an array of strings")
        used = [x for x in used if isinstance(x, str)] if isinstance(used, list) else []
        req = [x for x in req if isinstance(x, str)] if isinstance(req, list) else []
        present: dict[str, str] = {}
        stack: list[tuple[Any, str, int]] = [(self.doc, "", 0)]
        while stack:
            v, p, depth = stack.pop()
            if isinstance(v, dict):
                ext = v.get("extensions")
                if isinstance(ext, dict):
                    for k in ext:
                        present.setdefault(k, f"{p}/extensions/{k}")
                for k, x in v.items():
                    if isinstance(x, (dict, list)):
                        stack.append((x, f"{p}/{k}", depth + 1))
            elif isinstance(v, list):
                for i, x in enumerate(v):
                    if isinstance(x, (dict, list)):
                        stack.append((x, f"{p}/{i}", depth + 1))
        for name in sorted(set(req) - set(used)):
            ctx.add(
                "FVA-EXT-003",
                "/extensionsRequired",
                "Required extension is not listed in extensionsUsed",
                {"extension": name},
            )
        for name, p in sorted(present.items()):
            if name not in used:
                ctx.add("FVA-EXT-002", p, "Extension is used but not declared in extensionsUsed", {"extension": name})
        for i, name in enumerate(req):
            ctx.add(
                "FVA-EXT-001",
                f"/extensionsRequired/{i}",
                "Required extension is not supported by any accepted Finalverse runtime profile",
                {"extension": name},
            )
        for i, name in enumerate(used):
            if name in req:
                continue
            ctx.add(
                "FVA-EXT-004",
                f"/extensionsUsed/{i}",
                "Optional extension; Finalverse runtime handling is unverified",
                {"extension": name},
            )
        self.m.extensions = {"used": sorted(set(used)), "required": sorted(set(req)), "present": sorted(present)}

    # -- buffers ------------------------------------------------------------------
    def buffers(self) -> list[bytes | None]:
        out: list[bytes | None] = []
        glb = self.m.container.kind == "glb"
        for i, b in enumerate(self.arr("buffers")):
            p = f"/buffers/{i}"
            bl = b.get("byteLength")
            if not is_int(bl) or bl < 1:
                self.ctx.add("FVA-CON-009", p + "/byteLength", "buffer.byteLength must be an integer >= 1")
                out.append(None)
                continue
            data: bytes | None
            if "uri" in b:
                res = self.resolver.resolve(b["uri"], p, "buffer")
                data = res.data
            elif i == 0 and glb and self.m.container.bin_chunk is not None:
                data = self.m.container.bin_chunk
                self.resolver.resources.append(_embedded(p, data))
            else:
                self.ctx.add("FVA-BUF-001", p, "Buffer has no uri and no GLB BIN chunk")
                data = None
            if data is not None and len(data) < bl:
                self.ctx.add(
                    "FVA-BUF-002",
                    p,
                    "Buffer data is shorter than byteLength",
                    {"byteLength": bl, "available": len(data)},
                )
            out.append(data)
        return out

    # -- images / textures / materials -----------------------------------------------
    def images(self) -> None:
        acc = self.m.acc
        for i, im in enumerate(self.arr("images")):
            p = f"/images/{i}"
            info: dict[str, Any] = {"index": i, "name": im.get("name") if isinstance(im.get("name"), str) else None}
            raw = None
            mime = im.get("mimeType")
            if "uri" in im and "bufferView" in im:
                self.ctx.add("FVA-CON-009", p, "image must not define both uri and bufferView")
            if "bufferView" in im:
                vi = im["bufferView"]
                if not mime:
                    self.ctx.add("FVA-CON-009", p + "/mimeType", "mimeType is required with bufferView")
                if is_int(vi) and 0 <= vi < len(acc.views) and acc.view_ok[vi]:
                    raw = acc._raw_view(vi)
                    info["source"] = "buffer_view"
                else:
                    self.ctx.add("FVA-CON-011", p + "/bufferView", "image references a missing bufferView")
            elif "uri" in im:
                res = self.resolver.resolve(im["uri"], p, "image")
                raw = res.data
                info["source"] = res.uri_class
                info["status"] = res.status
                mime = mime or res.mime
            else:
                self.ctx.add("FVA-CON-009", p, "image requires uri or bufferView")
            if raw is not None:
                info["byte_length"] = len(raw)
                info["sha256"] = hashlib.sha256(raw).hexdigest()
                probe = imageinfo.probe(raw)
                if probe is None:
                    self.ctx.add("FVA-MAT-005", p, "Image header is not a recognized PNG, JPEG, WebP or KTX2 image")
                else:
                    info.update(media_type=probe["format"], width=probe["width"], height=probe["height"])
                    if mime and mime != probe["format"]:
                        self.ctx.add(
                            "FVA-MAT-005",
                            p + "/mimeType",
                            "mimeType does not match image content",
                            {"declared": str(mime)[:64], "detected": probe["format"]},
                        )
                    if probe["format"] not in ("image/png", "image/jpeg"):
                        self.ctx.add(
                            "FVA-MAT-006", p, "Image format requires a glTF extension", {"format": probe["format"]}
                        )
                    w, h = probe["width"], probe["height"]
                    if w < 1 or h < 1:
                        self.ctx.add("FVA-MAT-005", p, "Image has zero dimensions")
                    lim = self.m.budget.max_texture_dimension.value
                    if max(w, h) > lim:
                        self.ctx.add(
                            "FVA-MAT-007",
                            p,
                            "Texture exceeds the configured maximum dimension",
                            {"width": w, "height": h, "budget": lim},
                        )
                    if w & (w - 1) or h & (h - 1):
                        self.ctx.add(
                            "FVA-MAT-008", p, "Texture dimensions are not powers of two", {"width": w, "height": h}
                        )
            elif mime:
                info["media_type"] = mime
            self.m.images.append(info)

    def textures(self) -> None:
        n_img = len(self.m.images)
        samplers = self.arr("samplers")
        for i, t in enumerate(self.arr("textures")):
            p = f"/textures/{i}"
            src = t.get("source")
            ext = t.get("extensions") if isinstance(t.get("extensions"), dict) else {}
            ext_src = [(k, v.get("source")) for k, v in ext.items() if k in IMAGE_EXTENSIONS and isinstance(v, dict)]
            info = {"index": i, "source": src, "sampler": t.get("sampler"), "extension_sources": dict(ext_src)}
            for k, s in [("source", src)] + [(f"extensions/{k}/source", s) for k, s in ext_src]:
                if s is not None and not (is_int(s) and 0 <= s < n_img):
                    self.ctx.add("FVA-MAT-004", f"{p}/{k}", "texture references a missing image", {"image": s})
                elif s is not None:
                    self.used_images.add(s)
            if src is None and not ext_src:
                self.ctx.add("FVA-MAT-004", p, "texture has no image source")
            smp = t.get("sampler")
            if smp is not None and not (is_int(smp) and 0 <= smp < len(samplers)):
                self.ctx.add("FVA-MAT-004", p + "/sampler", "texture references a missing sampler", {"sampler": smp})
            self.m.textures.append(info)
        for i, s in enumerate(samplers):
            for k, allowed in (
                ("magFilter", {9728, 9729}),
                ("minFilter", {9728, 9729, 9984, 9985, 9986, 9987}),
                ("wrapS", {33071, 33648, 10497}),
                ("wrapT", {33071, 33648, 10497}),
            ):
                if k in s and hkey(s[k]) not in allowed:
                    self.ctx.add("FVA-CON-009", f"/samplers/{i}/{k}", f"invalid sampler {k}", {k: s[k]})

    def materials(self) -> None:
        n_tex = len(self.m.textures)
        for i, mat in enumerate(self.arr("materials")):
            p = f"/materials/{i}"
            pbr = mat.get("pbrMetallicRoughness") if isinstance(mat.get("pbrMetallicRoughness"), dict) else {}
            ext = mat.get("extensions") if isinstance(mat.get("extensions"), dict) else {}
            strength = 1.0
            es = ext.get("KHR_materials_emissive_strength")
            if isinstance(es, dict) and is_num(es.get("emissiveStrength")):
                strength = float(es["emissiveStrength"])
            info: dict[str, Any] = {
                "index": i,
                "name": mat.get("name") if isinstance(mat.get("name"), str) else None,
                "base_color_factor": self._factor(
                    pbr, "baseColorFactor", 4, [1.0, 1.0, 1.0, 1.0], f"{p}/pbrMetallicRoughness"
                ),
                "metallic_factor": self._scalar(pbr, "metallicFactor", 1.0, f"{p}/pbrMetallicRoughness"),
                "roughness_factor": self._scalar(pbr, "roughnessFactor", 1.0, f"{p}/pbrMetallicRoughness"),
                "emissive_factor": self._factor(mat, "emissiveFactor", 3, [0.0, 0.0, 0.0], p),
                "emissive_strength": strength,
                "alpha_mode": hkey(mat.get("alphaMode", "OPAQUE")),
                "double_sided": mat.get("doubleSided", False) is True,
                "extensions": sorted(ext),
                "textures": {},
                "explicit": sorted(k for k in ("baseColorFactor", "metallicFactor", "roughnessFactor") if k in pbr),
            }
            if info["alpha_mode"] not in ("OPAQUE", "MASK", "BLEND"):
                self.ctx.add(
                    "FVA-MAT-002", p + "/alphaMode", "Invalid alphaMode", {"alphaMode": str(info["alpha_mode"])[:16]}
                )
            if "alphaCutoff" in mat:
                c = mat["alphaCutoff"]
                if not is_num(c) or c < 0:
                    self.ctx.add("FVA-MAT-001", p + "/alphaCutoff", "alphaCutoff must be >= 0")
                if info["alpha_mode"] != "MASK":
                    self.ctx.add(
                        "FVA-MAT-003", p + "/alphaCutoff", "alphaCutoff has no effect unless alphaMode is MASK"
                    )
                info["alpha_cutoff"] = c
            if "doubleSided" in mat and not isinstance(mat["doubleSided"], bool):
                self.ctx.add("FVA-CON-009", p + "/doubleSided", "doubleSided must be boolean")
            for slot in TEXTURE_SLOTS:
                holder = pbr if slot in ("baseColorTexture", "metallicRoughnessTexture") else mat
                ti = holder.get(slot)
                if ti is None:
                    continue
                tp = f"{p}/pbrMetallicRoughness/{slot}" if holder is pbr else f"{p}/{slot}"
                if not isinstance(ti, dict) or not is_int(ti.get("index")) or not 0 <= ti["index"] < n_tex:
                    self.ctx.add(
                        "FVA-MAT-004",
                        tp,
                        "textureInfo references a missing texture",
                        {"index": ti.get("index") if isinstance(ti, dict) else None},
                    )
                    continue
                tc = ti.get("texCoord", 0)
                if not is_int(tc) or tc < 0:
                    self.ctx.add("FVA-CON-009", tp + "/texCoord", "texCoord must be a non-negative integer")
                    tc = 0
                self.texcoords_needed.setdefault(i, set()).add(tc)
                self.used_textures.add(ti["index"])
                if slot == "normalTexture":
                    self.normal_mapped.add(i)
                if (
                    slot == "occlusionTexture"
                    and "strength" in ti
                    and not (is_num(ti["strength"]) and 0 <= ti["strength"] <= 1)
                ):
                    self.ctx.add("FVA-MAT-001", tp + "/strength", "occlusion strength must be in [0, 1]")
                tex = self.m.textures[ti["index"]]
                img = (
                    tex["source"] if is_int(tex.get("source")) else next(iter(tex["extension_sources"].values()), None)
                )
                info["textures"][slot] = {"texture": ti["index"], "image": img, "tex_coord": tc}
            self.m.materials.append(info)

    def _factor(self, obj: dict, key: str, n: int, default: list[float], p: str) -> list[float]:
        v = obj.get(key)
        if v is None:
            return default
        hi = 1.0
        if not (isinstance(v, list) and len(v) == n and all(is_num(x) for x in v)):
            self.ctx.add("FVA-CON-009", f"{p}/{key}", f"{key} must be {n} numbers")
            return default
        if not all(math.isfinite(x) and 0.0 <= x <= hi for x in v):
            self.ctx.add("FVA-MAT-001", f"{p}/{key}", f"{key} components must be in [0, 1]", {key: v})
        return [float(x) for x in v]

    def _scalar(self, obj: dict, key: str, default: float, p: str) -> float:
        v = obj.get(key)
        if v is None:
            return default
        if not is_num(v) or not math.isfinite(v) or not 0.0 <= v <= 1.0:
            self.ctx.add("FVA-MAT-001", f"{p}/{key}", f"{key} must be in [0, 1]", {key: v if is_num(v) else None})
            return default
        return float(v)

    # -- meshes -------------------------------------------------------------------
    def meshes(self) -> None:
        mats = len(self.m.materials)
        for mi, mesh in enumerate(self.arr("meshes")):
            prims = mesh.get("primitives")
            if not isinstance(prims, list) or not prims:
                self.ctx.add("FVA-GEO-015", f"/meshes/{mi}", "Mesh has no primitives")
                self.m.mesh_prims[mi] = []
                continue
            out = []
            target_counts = set()
            for pi, prim in enumerate(prims):
                self.ctx.tick(64)
                if not isinstance(prim, dict):
                    self.ctx.add("FVA-CON-009", f"/meshes/{mi}/primitives/{pi}", "primitive must be an object")
                    continue
                pr = self.primitive(mi, pi, prim, mats)
                target_counts.add(pr.targets)
                out.append(pr)
            if len(target_counts) > 1:
                self.ctx.add(
                    "FVA-GEO-016", f"/meshes/{mi}", "Primitives of one mesh must have the same number of morph targets"
                )
            w = mesh.get("weights")
            if w is not None and (not isinstance(w, list) or (target_counts and len(w) != max(target_counts))):
                self.ctx.add(
                    "FVA-GEO-016", f"/meshes/{mi}/weights", "mesh.weights length must equal the morph target count"
                )
            self.m.mesh_prims[mi] = out
            self.m.prims.extend(out)

    def primitive(self, mi: int, pi: int, prim: dict, mats: int) -> Prim:
        ctx, acc = self.ctx, self.m.acc
        p = f"/meshes/{mi}/primitives/{pi}"
        mode = prim.get("mode", 4)
        if not is_int(mode) or not 0 <= mode <= 6:
            ctx.add("FVA-GEO-009", p + "/mode", "Invalid primitive mode", {"mode": mode if is_num(mode) else None})
            mode = -1
        elif mode != 4:
            ctx.add(
                "FVA-GEO-010",
                p + "/mode",
                "Primitive mode is not indexed triangles",
                {
                    "mode": [
                        "POINTS",
                        "LINES",
                        "LINE_LOOP",
                        "LINE_STRIP",
                        "TRIANGLES",
                        "TRIANGLE_STRIP",
                        "TRIANGLE_FAN",
                    ][mode]
                },
            )
        attrs_raw = prim.get("attributes")
        if not isinstance(attrs_raw, dict):
            ctx.add("FVA-CON-009", p + "/attributes", "primitive.attributes must be an object")
            attrs_raw = {}
        material = prim.get("material")
        if material is not None and not (is_int(material) and 0 <= material < mats):
            ctx.add("FVA-CON-011", p + "/material", "primitive references a missing material", {"material": material})
            material = None
        elif material is None:
            ctx.add("FVA-MAT-009", p, "Primitive uses the glTF default material")
        else:
            self.used_materials.add(material)
        pr = Prim(p, mi, pi, mode, {}, material)
        counts: dict[str, int] = {}
        for sem, ai in sorted(attrs_raw.items()):
            ap = f"{p}/attributes/{sem}"
            if not is_int(ai) or not 0 <= ai < len(acc.accessors):
                ctx.add("FVA-CON-011", ap, "attribute references a missing accessor", {"accessor": ai})
                continue
            base = sem.split("_")[0] if not sem.startswith("_") else "_"
            rule = ATTR_RULES.get(base)
            if sem.startswith("_"):
                pass
            elif (
                rule is None
                or (base in ("TEXCOORD", "COLOR", "JOINTS", "WEIGHTS") and not sem[len(base) + 1 :].isdigit())
                or (base in ("POSITION", "NORMAL", "TANGENT") and sem != base)
            ):
                ctx.add(
                    "FVA-GEO-012",
                    ap,
                    "Unknown attribute semantic (application-specific names must start with '_')",
                    {"semantic": sem[:64]},
                )
            else:
                a = acc.accessors[ai]
                types, cts, may_norm = rule
                ok = hkey(a.get("type")) in types and hkey(a.get("componentType")) in cts
                if (
                    ok
                    and a.get("componentType") != 5126
                    and base != "JOINTS"
                    and may_norm
                    and a.get("normalized") is not True
                ):
                    ok = False
                if not ok:
                    ctx.add(
                        "FVA-GEO-012",
                        ap,
                        "Accessor encoding is not allowed for this semantic",
                        {"semantic": sem, "type": a.get("type"), "componentType": a.get("componentType")},
                    )
            pr.attributes[sem] = ai
            if is_int(acc.accessors[ai].get("count")):
                counts[sem] = acc.accessors[ai]["count"]
        if len(set(counts.values())) > 1:
            ctx.add("FVA-GEO-002", p + "/attributes", "Attributes have different counts", {"counts": counts})
        n = counts.get("POSITION", max(counts.values()) if counts else 0)
        pr.vertices = n if "POSITION" in counts else 0
        if "POSITION" not in pr.attributes:
            ctx.add("FVA-GEO-001", p + "/attributes", "Primitive has no POSITION attribute")
        else:
            pos = acc.get(pr.attributes["POSITION"])
            if pos is not None and pos.components == 3:
                acc.check_bounds(pr.attributes["POSITION"], pos, True, p)
                pr.positions = pos
                v = pos.values
                if all(math.isfinite(x) for x in v):
                    pr.bbox = ([min(v[0::3]), min(v[1::3]), min(v[2::3])], [max(v[0::3]), max(v[1::3]), max(v[2::3])])
        tri_mode = mode in (4, 5, 6)
        if tri_mode and "NORMAL" not in pr.attributes:
            ctx.add("FVA-GEO-007", p + "/attributes", "Primitive has no vertex normals")
        elif "NORMAL" in pr.attributes:
            nd = acc.get(pr.attributes["NORMAL"])
            if nd is not None and nd.components == 3:
                pr.normals = nd
                bad = 0
                vals = nd.values
                for k in range(0, len(vals), 3):
                    ln = math.sqrt(vals[k] ** 2 + vals[k + 1] ** 2 + vals[k + 2] ** 2)
                    if not abs(ln - 1.0) <= 5e-3:
                        bad += 1
                if bad:
                    ctx.add(
                        "FVA-GEO-008",
                        p + "/attributes/NORMAL",
                        "Vertex normals are not unit length",
                        {"non_unit": bad, "vertices": nd.count},
                    )
        if material is not None:
            for tc in sorted(self.texcoords_needed.get(material, ())):
                if f"TEXCOORD_{tc}" not in pr.attributes:
                    ctx.add(
                        "FVA-GEO-013",
                        p + "/attributes",
                        "Material texture needs a missing UV set",
                        {"tex_coord": tc, "material": material},
                    )
            if material in self.normal_mapped and "TANGENT" not in pr.attributes:
                ctx.add("FVA-GEO-014", p + "/attributes", "Normal-mapped primitive has no tangents")
        # indices
        if "indices" in prim:
            ii = prim["indices"]
            ip = p + "/indices"
            if not is_int(ii) or not 0 <= ii < len(acc.accessors):
                ctx.add("FVA-CON-011", ip, "indices reference a missing accessor", {"accessor": ii})
            else:
                a = acc.accessors[ii]
                if (
                    a.get("type") != "SCALAR"
                    or hkey(a.get("componentType")) not in RESTART
                    or a.get("normalized") is True
                ):
                    ctx.add(
                        "FVA-GEO-012",
                        ip,
                        "indices must be SCALAR unsigned byte/short/int",
                        {"type": a.get("type"), "componentType": a.get("componentType")},
                    )
                else:
                    idx = acc.get(ii)
                    if idx is not None:
                        pr.indices = idx.values
                        if n:
                            oob = sum(1 for x in idx.values if x >= n)
                            if oob:
                                ctx.add(
                                    "FVA-GEO-003",
                                    ip,
                                    "Indices reference vertices beyond the vertex count",
                                    {"out_of_range": oob, "vertex_count": n, "max_index": max(idx.values)},
                                )
                        restart = RESTART[a["componentType"]]
                        if any(x == restart for x in idx.values):
                            ctx.add("FVA-GEO-004", ip, "Index data contains the primitive restart value")
        elif mode >= 0 and pr.positions is not None and ctx.charge(pr.positions.count, p):
            # non-indexed: draw order from *decoded* positions only, never from a declared count
            pr.indices = list(range(pr.positions.count))
        if pr.indices is not None and mode >= 0:
            k = len(pr.indices)
            if (
                (mode == 4 and k % 3)
                or (mode in (5, 6) and k < 3)
                or (mode == 1 and k % 2)
                or (mode in (2, 3) and k < 2)
            ):
                ctx.add(
                    "FVA-GEO-005",
                    p + ("/indices" if "indices" in prim else ""),
                    "Index/vertex count does not form complete primitives",
                    {"count": k, "mode": mode},
                )
            pr.triangles = self.degenerate(pr, mode, n)
        # morph targets
        targets = prim.get("targets")
        if targets is not None:
            if not isinstance(targets, list):
                ctx.add("FVA-CON-009", p + "/targets", "targets must be an array")
            else:
                pr.targets = len(targets)
                for ti, t in enumerate(targets):
                    if not isinstance(t, dict) or not t:
                        ctx.add("FVA-GEO-016", f"{p}/targets/{ti}", "Morph target must define attributes")
                        continue
                    for sem, ai in t.items():
                        if not is_int(ai) or not 0 <= ai < len(acc.accessors):
                            ctx.add(
                                "FVA-CON-011", f"{p}/targets/{ti}/{sem}", "morph target references a missing accessor"
                            )
                        elif acc.accessors[ai].get("count") != n:
                            ctx.add(
                                "FVA-GEO-016",
                                f"{p}/targets/{ti}/{sem}",
                                "Morph target count differs from the vertex count",
                                {"count": acc.accessors[ai].get("count"), "vertices": n},
                            )
        # skin attributes
        if "JOINTS_0" in pr.attributes or "WEIGHTS_0" in pr.attributes:
            if ("JOINTS_0" in pr.attributes) != ("WEIGHTS_0" in pr.attributes):
                ctx.add("FVA-SKN-004", p + "/attributes", "JOINTS_0 and WEIGHTS_0 must be used together")
            self.skin_attributes(pr)
        return pr

    def degenerate(self, pr: Prim, mode: int, n: int) -> int:
        idx = pr.indices or []
        if mode == 4:
            tris = [(idx[i], idx[i + 1], idx[i + 2]) for i in range(0, len(idx) - 2, 3)]
        elif mode == 5:
            tris = [
                (idx[i], idx[i + 1], idx[i + 2]) if i % 2 == 0 else (idx[i + 1], idx[i], idx[i + 2])
                for i in range(len(idx) - 2)
            ]
        elif mode == 6:
            tris = [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)]
        else:
            return 0
        pos = pr.positions.values if pr.positions is not None else None
        eps = 0.0
        if pr.bbox:
            d2 = sum((pr.bbox[1][k] - pr.bbox[0][k]) ** 2 for k in range(3))
            eps = d2 * d2 * 1e-24  # |cross|^2 scales with length^4
        bad = 0
        for t, (a, b, c) in enumerate(tris):
            if t & 4095 == 0:
                self.ctx.tick(4096)
            if a == b or b == c or a == c:
                bad += 1
                continue
            if pos is None or max(a, b, c) >= n:
                continue
            ax, ay, az = pos[3 * a : 3 * a + 3]
            ux, uy, uz = pos[3 * b] - ax, pos[3 * b + 1] - ay, pos[3 * b + 2] - az
            vx, vy, vz = pos[3 * c] - ax, pos[3 * c + 1] - ay, pos[3 * c + 2] - az
            cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            if not cx * cx + cy * cy + cz * cz > eps:
                bad += 1
        pr.degenerate = bad
        if bad:
            self.ctx.add(
                "FVA-GEO-006",
                pr.pointer,
                "Primitive contains degenerate (zero-area) triangles",
                {"degenerate": bad, "triangles": len(tris)},
            )
        return len(tris)

    def skin_attributes(self, pr: Prim) -> None:
        acc, ctx, p = self.m.acc, self.ctx, pr.pointer + "/attributes"
        j = acc.get(pr.attributes.get("JOINTS_0")) if "JOINTS_0" in pr.attributes else None
        w = acc.get(pr.attributes.get("WEIGHTS_0")) if "WEIGHTS_0" in pr.attributes else None
        pr.joints, pr.weights = j, w
        if w is None or w.components != 4:
            return
        neg = zero = unnorm = 0
        tol = 2e-3 if w.component_type == 5126 else 4.0 / 255.0
        vals = w.values
        for k in range(0, len(vals), 4):
            q = vals[k : k + 4]
            s = q[0] + q[1] + q[2] + q[3]
            if min(q) < 0:
                neg += 1
            if s == 0:
                zero += 1
            elif abs(s - 1.0) > tol:
                unnorm += 1
        if neg:
            ctx.add("FVA-SKN-006", p + "/WEIGHTS_0", "Negative joint weights", {"vertices": neg})
        if zero:
            ctx.add("FVA-SKN-010", p + "/WEIGHTS_0", "Vertices with zero total weight", {"vertices": zero})
        if unnorm:
            ctx.add("FVA-SKN-007", p + "/WEIGHTS_0", "Joint weights do not sum to 1", {"vertices": unnorm})

    # -- nodes and scenes -----------------------------------------------------------
    def nodes(self) -> None:
        ctx, m = self.ctx, self.m
        nodes = self.arr("nodes")
        m.nodes = nodes
        n = len(nodes)
        parents: list[int | None] = [None] * n
        m.local = [None] * n
        for i, node in enumerate(nodes):
            p = f"/nodes/{i}"
            ch = node.get("children", [])
            if not isinstance(ch, list):
                ctx.add("FVA-CON-009", p + "/children", "children must be an array")
                ch = []
            for c in ch:
                if not is_int(c) or not 0 <= c < n or c == i:
                    ctx.add("FVA-SCN-001", p + "/children", "Invalid child index", {"child": c if is_num(c) else None})
                elif parents[c] is not None:
                    ctx.add("FVA-SCN-001", f"/nodes/{c}", "Node has more than one parent", {"parents": [parents[c], i]})
                else:
                    parents[c] = i
            m.local[i] = self.transform(node, p)
            if "mesh" in node and not (is_int(node["mesh"]) and 0 <= node["mesh"] < len(m.mesh_prims)):
                ctx.add("FVA-CON-011", p + "/mesh", "node references a missing mesh", {"mesh": node["mesh"]})
            if "skin" in node:
                if "mesh" not in node:
                    ctx.add("FVA-SKN-008", p, "Node references a skin but has no mesh")
                if not (is_int(node["skin"]) and 0 <= node["skin"] < list_len(self.doc.get("skins"))):
                    ctx.add("FVA-CON-011", p + "/skin", "node references a missing skin", {"skin": node["skin"]})
                elif any(k in node for k in ("matrix", "translation", "rotation", "scale")):
                    ctx.add("FVA-SCN-007", p, "Skinned mesh node has a local transform that glTF ignores")
            if "camera" in node and not (
                is_int(node["camera"]) and 0 <= node["camera"] < list_len(self.doc.get("cameras"))
            ):
                ctx.add("FVA-CON-011", p + "/camera", "node references a missing camera")
        # cycle detection: walk parent chains
        for i in range(n):
            seen = {i}
            j = parents[i]
            depth = 0
            while j is not None:
                depth += 1
                if j in seen:
                    ctx.add("FVA-SCN-001", f"/nodes/{i}", "Node hierarchy contains a cycle")
                    parents[i] = None  # break the cycle so traversal terminates
                    break
                if depth > ctx.limits.max_node_depth:
                    raise ctx.abort(
                        "FVA-RES-005",
                        f"/nodes/{i}",
                        "Node hierarchy exceeds the maximum depth",
                        {"max_node_depth": ctx.limits.max_node_depth},
                    )
                seen.add(j)
                j = parents[j]
        m.parents = parents
        # world transforms (independent of scenes)
        for i in range(n):
            self.world_of(i)

    def world_of(self, i: int) -> list[float]:
        m = self.m
        if i in m.world:
            return m.world[i]
        chain = []
        j: int | None = i
        while j is not None and j not in m.world and len(chain) <= self.ctx.limits.max_node_depth:
            chain.append(j)
            j = m.parents[j]
        base = m.world[j] if j is not None and j in m.world else mu.IDENTITY
        for k in reversed(chain):
            base = mu.mul(base, m.local[k] or mu.IDENTITY)
            m.world[k] = base
        return m.world[i]

    def transform(self, node: dict, p: str) -> list[float] | None:
        ctx = self.ctx
        if "matrix" in node:
            mat = node["matrix"]
            if any(k in node for k in ("translation", "rotation", "scale")):
                ctx.add("FVA-SCN-003", p, "Node defines both matrix and TRS")
            if not (isinstance(mat, list) and len(mat) == 16 and all(is_num(x) for x in mat)):
                ctx.add("FVA-CON-009", p + "/matrix", "matrix must be 16 numbers")
                return None
            if not mu.finite(mat):
                ctx.add("FVA-SCN-002", p + "/matrix", "Node matrix is not finite")
                return None
            if abs(mu.det3(mat)) < 1e-12:
                ctx.add("FVA-SCN-008", p + "/matrix", "Node matrix is singular (zero scale)")
            return [float(x) for x in mat]
        t = node.get("translation", [0.0, 0.0, 0.0])
        r = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
        s = node.get("scale", [1.0, 1.0, 1.0])
        ok = True
        for key, v, k in (("translation", t, 3), ("rotation", r, 4), ("scale", s, 3)):
            if not (isinstance(v, list) and len(v) == k and all(is_num(x) for x in v)):
                ctx.add("FVA-CON-009", f"{p}/{key}", f"{key} must be {k} numbers")
                ok = False
            elif not mu.finite(v):
                ctx.add(
                    "FVA-SCN-002",
                    f"{p}/{key}",
                    f"Node {key} is not finite",
                    {key: [x if math.isfinite(x) else str(x) for x in v]},
                )
                ok = False
        if not ok:
            return None
        ln = math.sqrt(sum(x * x for x in r))
        if abs(ln - 1.0) > 1e-3:
            ctx.add("FVA-SCN-004", p + "/rotation", "Node rotation is not a unit quaternion", {"length": round(ln, 6)})
            r = [x / ln for x in r] if ln > 0 else [0.0, 0.0, 0.0, 1.0]
        if any(abs(x) < 1e-9 for x in s):
            ctx.add("FVA-SCN-008", p + "/scale", "Node scale has a zero component")
        if t == [0.0, 0.0, 0.0] and r == [0.0, 0.0, 0.0, 1.0] and s == [1.0, 1.0, 1.0]:
            return None
        return mu.from_trs(t, r, s)

    def scenes(self) -> None:
        ctx, m = self.ctx, self.m
        scenes = self.arr("scenes")
        n = len(m.nodes)
        if "scene" in self.doc:
            s = self.doc["scene"]
            if not (is_int(s) and 0 <= s < len(scenes)):
                ctx.add("FVA-CON-011", "/scene", "Default scene index is invalid", {"scene": s})
            else:
                m.scene_index = s
        elif scenes:
            ctx.add("FVA-SCN-006", "/scene", "No default scene; scene 0 is assumed")
            m.scene_index = 0
        else:
            ctx.add("FVA-SCN-006", "/", "Asset defines no scenes")
        for si, sc in enumerate(scenes):
            roots = sc.get("nodes", [])
            if not isinstance(roots, list):
                ctx.add("FVA-CON-009", f"/scenes/{si}/nodes", "scene.nodes must be an array")
                continue
            for r in roots:
                if not is_int(r) or not 0 <= r < n:
                    ctx.add("FVA-CON-011", f"/scenes/{si}/nodes", "scene references a missing node", {"node": r})
                elif m.parents[r] is not None:
                    ctx.add("FVA-SCN-005", f"/scenes/{si}/nodes", "Scene lists a node that has a parent", {"node": r})
            if len(set(x for x in roots if is_int(x))) != len([x for x in roots if is_int(x)]):
                ctx.add("FVA-SCN-005", f"/scenes/{si}/nodes", "Scene lists a node more than once")
        if m.scene_index is not None:
            roots = scenes[m.scene_index].get("nodes", [])
            m.scene_nodes = (
                self.descendants([r for r in roots if is_int(r) and 0 <= r < n and m.parents[r] is None])
                if isinstance(roots, list)
                else []
            )

    def descendants(self, roots: list[int]) -> list[int]:
        out, stack, seen = [], list(reversed(roots)), set()
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            out.append(i)
            ch = self.m.nodes[i].get("children", [])
            if isinstance(ch, list):
                stack.extend(
                    c for c in reversed(ch) if is_int(c) and 0 <= c < len(self.m.nodes) and self.m.parents[c] == i
                )
        return out

    # -- skins ----------------------------------------------------------------------
    def skins(self) -> None:
        ctx, m, acc = self.ctx, self.m, self.m.acc
        n = len(m.nodes)
        for si, sk in enumerate(self.arr("skins")):
            p = f"/skins/{si}"
            joints = sk.get("joints")
            info: dict[str, Any] = {
                "index": si,
                "name": sk.get("name") if isinstance(sk.get("name"), str) else None,
                "joints": [],
                "joint_names": [],
                "valid": False,
                "rest_consistent": None,
            }
            if not (isinstance(joints, list) and joints and all(is_int(j) and 0 <= j < n for j in joints)) or len(
                set(joints)
            ) != len(joints):
                ctx.add("FVA-SKN-001", p + "/joints", "Skin joints must be a non-empty list of unique existing nodes")
                m.skins.append(info)
                continue
            info["joints"] = joints
            info["joint_names"] = [
                m.nodes[j].get("name") if isinstance(m.nodes[j].get("name"), str) else None for j in joints
            ]
            info["valid"] = True
            roots = {self.root_of(j) for j in joints}
            if len(roots) > 1:
                ctx.add(
                    "FVA-SKN-003", p + "/joints", "Skin joints do not share one hierarchy", {"roots": sorted(roots)[:8]}
                )
                info["valid"] = False
            skel = sk.get("skeleton")
            if skel is not None:
                if not (is_int(skel) and 0 <= skel < n) or not all(self.is_ancestor_or_self(skel, j) for j in joints):
                    ctx.add(
                        "FVA-SKN-003",
                        p + "/skeleton",
                        "skin.skeleton must be a common root of all joints",
                        {"skeleton": skel if is_num(skel) else None},
                    )
                    info["valid"] = False
            info["skeleton"] = skel
            ibm = None
            if "inverseBindMatrices" in sk:
                ai = sk["inverseBindMatrices"]
                if not (is_int(ai) and 0 <= ai < len(acc.accessors)):
                    ctx.add("FVA-CON-011", p + "/inverseBindMatrices", "Missing inverseBindMatrices accessor")
                else:
                    a = acc.accessors[ai]
                    if (
                        a.get("type") != "MAT4"
                        or a.get("componentType") != 5126
                        or not is_int(a.get("count"))
                        or a["count"] < len(joints)
                    ):
                        ctx.add(
                            "FVA-SKN-002",
                            p + "/inverseBindMatrices",
                            "inverseBindMatrices must be float MAT4 with one matrix per joint",
                            {"type": a.get("type"), "count": a.get("count"), "joints": len(joints)},
                        )
                        info["valid"] = False
                    else:
                        dec = acc.get(ai)
                        if dec is not None:
                            ibm = [dec.values[k * 16 : (k + 1) * 16] for k in range(len(joints))]
            if ibm is not None:
                bad = [
                    k
                    for k, mt in enumerate(ibm)
                    if not mu.finite(mt)
                    or mu.inverse(mt) is None
                    or max(abs(mt[3]), abs(mt[7]), abs(mt[11]), abs(mt[15] - 1.0)) > 1e-5
                ]
                if bad:
                    ctx.add(
                        "FVA-SKN-002",
                        p + "/inverseBindMatrices",
                        "Inverse bind matrices must be finite, affine and invertible",
                        {"joints": bad[:16]},
                    )
                    info["valid"] = False
                else:
                    mismatch = [
                        k
                        for k, (j, mt) in enumerate(zip(joints, ibm))
                        if mu.max_abs_diff(mu.mul(m.world[j], mt), mu.IDENTITY) > 1e-3
                    ]
                    info["rest_consistent"] = not mismatch
                    if mismatch:
                        ctx.add(
                            "FVA-SKN-009",
                            p + "/inverseBindMatrices",
                            "Bind pose differs from the node rest pose",
                            {"joints": len(mismatch)},
                        )
            info["inverse_bind_matrices"] = ibm
            info["depth"] = max(self.depth_of(j) for j in joints) - min(self.depth_of(j) for j in joints)
            m.skins.append(info)
        # joint palette checks for skinned nodes
        for i, node in enumerate(m.nodes):
            sk, mesh = node.get("skin"), node.get("mesh")
            if not (is_int(sk) and 0 <= sk < len(m.skins) and is_int(mesh) and mesh in m.mesh_prims):
                continue
            nj = len(m.skins[sk]["joints"])
            for pr in m.mesh_prims[mesh]:
                if "JOINTS_0" not in pr.attributes:
                    ctx.add(
                        "FVA-SKN-004",
                        pr.pointer + "/attributes",
                        "Skinned primitive lacks JOINTS_0/WEIGHTS_0",
                        {"node": i},
                    )
                elif pr.joints is not None and nj:
                    w = pr.weights.values if pr.weights is not None else None
                    oob = 0
                    for k, j in enumerate(pr.joints.values):
                        if j >= nj and (w is None or (k < len(w) and w[k] != 0)):
                            oob += 1
                    if oob:
                        ctx.add(
                            "FVA-SKN-005",
                            pr.pointer + "/attributes/JOINTS_0",
                            "Joint indices exceed the skin's joint count",
                            {"influences": oob, "joints": nj},
                        )

    def root_of(self, i: int) -> int:
        while self.m.parents[i] is not None:
            i = self.m.parents[i]
        return i

    def depth_of(self, i: int) -> int:
        d = 0
        while self.m.parents[i] is not None:
            i, d = self.m.parents[i], d + 1
        return d

    def is_ancestor_or_self(self, a: int, i: int) -> bool:
        j: int | None = i
        while j is not None:
            if j == a:
                return True
            j = self.m.parents[j]
        return False

    # -- animations ---------------------------------------------------------------
    def animations(self) -> None:
        ctx, m = self.ctx, self.m
        joint_nodes = {j for s in m.skins for j in s["joints"]}
        for ai, an in enumerate(self.arr("animations")):
            p = f"/animations/{ai}"
            name = an.get("name") if isinstance(an.get("name"), str) else None
            if name is None:
                ctx.add("FVA-ANM-010", p, "Animation has no name")
            samplers = an.get("samplers") if isinstance(an.get("samplers"), list) else []
            channels = an.get("channels") if isinstance(an.get("channels"), list) else []
            info: dict[str, Any] = {
                "index": ai,
                "name": name,
                "channels": len(channels),
                "duration": 0.0,
                "kinds": [],
                "paths": {},
                "targets": [],
                "loops": None,
                "valid": True,
                "interpolations": [],
            }
            if not channels or not samplers:
                ctx.add("FVA-ANM-008", p, "Animation needs at least one channel and sampler")
                info["valid"] = False
            smp_info: list[dict | None] = []
            for si, s in enumerate(samplers):
                smp_info.append(self.sampler(f"{p}/samplers/{si}", s))
            seen = set()
            kinds = set()
            loops = []
            interps = set()
            for ci, ch in enumerate(channels):
                cp = f"{p}/channels/{ci}"
                if not isinstance(ch, dict):
                    ctx.add("FVA-CON-009", cp, "channel must be an object")
                    info["valid"] = False
                    continue
                t = ch.get("target") if isinstance(ch.get("target"), dict) else {}
                node, path = t.get("node"), hkey(t.get("path"))
                if path not in PATHS:
                    ctx.add("FVA-ANM-001", cp + "/target/path", "Invalid channel target path", {"path": str(path)[:32]})
                    info["valid"] = False
                    continue
                if node is None:
                    continue  # targeted through an extension (e.g. KHR_animation_pointer)
                if not (is_int(node) and 0 <= node < len(m.nodes)):
                    ctx.add("FVA-ANM-001", cp + "/target/node", "Channel targets a missing node", {"node": node})
                    info["valid"] = False
                    continue
                if (node, path) in seen:
                    ctx.add(
                        "FVA-ANM-005", cp, "Duplicate channel for the same node and path", {"node": node, "path": path}
                    )
                    info["valid"] = False
                seen.add((node, path))
                si = ch.get("sampler")
                if not (is_int(si) and 0 <= si < len(samplers)):
                    ctx.add("FVA-ANM-002", cp + "/sampler", "Channel references a missing sampler", {"sampler": si})
                    info["valid"] = False
                    continue
                s = smp_info[si]
                if s is None:
                    info["valid"] = False
                    continue
                interps.add(s["interpolation"])
                info["duration"] = max(info["duration"], s["duration"])
                kinds.add("morph" if path == "weights" else "skeletal" if node in joint_nodes else "node")
                info["paths"][path] = info["paths"].get(path, 0) + 1
                info["targets"].append(node)
                if not self.channel_output(cp, s, path, node, samplers[si], info):
                    info["valid"] = False
                elif s.get("loops") is not None:
                    loops.append(s["loops"])
            info["kinds"] = sorted(kinds)
            info["interpolations"] = sorted(interps)
            info["targets"] = sorted(set(info["targets"]))
            info["loops"] = all(loops) if loops else None
            info["duration"] = round(info["duration"], 6)
            m.animations.append(info)

    def sampler(self, p: str, s: Any) -> dict | None:
        ctx, acc = self.ctx, self.m.acc
        if not isinstance(s, dict):
            ctx.add("FVA-CON-009", p, "sampler must be an object")
            return None
        interp = hkey(s.get("interpolation", "LINEAR"))
        if interp not in ("LINEAR", "STEP", "CUBICSPLINE"):
            ctx.add("FVA-ANM-002", p + "/interpolation", "Invalid interpolation", {"interpolation": str(interp)[:16]})
            return None
        ii = s.get("input")
        if not (is_int(ii) and 0 <= ii < len(acc.accessors)):
            ctx.add("FVA-ANM-002", p + "/input", "Sampler input references a missing accessor")
            return None
        a = acc.accessors[ii]
        if a.get("type") != "SCALAR" or a.get("componentType") != 5126:
            ctx.add("FVA-ANM-002", p + "/input", "Sampler input must be float SCALAR")
            return None
        dec = acc.get(ii)
        if dec is None:
            return None
        acc.check_bounds(ii, dec, True, p)
        times = dec.values
        if any(x < 0 for x in times):
            ctx.add("FVA-ANM-009", p + "/input", "Keyframe times must be >= 0")
        bad = sum(1 for x, y in zip(times, times[1:]) if not y > x)
        if bad:
            ctx.add("FVA-ANM-003", p + "/input", "Keyframe times are not strictly increasing", {"violations": bad})
            return None
        if interp == "CUBICSPLINE" and len(times) < 2:
            ctx.add("FVA-ANM-002", p, "CUBICSPLINE requires at least two keyframes")
            return None
        return {
            "interpolation": interp,
            "times": times,
            "keys": len(times),
            "duration": max(times) if times and all(math.isfinite(x) for x in times) else 0.0,
            "output": s.get("output"),
        }

    def channel_output(self, cp: str, s: dict, path: str, node: int, raw: dict, info: dict) -> bool:
        ctx, m, acc = self.ctx, self.m, self.m.acc
        oi = s["output"]
        if not (is_int(oi) and 0 <= oi < len(acc.accessors)):
            ctx.add("FVA-ANM-002", cp, "Sampler output references a missing accessor")
            return False
        a = acc.accessors[oi]
        want_type, comps = PATHS[path]
        ok_ct = {5126} if path in ("translation", "scale") else {5126, 5120, 5121, 5122, 5123}
        if (
            a.get("type") != want_type
            or hkey(a.get("componentType")) not in ok_ct
            or (a.get("componentType") != 5126 and a.get("normalized") is not True)
        ):
            ctx.add(
                "FVA-ANM-002",
                cp,
                "Sampler output encoding does not match the target path",
                {"path": path, "type": a.get("type"), "componentType": a.get("componentType")},
            )
            return False
        mult = 3 if s["interpolation"] == "CUBICSPLINE" else 1
        targets = 1
        if path == "weights":
            mesh = m.nodes[node].get("mesh")
            prims = m.mesh_prims.get(mesh, []) if is_int(mesh) else []
            targets = prims[0].targets if prims else 0
            if not targets:
                ctx.add("FVA-ANM-007", cp, "weights animation targets a node without morph targets", {"node": node})
                return False
        expected = s["keys"] * mult * targets
        if a.get("count") != expected:
            ctx.add(
                "FVA-ANM-004",
                cp,
                "Output keyframe count does not match input keys",
                {"expected": expected, "actual": a.get("count")},
            )
            return False
        dec = acc.get(oi)
        if dec is None:
            return False
        vals = dec.values
        if path == "rotation" and s["interpolation"] != "CUBICSPLINE":
            bad = 0
            for k in range(0, len(vals), 4):
                ln = math.sqrt(sum(x * x for x in vals[k : k + 4]))
                if abs(ln - 1.0) > 1e-3:
                    bad += 1
            if bad:
                ctx.add("FVA-ANM-006", cp, "Rotation keyframes are not unit quaternions", {"keys": bad})
                return False
        if mult == 1 and s["keys"] >= 2:
            w = comps * targets
            first, last = vals[:w], vals[len(vals) - w :]
            s["loops"] = all(abs(x - y) <= 1e-3 for x, y in zip(first, last)) or (
                path == "rotation" and all(abs(x + y) <= 1e-3 for x, y in zip(first, last))
            )
        return True

    # -- usage / bounds / metrics ---------------------------------------------------
    def unused(self) -> None:
        for i in range(len(self.m.materials)):
            if i not in self.used_materials:
                self.ctx.add("FVA-MAT-010", f"/materials/{i}", "Material is not used by any primitive")
        for i in range(len(self.m.textures)):
            if i not in self.used_textures:
                self.ctx.add("FVA-MAT-010", f"/textures/{i}", "Texture is not used by any material")
        for i in range(len(self.m.images)):
            if i not in self.used_images:
                self.ctx.add("FVA-MAT-010", f"/images/{i}", "Image is not used by any texture")

    def instances(self) -> list[tuple[int, int, bool]]:
        """(node, mesh, skinned) for mesh nodes in the default scene (all mesh nodes when no scene)."""
        m = self.m
        nodes = m.scene_nodes if m.scene_index is not None else range(len(m.nodes))
        out = []
        for i in nodes:
            mesh = m.nodes[i].get("mesh")
            if is_int(mesh) and mesh in m.mesh_prims:
                out.append((i, mesh, is_int(m.nodes[i].get("skin"))))
        if not out and m.scene_index is None:
            out = [(-1, mi, False) for mi in m.mesh_prims]
        return out

    def bounds(self) -> None:
        m = self.m
        lo = [math.inf] * 3
        hi = [-math.inf] * 3
        for node, mesh, skinned in self.instances():
            mat = mu.IDENTITY if skinned or node < 0 else m.world.get(node, mu.IDENTITY)
            for pr in m.mesh_prims[mesh]:
                if pr.bbox is None:
                    continue
                (x0, y0, z0), (x1, y1, z1) = pr.bbox
                for c in (
                    (x0, y0, z0),
                    (x0, y0, z1),
                    (x0, y1, z0),
                    (x0, y1, z1),
                    (x1, y0, z0),
                    (x1, y0, z1),
                    (x1, y1, z0),
                    (x1, y1, z1),
                ):
                    w = mu.apply(mat, c)
                    for k in range(3):
                        lo[k] = min(lo[k], w[k])
                        hi[k] = max(hi[k], w[k])
        if not all(math.isfinite(x) for x in lo + hi):
            if m.prims:
                self.ctx.add("FVA-GEO-011", "/", "Scene has no finite geometric extent")
            m.bounds = None
            return
        size = [hi[k] - lo[k] for k in range(3)]
        m.bounds = {
            "min": [round(x, 6) for x in lo],
            "max": [round(x, 6) for x in hi],
            "size": [round(x, 6) for x in size],
            "frame": "gltf (Y up, metres)",
        }
        if max(size) <= 1e-6:
            self.ctx.add("FVA-GEO-011", "/", "Scene geometry has zero extent", {"size": m.bounds["size"]})
        elif max(size) > 10_000:
            self.ctx.add(
                "FVA-GEO-011", "/", "Scene geometry is larger than 10 km; check units", {"size": m.bounds["size"]}
            )

    def metrics(self) -> None:
        m, b = self.m, self.m.budget
        inst = self.instances()
        tris = sum(pr.triangles for _, mesh, _ in inst for pr in m.mesh_prims[mesh])
        verts = sum(pr.vertices for _, mesh, _ in inst for pr in m.mesh_prims[mesh])
        draws = sum(len(m.mesh_prims[mesh]) for _, mesh, _ in inst)
        degenerate = sum(pr.degenerate for _, mesh, _ in inst for pr in m.mesh_prims[mesh])
        dims = [max(i.get("width", 0), i.get("height", 0)) for i in m.images]
        joints = len({j for s in m.skins for j in s["joints"]})
        morph = max((pr.targets for pr in m.prims), default=0)
        mt = {
            "file_bytes": m.byte_length,
            "nodes": len(m.nodes),
            "scene_nodes": len(m.scene_nodes),
            "meshes": len(m.mesh_prims),
            "mesh_instances": len(inst),
            "primitives": len(m.prims),
            "draw_calls": draws,
            "vertices": verts,
            "triangles": tris,
            "degenerate_triangles": degenerate,
            "materials": len(m.materials),
            "textures": len(m.textures),
            "images": len(m.images),
            "max_texture_dimension": max(dims, default=0),
            "texture_pixels": sum(i.get("width", 0) * i.get("height", 0) for i in m.images),
            "skins": len(m.skins),
            "joints": joints,
            "animations": len(m.animations),
            "animation_duration_s": round(max((a["duration"] for a in m.animations), default=0.0), 6),
            "morph_targets": morph,
            "external_dependencies": sum(1 for r in self.resolver.resources if r.uri_class in ("relative", "remote")),
        }
        m.metrics = mt
        checks = [
            ("FVA-CPX-001", "triangles", b.max_triangles),
            ("FVA-CPX-002", "vertices", b.max_vertices),
            ("FVA-CPX-003", "file_bytes", b.max_file_bytes),
            ("FVA-CPX-004", "draw_calls", b.max_draw_calls),
            ("FVA-CPX-005", "materials", b.max_materials),
            ("FVA-CPX-006", "joints", b.max_joints),
            ("FVA-CPX-007", "animations", b.max_animations),
            ("FVA-CPX-008", "morph_targets", b.max_morph_targets),
            ("FVA-CPX-009", "nodes", b.max_nodes),
        ]
        for code, key, bv in checks:
            if mt[key] > bv.value:
                self.ctx.add(
                    code,
                    "/",
                    f"{key} exceeds the configured runtime budget",
                    {"actual": mt[key], "budget": bv.value, "budget_basis": bv.basis, "budget_name": b.name},
                )


def _embedded(p: str, data: bytes):
    from .container import Resource

    return Resource(p, "buffer", "embedded", None, data)
