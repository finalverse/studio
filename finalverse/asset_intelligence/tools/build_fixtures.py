"""Build the S3-A fixture assets deterministically.

    python tools/build_fixtures.py            # write fixtures/
    python tools/build_fixtures.py --check    # verify committed fixtures are reproducible

Fixtures are synthetic test assets authored by this script; they claim no other
provenance (their asset.generator is "Finalverse S3-A fixture builder/1").
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests"))

from gltf_builder import Builder, box, octahedron, png, quat  # noqa: E402

FIXTURES = HERE.parent / "fixtures"
F, U16, U32 = 5126, 5123, 5125

JOINTS = (
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
PARENTS = (None, 0, 1, 2, 3, 4, 3, 6, 7, 8, 3, 10, 11, 12, 1, 14, 15, 1, 17, 18, 5, 5, 5, 9, 13, 5)
REST = (
    (0, 0, 0),
    (0, 0.95, 0),
    (0, 0.12, 0),
    (0, 0.2, 0),
    (0, 0.22, 0),
    (0, 0.1, 0),
    (0.08, 0.18, 0),
    (0.12, 0, 0),
    (0, -0.28, 0),
    (0, -0.25, 0),
    (-0.08, 0.18, 0),
    (-0.12, 0, 0),
    (0, -0.28, 0),
    (0, -0.25, 0),
    (0.1, -0.05, 0),
    (0, -0.42, 0),
    (0, -0.42, 0),
    (-0.1, -0.05, 0),
    (0, -0.42, 0),
    (0, -0.42, 0),
    (0.035, 0.08, 0.09),
    (-0.035, 0.08, 0.09),
    (0, 0.02, 0.06),
    (0, -0.08, 0),
    (0, -0.08, 0),
    (0, 0.2, 0),
)


def _global(j: int) -> tuple[float, float, float]:
    x = y = z = 0.0
    while j is not None:
        t = REST[j]
        x, y, z = x + t[0], y + t[1], z + t[2]
        j = PARENTS[j]
    return x, y, z


def humanoid() -> bytes:
    """Canonical finalverse.humanoid/v1 body, rigid per-part weights, five rotation-only clips."""
    b = Builder()
    g = [_global(j) for j in range(26)]
    for j in range(26):
        node = {"name": JOINTS[j], "translation": [float(v) for v in REST[j]]}
        kids = [k for k in range(26) if PARENTS[k] == j]
        if kids:
            node["children"] = kids
        b.add("nodes", node)
    # (joint, centre offset from joint global, size, primitive)
    parts = [
        (1, (0, 0.02, 0), (0.3, 0.16, 0.18), 1),
        (2, (0, 0.1, 0), (0.28, 0.2, 0.17), 1),
        (3, (0, 0.11, 0), (0.34, 0.22, 0.2), 1),
        (4, (0, 0.05, 0), (0.08, 0.1, 0.08), 0),
        (5, (0, 0.1, 0.0), (0.18, 0.2, 0.2), 0),
        (7, (0, -0.14, 0), (0.08, 0.28, 0.08), 1),
        (8, (0, -0.125, 0), (0.07, 0.25, 0.07), 0),
        (9, (0, -0.05, 0), (0.06, 0.1, 0.04), 0),
        (11, (0, -0.14, 0), (0.08, 0.28, 0.08), 1),
        (12, (0, -0.125, 0), (0.07, 0.25, 0.07), 0),
        (13, (0, -0.05, 0), (0.06, 0.1, 0.04), 0),
        (15, (0, 0.21, 0), (0.11, 0.42, 0.11), 1),
        (16, (0, 0.19, 0), (0.09, 0.4, 0.09), 1),
        (18, (0, 0.21, 0), (0.11, 0.42, 0.11), 1),
        (19, (0, 0.19, 0), (0.09, 0.4, 0.09), 1),
        (16, (0, -0.02, 0.04), (0.1, 0.08, 0.2), 1),
        (19, (0, -0.02, 0.04), (0.1, 0.08, 0.2), 1),
        (20, (0, 0, 0.012), (0.03, 0.03, 0.02), 0),
        (21, (0, 0, 0.012), (0.03, 0.03, 0.02), 0),
        (22, (0, -0.02, 0.01), (0.1, 0.04, 0.06), 0),
    ]
    prims = []
    for prim in (0, 1):
        P, N, J, W, IDX = [], [], [], [], []
        for joint, off, size, which in parts:
            if which != prim:
                continue
            c = [g[joint][k] + off[k] for k in range(3)]
            pos, nrm, _, idx = box(*c, *size)
            base = len(P)
            P += pos
            N += nrm
            J += [(joint, 0, 0, 0)] * len(pos)
            W += [(1.0, 0.0, 0.0, 0.0)] * len(pos)
            IDX += [base + i for i in idx]
        attrs = {
            "POSITION": b.accessor(P, F, "VEC3", minmax=True, target=34962),
            "NORMAL": b.accessor(N, F, "VEC3", target=34962),
            "JOINTS_0": b.accessor(J, U16, "VEC4", target=34962),
            "WEIGHTS_0": b.accessor(W, F, "VEC4", target=34962),
        }
        prims.append(
            {"attributes": attrs, "indices": b.accessor(IDX, U32, "SCALAR", target=34963), "material": prim, "mode": 4}
        )
    b.add(
        "materials",
        {
            "name": "skin",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.78, 0.6, 0.5, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.7,
            },
        },
    )
    b.add(
        "materials",
        {
            "name": "clothing",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.2, 0.32, 0.45, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.9,
            },
        },
    )
    b.add("meshes", {"name": "body", "primitives": prims})
    ibm = []
    for j in range(26):
        x, y, z = g[j]
        ibm.append((1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -x, -y, -z, 1))
    b.add("skins", {"joints": list(range(26)), "inverseBindMatrices": b.accessor(ibm, F, "MAT4"), "name": "humanoid"})
    b.add("nodes", {"mesh": 0, "name": "body", "skin": 0})
    times = [0.0, 0.5, 1.0, 1.5, 2.0]
    X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    clips = {
        "idle": {3: [(X, a) for a in (0, 2, 0, -2, 0)], 5: [(Y, a) for a in (0, 4, 0, -4, 0)]},
        "walk": {
            14: [(X, a) for a in (0, -25, 0, 25, 0)],
            17: [(X, a) for a in (0, 25, 0, -25, 0)],
            15: [(X, a) for a in (0, 20, 5, 0, 0)],
            18: [(X, a) for a in (0, 0, 5, 20, 0)],
            7: [(X, a) for a in (0, 20, 0, -20, 0)],
            11: [(X, a) for a in (0, -20, 0, 20, 0)],
        },
        "turn": {0: [(Y, a) for a in (0, 22.5, 45, 22.5, 0)]},
        "greet": {7: [(Z, a) for a in (0, 150, 150, 150, 0)], 8: [(Z, a) for a in (0, 20, -20, 20, 0)]},
        "speak": {22: [(X, a) for a in (0, 12, 0, 12, 0)], 5: [(X, a) for a in (0, 3, 0, 3, 0)]},
    }
    for name, tracks in clips.items():
        samplers, channels = [], []
        for joint, keys in sorted(tracks.items()):
            tin = b.accessor(times, F, "SCALAR", minmax=True)
            tout = b.accessor([quat(ax, a) for ax, a in keys], F, "VEC4")
            samplers.append({"input": tin, "interpolation": "LINEAR", "output": tout})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": joint, "path": "rotation"}})
        b.add("animations", {"channels": channels, "name": name, "samplers": samplers})
    b.doc["scene"] = 0
    b.doc["scenes"] = [{"nodes": [0, 26]}]
    return b.glb()


def wisp() -> bytes:
    """Floating spirit: no skeleton; node bob + spin and a morph-target pulse; emissive, translucent."""
    b = Builder()
    pos, nrm, idx = octahedron(0, 0, 0, 0.25)
    pulse = [(p[0] * 0.2, p[1] * 0.2, p[2] * 0.2) for p in pos]
    core_prim = {
        "attributes": {"POSITION": b.accessor(pos, F, "VEC3", minmax=True), "NORMAL": b.accessor(nrm, F, "VEC3")},
        "indices": b.accessor(idx, U32, "SCALAR"),
        "material": 0,
        "mode": 4,
        "targets": [{"POSITION": b.accessor(pulse, F, "VEC3", minmax=True)}],
    }
    b.add(
        "materials",
        {
            "name": "spirit_core",
            "alphaMode": "BLEND",
            "doubleSided": True,
            "emissiveFactor": [0.55, 0.85, 1.0],
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.7, 0.9, 1.0, 0.75],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.3,
            },
        },
    )
    b.add(
        "materials",
        {
            "name": "spirit_mote",
            "emissiveFactor": [1.0, 0.95, 0.7],
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 0.95, 0.8, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.5,
            },
        },
    )
    b.add("meshes", {"extras": {"targetNames": ["pulse"]}, "name": "core", "primitives": [core_prim], "weights": [0.0]})
    mpos, mnrm, midx = octahedron(0, 0, 0, 0.06)
    b.add(
        "meshes",
        {
            "name": "mote",
            "primitives": [
                {
                    "attributes": {
                        "POSITION": b.accessor(mpos, F, "VEC3", minmax=True),
                        "NORMAL": b.accessor(mnrm, F, "VEC3"),
                    },
                    "indices": b.accessor(midx, U32, "SCALAR"),
                    "material": 1,
                    "mode": 4,
                }
            ],
        },
    )
    b.add("nodes", {"children": [1, 2, 3, 4], "name": "wisp", "translation": [0.0, 1.2, 0.0]})
    b.add("nodes", {"mesh": 0, "name": "core"})
    for k, (x, z) in enumerate(((0.4, 0.0), (-0.2, 0.35), (-0.2, -0.35))):
        b.add("nodes", {"mesh": 1, "name": f"mote_{k}", "translation": [x, 0.05 * k, z]})
    times = [0.0, 1.0, 2.0, 3.0, 4.0]
    t_in = b.accessor(times, F, "SCALAR", minmax=True)
    bob = b.accessor([(0, 1.2, 0), (0, 1.3, 0), (0, 1.2, 0), (0, 1.1, 0), (0, 1.2, 0)], F, "VEC3")
    spin = b.accessor([quat((0, 1, 0), a) for a in (0, 90, 180, 270, 360)], F, "VEC4")
    breathe = b.accessor([0.0, 1.0, 0.0, 1.0, 0.0], F, "SCALAR")
    b.add(
        "animations",
        {
            "name": "idle_float",
            "samplers": [
                {"input": t_in, "interpolation": "LINEAR", "output": bob},
                {"input": t_in, "interpolation": "LINEAR", "output": spin},
                {"input": t_in, "interpolation": "LINEAR", "output": breathe},
            ],
            "channels": [
                {"sampler": 0, "target": {"node": 0, "path": "translation"}},
                {"sampler": 1, "target": {"node": 0, "path": "rotation"}},
                {"sampler": 2, "target": {"node": 1, "path": "weights"}},
            ],
        },
    )
    b.doc["scene"] = 0
    b.doc["scenes"] = [{"name": "wisp", "nodes": [0]}]
    return b.glb()


def defective() -> bytes:
    """Intentionally defective creature. Every defect is documented in S3A-ACCEPTANCE.md."""
    b = Builder()
    pos, nrm, _, idx = box(0, 0.5, 0, 1, 1, 1)
    idx = idx[:-3] + [0, 0, 1] + [99, 1, 2]  # degenerate triangle + out-of-range index
    prim = {
        "attributes": {
            "POSITION": b.accessor(pos, F, "VEC3", minmax=True),  # NORMAL omitted
            "JOINTS_0": b.accessor([(0, 1, 0, 0)] * len(pos), U16, "VEC4"),
            "WEIGHTS_0": b.accessor([(0.5, 0.5, 0, 0)] * len(pos), F, "VEC4"),
        },
        "indices": b.accessor(idx, U32, "SCALAR"),
        "material": 0,
        "mode": 4,
    }
    b.add("images", {"uri": "https://example.invalid/creature_albedo.png"})  # remote dependency
    b.add("textures", {"source": 0})
    b.add(
        "materials",
        {
            "name": "hide",
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.2, 0.4, 0.3, 1.0],  # out of range
                "baseColorTexture": {"index": 0},
            },
        },
    )  # needs TEXCOORD_0
    b.add("meshes", {"name": "creature", "primitives": [prim]})
    b.add("nodes", {"children": [1, 2], "name": "creature_root"})
    b.add("nodes", {"name": "spine", "translation": [0.0, b.raw("1e400"), 0.0]})  # non-finite transform
    b.add("nodes", {"mesh": 0, "name": "body", "skin": 0})
    b.add("skins", {"joints": [1, 40], "name": "broken_rig"})  # missing joint node
    tin = b.accessor([0.0, 1.0, 1.0, 0.5], F, "SCALAR", minmax=True)  # not increasing
    tout = b.accessor([quat((1, 0, 0), a) for a in (0, 10, 20, 0)], F, "VEC4")
    b.add(
        "animations",
        {
            "name": "twitch",
            "samplers": [{"input": tin, "interpolation": "LINEAR", "output": tout}],
            "channels": [
                {"sampler": 0, "target": {"node": 1, "path": "rotation"}},
                {"sampler": 0, "target": {"node": 99, "path": "rotation"}},
            ],
        },
    )
    b.doc["extensionsUsed"] = ["KHR_draco_mesh_compression"]
    b.doc["extensionsRequired"] = ["KHR_draco_mesh_compression"]  # unsupported required ext
    b.doc["scene"] = 0
    b.doc["scenes"] = [{"nodes": [0]}]
    return b.glb()


def static_prop() -> bytes:
    """Static prop in the reviewed EC subset (single node, POSITION/NORMAL/TEXCOORD_0, factor-only PBR)."""
    b = Builder()
    prims = []
    for k, (c, s) in enumerate((((0, 0.4, 0), (0.8, 0.8, 0.8)), ((0, 0.85, 0), (0.9, 0.1, 0.9)))):
        pos, nrm, uv, idx = box(*c, *s)
        prims.append(
            {
                "attributes": {
                    "NORMAL": b.accessor(nrm, F, "VEC3"),
                    "POSITION": b.accessor(pos, F, "VEC3", minmax=True),
                    "TEXCOORD_0": b.accessor(uv, F, "VEC2"),
                },
                "indices": b.accessor(idx, U32, "SCALAR"),
                "material": k,
                "mode": 4,
            }
        )
    for name, col in (("wood", [0.55, 0.38, 0.22, 1.0]), ("lid", [0.35, 0.25, 0.15, 1.0])):
        b.add(
            "materials",
            {
                "emissiveFactor": [0.0, 0.0, 0.0],
                "name": name,
                "pbrMetallicRoughness": {"baseColorFactor": col, "metallicFactor": 0.0, "roughnessFactor": 0.8},
            },
        )
    b.add("meshes", {"primitives": prims})
    b.add("nodes", {"mesh": 0})
    b.doc["scene"] = 0
    b.doc["scenes"] = [{"nodes": [0]}]
    return b.glb()


def textured_gltf() -> dict[str, bytes]:
    """Separate .gltf + .bin + PNG texture (valid glTF with local external dependencies)."""
    b = Builder()
    pos, nrm, uv, idx = box(0, 0.25, 0, 0.5, 0.5, 0.5)
    b.add("images", {"mimeType": "image/png", "uri": "crate_albedo.png"})
    b.add("samplers", {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
    b.add("textures", {"sampler": 0, "source": 0})
    b.add(
        "materials",
        {
            "name": "crate",
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "baseColorTexture": {"index": 0},
                "metallicFactor": 0.0,
                "roughnessFactor": 0.85,
            },
        },
    )
    b.add(
        "meshes",
        {
            "name": "crate",
            "primitives": [
                {
                    "attributes": {
                        "NORMAL": b.accessor(nrm, F, "VEC3"),
                        "POSITION": b.accessor(pos, F, "VEC3", minmax=True),
                        "TEXCOORD_0": b.accessor(uv, F, "VEC2"),
                    },
                    "indices": b.accessor(idx, U32, "SCALAR"),
                    "material": 0,
                    "mode": 4,
                }
            ],
        },
    )
    b.add("nodes", {"mesh": 0, "name": "crate"})
    b.doc["scene"] = 0
    b.doc["scenes"] = [{"nodes": [0]}]
    j, binary = b.gltf("textured_crate.bin")
    return {
        "textured_crate.gltf": j,
        "textured_crate.bin": binary,
        "crate_albedo.png": png(16, 16, (150, 110, 70, 255)),
    }


def all_fixtures() -> dict[str, bytes]:
    out = {
        "humanoid_walker.glb": humanoid(),
        "floating_wisp.glb": wisp(),
        "defective_creature.glb": defective(),
        "static_prop.glb": static_prop(),
    }
    out.update(textured_gltf())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    fx = all_fixtures()
    bad = 0
    for name, data in sorted(fx.items()):
        path = FIXTURES / name
        digest = hashlib.sha256(data).hexdigest()
        if args.check:
            ok = path.is_file() and path.read_bytes() == data
            bad += not ok
            print(f"{'ok  ' if ok else 'DIFF'} {name} {digest}")
        else:
            FIXTURES.mkdir(exist_ok=True)
            path.write_bytes(data)
            print(f"wrote {name} {len(data)} bytes sha256 {digest}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
