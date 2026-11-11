"""Correct the measured ipsilateral arm swing in a CF1 Elara GLB.

Run with the Studio or Blender Python environment. The operation preserves
every original GLB byte outside four reviewed animation output accessors.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from statistics import correlation
import numpy as np
import bpy
from mathutils import Matrix, Quaternion, Vector

def glb(data):
    magic, version, declared_length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or declared_length != len(data):
        raise ValueError("expected one complete GLB 2.0")
    size, kind = struct.unpack_from("<I4s", data, 12)
    if kind != b"JSON" or size > 1024 * 1024:
        raise ValueError("expected a bounded GLB JSON chunk")
    binary_size, binary_kind = struct.unpack_from("<I4s", data, 20 + size)
    prefix = 28 + size
    if binary_kind != b"BIN\x00" or prefix + binary_size != len(data):
        raise ValueError("expected one embedded GLB binary chunk")
    return json.loads(data[20:20 + size]), bytearray(data[prefix:]), prefix


def track(document, buffer, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    axes = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    if accessor["componentType"] != 5126 or "sparse" in accessor or view["buffer"] != 0:
        raise ValueError("expected an embedded non-sparse float accessor")
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", axes * 4)
    end = start + (accessor["count"] - 1) * stride + axes * 4
    if not 0 <= start < end <= len(buffer) or end > view.get("byteOffset", 0) + view["byteLength"]:
        raise ValueError("animation accessor exceeds its buffer view")
    return np.ndarray((accessor["count"], axes), dtype="<f4", buffer=buffer,
                      offset=start, strides=(stride, 4))


def quaternion(values):
    x, y, z, w = map(float, values)
    return Quaternion((w, x, y, z))


def sample(document, buffer, phase):
    clip = next(clip for clip in document["animations"] if clip["name"] == "Elara_Walk")
    duration = max(document["accessors"][sampler["input"]]["max"][0]
                   for sampler in clip["samplers"])
    poses = [node.copy() for node in document["nodes"]]
    time = phase * duration
    for channel in clip["channels"]:
        target = channel["target"]
        sampler = clip["samplers"][channel["sampler"]]
        times = track(document, buffer, sampler["input"])[:, 0]
        values = track(document, buffer, sampler["output"])
        successor = np.searchsorted(times, time, side="right")
        left = max(0, successor - 1)
        right = min(successor, len(times) - 1)
        weight = 0.0
        if left != right and sampler["interpolation"] != "STEP":
            weight = (time - times[left]) / (times[right] - times[left])
        prop = target["path"]
        if prop == "rotation":
            rotation = quaternion(values[left]).slerp(quaternion(values[right]), float(weight))
            result = [rotation.x, rotation.y, rotation.z, rotation.w]
        else:
            result = values[left] * (1 - weight) + values[right] * weight
        poses[target["node"]][prop] = result

    parents = {child: i for i, node in enumerate(poses) for child in node.get("children", [])}
    cache = {}

    def world(index):
        if index in cache:
            return cache[index]
        node = poses[index]
        if "matrix" in node:
            data = node["matrix"]
            local = Matrix(tuple(data[i:i + 4] for i in range(0, 16, 4))).transposed()
        else:
            local = Matrix.LocRotScale(Vector(node.get("translation", (0, 0, 0))),
                                       quaternion(node.get("rotation", (0, 0, 0, 1))),
                                       Vector(node.get("scale", (1, 1, 1))))
        cache[index] = world(parents[index]) @ local if index in parents else local
        return cache[index]

    return {node["name"]: list(world(i).translation)
            for i, node in enumerate(poses) if "name" in node}


def metrics(doc, buf):
    poses=[sample(doc,buf,i/48) for i in range(48)]
    def delta(a,b):
        return [pose[a][2]-pose[b][2] for pose in poses]
    report = {}
    for side,opp in [('L','R'),('R','L')]:
        foot=delta('foot.'+side,'upperleg01.'+side)
        arm=delta('lowerarm01.'+side,'upperarm01.'+side)
        opposite=delta('foot.'+opp,'upperleg01.'+opp)
        report[side] = {"same_side": correlation(arm, foot),
                        "opposite_side": correlation(arm, opposite),
                        "arm_excursion_m": max(arm) - min(arm),
                        "ankle_excursion_m": max(foot) - min(foot)}
    return report

def sha(data):
    return hashlib.sha256(data).hexdigest()


def repair(path, out, expected, editable):
    original = path.read_bytes()
    if sha(original) != expected:
        raise ValueError("source digest differs from the reviewed input")
    doc, buffer, prefix = glb(original)
    before = metrics(doc, buffer)
    if any(m["same_side"] < 0.6 or m["opposite_side"] > -0.6 for m in before.values()):
        raise ValueError("the source does not exhibit the measured ipsilateral fault")
    clip = next(c for c in doc["animations"] if c["name"] == "Elara_Walk")
    names = {f"{bone}.{side}" for bone in ("upperarm01", "lowerarm01") for side in ("L", "R")}
    edited = []
    for channel in clip["channels"]:
        target = channel["target"]
        node = doc["nodes"][target["node"]]["name"]
        if node not in names or target["path"] != "rotation":
            continue
        sampler = clip["samplers"][channel["sampler"]]
        output = sampler["output"]
        uses = sum(
            anim["samplers"][item["sampler"]]["output"] == output
            for anim in doc["animations"] for item in anim["channels"]
        )
        if uses != 1 or sampler["interpolation"] != "LINEAR":
            raise ValueError(f"{node} uses a shared or unsupported rotation accessor")
        times = track(doc, buffer, sampler["input"])[:, 0]
        values = track(doc, buffer, output)
        steps = len(times) - 1
        if (steps < 4 or steps % 2 or len(values) != len(times)
                or not np.allclose(np.diff(times), (times[-1] - times[0]) / steps, atol=1e-5)
                or abs(float(np.dot(values[0], values[-1]))) < 0.999):
            raise ValueError(f"{node} does not have a periodic, evenly sampled curve")
        corrected = np.roll(values[:-1].copy(), steps // 2, axis=0)
        values[:-1] = corrected
        values[-1] = corrected[0]
        edited.append(node)
    if set(edited) != names:
        raise ValueError("four unique arm rotation tracks required")
    after = metrics(doc, buffer)
    for side, measurement in after.items():
        if (measurement["same_side"] > -0.6 or measurement["opposite_side"] < 0.6
                or abs(measurement["ankle_excursion_m"] - before[side]["ankle_excursion_m"]) > 1e-6):
            raise ValueError("corrected gait did not preserve ankle excursion and establish opposite coordination")
    payload = original[:prefix] + buffer
    out.mkdir(mode=0o700)
    candidate = out / "elara-gait.glb"
    candidate.write_bytes(payload)
    receipt = {
        "schema": "finalverse.elara-gait/1", "source_sha256": expected,
        "candidate_sha256": sha(payload), "affected_tracks": sorted(edited),
        "samples_per_cycle": 48, "before": before, "after": after,
        "method": "upper and lower arms advanced by half of the authored walk cycle",
        "studio_version": bpy.app.version_string,
    }
    if editable:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(candidate.resolve()))
        bpy.ops.file.pack_all()
        blend = out / "elara-gait.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()))
        receipt["editable_sha256"] = sha(blend.read_bytes())
    (out / "gait.json").write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--editable", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    repair(args.source, args.output, args.source_sha256, args.editable)


if __name__ == "__main__":
    main()
