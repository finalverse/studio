"""GLB / glTF container parsing and the resource (URI) policy.

Nothing here performs network access.  Remote URIs are recorded and refused.
Local files are read only for ``.gltf``/GLB assets inspected from a path, only
inside the asset's directory, and only when ``Limits.allow_local_resources``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from . import jsonstrict
from .context import Ctx

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


@dataclass
class Container:
    kind: str  # "glb" | "gltf"
    doc: Any
    bin_chunk: bytes | None
    layout: dict[str, Any] = field(default_factory=dict)


def parse_container(data: bytes, ctx: Ctx) -> Container:
    if data[:4] == GLB_MAGIC:
        return _parse_glb(data, ctx)
    head = data[:64].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"{"):
        doc = jsonstrict.parse(data, ctx)
        return Container("gltf", doc, None, {"json_byte_length": len(data)})
    raise ctx.abort(
        "FVA-CON-001",
        "/",
        "Not a glTF asset: neither GLB magic nor a JSON object",
        {"leading_bytes_hex": data[:8].hex()},
    )


def _parse_glb(data: bytes, ctx: Ctx) -> Container:
    n = len(data)
    if n < 12:
        raise ctx.abort("FVA-CON-003", "/", "GLB header is truncated", {"byte_length": n})
    _magic, version, length = struct.unpack_from("<4sII", data, 0)
    if version != 2:
        raise ctx.abort("FVA-CON-002", "/", "Unsupported GLB container version", {"version": version})
    if length != n:
        raise ctx.abort(
            "FVA-CON-003",
            "/",
            "GLB declared length differs from the actual byte length",
            {"declared": length, "actual": n},
        )
    layout: dict[str, Any] = {"declared_length": length, "chunks": []}
    off = 12
    json_raw = None
    bin_chunk = None
    index = 0
    while off < n:
        if off + 8 > n:
            raise ctx.abort("FVA-CON-004", "/", "GLB chunk header is truncated", {"offset": off})
        clen, ctype = struct.unpack_from("<II", data, off)
        start, end = off + 8, off + 8 + clen
        if end > n:
            raise ctx.abort(
                "FVA-CON-004", "/", "GLB chunk extends past the end of the file", {"offset": off, "chunk_length": clen}
            )
        layout["chunks"].append({"type": f"0x{ctype:08x}", "offset": off, "length": clen})
        if clen % 4:
            ctx.add(
                "FVA-CON-005", f"/glb/chunks/{index}", "GLB chunk length is not a multiple of 4", {"chunk_length": clen}
            )
        if index == 0:
            if ctype != CHUNK_JSON:
                raise ctx.abort("FVA-CON-004", "/", "The first GLB chunk must be JSON", {"type": f"0x{ctype:08x}"})
            json_raw = data[start:end]
        elif ctype == CHUNK_BIN:
            if index != 1 or bin_chunk is not None:
                ctx.add("FVA-CON-004", f"/glb/chunks/{index}", "A BIN chunk must be the second chunk", severity="error")
            else:
                bin_chunk = data[start:end]
        elif ctype == CHUNK_JSON:
            ctx.add("FVA-CON-004", f"/glb/chunks/{index}", "Only one JSON chunk is allowed", severity="error")
        # chunks of unknown type are ignored, as the specification requires
        off = end
        index += 1
    if json_raw is None:
        raise ctx.abort("FVA-CON-004", "/", "GLB has no JSON chunk")
    layout["json_byte_length"] = len(json_raw)
    layout["bin_byte_length"] = None if bin_chunk is None else len(bin_chunk)
    # trailing spaces are the specified JSON chunk padding
    doc = jsonstrict.parse(json_raw.rstrip(b" "), ctx)
    return Container("glb", doc, bin_chunk, layout)


# --- resources -----------------------------------------------------------------------

_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")
_DATA = re.compile(r"^data:([^,;]*)((?:;[^,;]*)*?)(;base64)?,", re.S)


@dataclass
class Resource:
    pointer: str
    kind: str  # buffer | image
    uri_class: str  # embedded | data | relative | remote | unsafe
    uri: str | None
    data: bytes | None
    mime: str | None = None
    status: str = "resolved"  # resolved | missing | refused | unresolved | invalid

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "component": self.pointer,
            "kind": self.kind,
            "uri_class": self.uri_class,
            "status": self.status,
        }
        if self.uri is not None and self.uri_class != "data":
            out["uri"] = self.uri[:512]
        if self.mime:
            out["media_type"] = self.mime
        if self.data is not None:
            out["byte_length"] = len(self.data)
            out["sha256"] = hashlib.sha256(self.data).hexdigest()
        return out


class Resolver:
    def __init__(self, ctx: Ctx, base_dir: Path | None) -> None:
        self.ctx = ctx
        self.base_dir = base_dir
        self.root = Path(os.path.realpath(base_dir)) if base_dir is not None else None
        self.external_files = 0
        self.total_bytes = 0
        self.resources: list[Resource] = []

    def _account(self, n: int, pointer: str) -> bool:
        if self.total_bytes + n > self.ctx.limits.max_total_buffer_bytes:
            self.ctx.add(
                "FVA-RES-003",
                pointer,
                "Resource not loaded: total resource budget exhausted",
                {"max_total_buffer_bytes": self.ctx.limits.max_total_buffer_bytes},
            )
            self.ctx.incomplete_reasons.add("FVA-RES-003")
            return False
        self.total_bytes += n
        return True

    def resolve(self, uri: Any, pointer: str, kind: str) -> Resource:
        res = self._resolve(uri, pointer, kind)
        self.resources.append(res)
        return res

    def _resolve(self, uri: Any, pointer: str, kind: str) -> Resource:
        ctx = self.ctx
        p = f"{pointer}/uri"
        if not isinstance(uri, str):
            ctx.add("FVA-CON-009", p, "uri must be a string")
            return Resource(pointer, kind, "unsafe", None, None, status="invalid")
        if uri.startswith("data:"):
            m = _DATA.match(uri)
            if not m or not m.group(3):
                ctx.add("FVA-SEC-003", p, "Only base64 data: URIs are supported")
                return Resource(pointer, kind, "data", uri, None, status="invalid")
            payload = uri[m.end() :]
            if len(payload) // 4 * 3 > ctx.limits.max_data_uri_bytes:
                ctx.add(
                    "FVA-RES-003",
                    p,
                    "data: URI exceeds the embedded-data limit",
                    {"max_data_uri_bytes": ctx.limits.max_data_uri_bytes},
                )
                ctx.incomplete_reasons.add("FVA-RES-003")
                return Resource(pointer, kind, "data", uri, None, m.group(1) or None, status="refused")
            try:
                raw = base64.b64decode(payload, validate=True)
            except (binascii.Error, ValueError):
                ctx.add("FVA-SEC-003", p, "data: URI is not valid base64")
                return Resource(pointer, kind, "data", uri, None, m.group(1) or None, status="invalid")
            if not self._account(len(raw), p):
                return Resource(pointer, kind, "data", uri, None, m.group(1) or None, status="refused")
            return Resource(pointer, kind, "data", uri, raw, m.group(1) or None)
        scheme = _SCHEME.match(uri)
        if scheme and not (len(scheme.group(1)) == 1 and uri[2:3] in ("/", "\\")):
            ctx.add(
                "FVA-SEC-001",
                p,
                "Remote or non-file URI refused; it was not fetched",
                {"scheme": scheme.group(1).lower()[:32]},
            )
            return Resource(pointer, kind, "remote", uri, None, status="refused")
        rel = unquote(uri)
        parts = re.split(r"[/\\]", rel)
        if scheme or rel.startswith(("/", "\\")) or "\x00" in rel or ".." in parts or rel.strip() == "":
            ctx.add("FVA-SEC-002", p, "Unsafe resource path refused", {"uri": uri[:256]})
            return Resource(pointer, kind, "unsafe", uri, None, status="refused")
        ctx.add("FVA-DEP-002", p, "Asset depends on an external file", {"uri": uri[:256]})
        if self.root is None or not ctx.limits.allow_local_resources:
            return Resource(pointer, kind, "relative", uri, None, status="unresolved")
        if self.external_files >= ctx.limits.max_external_files:
            ctx.add("FVA-RES-003", p, "Too many external files", {"max_external_files": ctx.limits.max_external_files})
            ctx.incomplete_reasons.add("FVA-RES-003")
            return Resource(pointer, kind, "relative", uri, None, status="refused")
        self.external_files += 1
        target = Path(os.path.realpath(self.root.joinpath(*[x for x in parts if x not in ("", ".")])))
        if target != self.root and self.root not in target.parents:
            ctx.add("FVA-SEC-002", p, "Resource path resolves outside the asset directory", {"uri": uri[:256]})
            return Resource(pointer, kind, "unsafe", uri, None, status="refused")
        if not target.is_file():
            ctx.add("FVA-DEP-001", p, "Referenced external file is missing", {"uri": uri[:256]})
            return Resource(pointer, kind, "relative", uri, None, status="missing")
        size = target.stat().st_size
        if not self._account(size, p):
            return Resource(pointer, kind, "relative", uri, None, status="refused")
        with open(target, "rb") as fh:
            raw = fh.read(size + 1)[:size]
        return Resource(pointer, kind, "relative", uri, raw)
