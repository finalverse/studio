"""Header-only image probing. Pixels are never decoded."""

from __future__ import annotations

import struct

KTX2_MAGIC = b"\xabKTX 20\xbb\r\n\x1a\n"


def probe(data: bytes) -> dict | None:
    """Return {"format", "width", "height"} from the header, or None if unrecognized/corrupt."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) >= 24 and data[12:16] == b"IHDR":
            w, h = struct.unpack(">II", data[16:24])
            return {"format": "image/png", "width": w, "height": h}
        return None
    if data.startswith(b"\xff\xd8"):
        return _jpeg(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp(data)
    if data.startswith(KTX2_MAGIC) and len(data) >= 36:
        w, h = struct.unpack_from("<II", data, 20)
        return {"format": "image/ktx2", "width": w, "height": max(h, 1)}
    return None


def _jpeg(d: bytes) -> dict | None:
    i, n = 2, len(d)
    for _ in range(4096):  # bounded marker walk
        while i < n and d[i] != 0xFF:
            i += 1
        while i < n and d[i] == 0xFF:
            i += 1
        if i >= n:
            return None
        marker = d[i]
        i += 1
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xD9 or i + 2 > n:
            return None
        seglen = struct.unpack(">H", d[i : i + 2])[0]
        if seglen < 2:
            return None
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 7 > n:
                return None
            h, w = struct.unpack(">HH", d[i + 3 : i + 7])
            return {"format": "image/jpeg", "width": w, "height": h}
        i += seglen
    return None


def _webp(d: bytes) -> dict | None:
    if len(d) < 30:
        return None
    kind = d[12:16]
    if kind == b"VP8 " and d[23:26] == b"\x9d\x01\x2a":
        w, h = struct.unpack("<HH", d[26:30])
        return {"format": "image/webp", "width": w & 0x3FFF, "height": h & 0x3FFF}
    if kind == b"VP8L" and d[20] == 0x2F:
        b = d[21:25]
        w = 1 + (((b[1] & 0x3F) << 8) | b[0])
        h = 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
        return {"format": "image/webp", "width": w, "height": h}
    if kind == b"VP8X":
        w = 1 + int.from_bytes(d[24:27], "little")
        h = 1 + int.from_bytes(d[27:30], "little")
        return {"format": "image/webp", "width": w, "height": h}
    return None
