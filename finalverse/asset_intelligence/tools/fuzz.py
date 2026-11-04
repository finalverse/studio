"""Deterministic mutation fuzzer for the inspector and report builder.

    python tools/fuzz.py --iterations 100000 --seed 1 [--crash-dir DIR]

Every input must yield a complete, JSON-serializable report with a known status;
any uncaught exception is a crash.  Mutations are byte-level (header words, chunk
lengths, random flips, truncation, splicing) and structure-aware (JSON-level
edits to the glTF document with the original BIN chunk preserved).
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import struct
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from finalverse_asset_intelligence import Limits, inspect_bytes, report  # noqa: E402

SEEDS = sorted(p for p in (ROOT / "fixtures").iterdir() if p.suffix in (".glb", ".gltf"))
STATUSES = {"valid", "valid_exceeds_limits", "invalid", "refused"}
POOL = [
    -1,
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    26,
    255,
    256,
    65535,
    65536,
    2**31,
    2**32 + 1,
    2**64,
    -(2**63),
    0.5,
    -0.0,
    1e308,
    1e-320,
    "",
    "x",
    "SCALAR",
    "VEC4",
    "MAT4",
    "LINEAR",
    "CUBICSPLINE",
    "rotation",
    "weights",
    "BLEND",
    "data:,",
    "data:application/octet-stream;base64,AAAA",
    "../x",
    "http://x",
    None,
    True,
    False,
    [],
    {},
    [0],
    [1, 2, 3],
    [0.0, 0.0, 0.0, 0.0],
    {"index": 0},
    {"nodes": [0]},
    [[[[[]]]]],
]
WORDS = [0, 1, 2, 3, 4, 0xFFFFFFFF, 0x7FFFFFFF, 0x4E4F534A, 0x004E4942, 0x46546C67]
LIMITS = Limits(time_budget_seconds=10.0, max_decoded_components=2_000_000, max_total_buffer_bytes=8 << 20)


def split(data: bytes):
    if data[:4] != b"glTF" or len(data) < 20:
        return None
    n = struct.unpack_from("<I", data, 12)[0]
    try:
        return json.loads(data[20 : 20 + n]), data[20 + n :]
    except ValueError:
        return None


def join(doc, rest: bytes) -> bytes:
    j = json.dumps(doc, separators=(",", ":")).encode()
    j += b" " * (-len(j) % 4)
    body = struct.pack("<I4s", len(j), b"JSON") + j + rest
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def nodes_of(v, max_depth: int = 48):
    """Iterative (path, value) walk; never descends past max_depth."""
    stack = [((), v)]
    while stack:
        path, x = stack.pop()
        yield path, x
        if len(path) >= max_depth:
            continue
        if isinstance(x, dict):
            stack.extend((path + (k,), y) for k, y in reversed(list(x.items())))
        elif isinstance(x, list):
            stack.extend((path + (i,), y) for i, y in reversed(list(enumerate(x))))


def pick(rng: random.Random):
    return copy.deepcopy(rng.choice(POOL))  # pool values must never be shared or mutated


def json_mutate(rng: random.Random, doc):
    for _ in range(rng.randint(1, 4)):
        items = list(nodes_of(doc))
        path, val = rng.choice(items)
        if not path:
            continue
        parent = doc
        for p in path[:-1]:
            parent = parent[p]
        key = path[-1]
        op = rng.random()
        if op < 0.45:
            parent[key] = pick(rng)
        elif op < 0.6 and isinstance(parent, dict):
            del parent[key]
        elif op < 0.7 and isinstance(parent, list):
            parent.append(copy.deepcopy(parent[key]))
        elif op < 0.8 and isinstance(val, (int, float)) and not isinstance(val, bool):
            parent[key] = val + rng.choice([-1, 1, 7, -1000, 10**6])
        elif op < 0.9 and isinstance(parent, dict):
            parent[
                rng.choice(
                    [
                        "extensions",
                        "uri",
                        "sparse",
                        "byteStride",
                        "normalized",
                        "targets",
                        "skin",
                        "matrix",
                        "extras",
                        "skeleton",
                    ]
                )
            ] = pick(rng)
        else:
            parent[key] = copy.deepcopy(rng.choice(items)[1])
    return doc


def byte_mutate(rng: random.Random, data: bytes) -> bytes:
    b = bytearray(data)
    op = rng.random()
    if op < 0.25 and len(b) >= 24:
        off = rng.choice([4, 8, 12, 16]) if rng.random() < 0.6 else rng.randrange(0, len(b) - 4) & ~3
        struct.pack_into("<I", b, off, rng.choice(WORDS))
    elif op < 0.5:
        for _ in range(rng.randint(1, 8)):
            if b:
                b[rng.randrange(len(b))] = rng.randrange(256)
    elif op < 0.65:
        b = b[: rng.randrange(len(b) + 1)]
    elif op < 0.8 and b:
        i = rng.randrange(len(b))
        b[i:i] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 16)))
    else:
        other = rng.choice(SEEDS).read_bytes()
        i, j = rng.randrange(len(b) + 1), rng.randrange(len(other) + 1)
        b = b[:i] + other[j : j + rng.randint(1, 256)] + b[i:]
    return bytes(b)


def one(data: bytes, name: str) -> str:
    m = inspect_bytes(data, name, limits=LIMITS)
    r = report(m, generated_at="2026-01-01T00:00:00Z")
    json.dumps(r, allow_nan=False)
    st = r["validation"]["status"]
    if st not in STATUSES:
        raise AssertionError(f"unknown status {st}")
    return st


def campaign(iterations: int, seed: int, crash_dir: Path | None = None, quiet: bool = False) -> dict:
    rng = random.Random(seed)
    seeds = [(p.name, p.read_bytes()) for p in SEEDS]
    stats: Counter = Counter()
    crashes = []
    t0 = time.monotonic()
    for i in range(iterations):
        name, base = rng.choice(seeds)
        if rng.random() < 0.55:
            if base[:4] == b"glTF":
                parts = split(base)
                data = join(json_mutate(rng, parts[0]), parts[1]) if parts else byte_mutate(rng, base)
            else:
                data = json.dumps(json_mutate(rng, json.loads(base))).encode()
        else:
            data = byte_mutate(rng, base)
        try:
            stats[one(data, name)] += 1
        except Exception:  # noqa: BLE001 - any exception is a crash
            stats["crash"] += 1
            crashes.append((i, traceback.format_exc()))
            if crash_dir:
                crash_dir.mkdir(parents=True, exist_ok=True)
                (crash_dir / f"crash-{seed}-{i}.bin").write_bytes(data)
        if not quiet and i and i % 10000 == 0:
            print(f"{i} inputs, {stats['crash']} crashes, {i / (time.monotonic() - t0):.0f}/s", flush=True)
    return {
        "iterations": iterations,
        "seed": seed,
        "seconds": round(time.monotonic() - t0, 2),
        "statuses": dict(sorted(stats.items())),
        "crashes": crashes,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--crash-dir", type=Path)
    a = ap.parse_args()
    res = campaign(a.iterations, a.seed, a.crash_dir)
    for i, tb in res["crashes"][:5]:
        print(f"--- crash at input {i}\n{tb}")
    print(json.dumps({k: v for k, v in res.items() if k != "crashes"} | {"crash_count": len(res["crashes"])}))
    return 1 if res["crashes"] else 0


if __name__ == "__main__":
    sys.exit(main())
