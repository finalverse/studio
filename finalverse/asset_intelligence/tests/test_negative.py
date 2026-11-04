"""Negative fixtures: corrupt containers, invalid data, hostile URIs, resource limits."""

from __future__ import annotations

import copy
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

from helpers import (
    FIXTURES,
    BudgetValue,
    Limits,
    RuntimeBudget,
    codes,
    finding,
    glb_json,
    rep_bytes,
    rep_path,
    replace_json,
)

STATIC = (FIXTURES / "static_prop.glb").read_bytes()
HUMANOID = (FIXTURES / "humanoid_walker.glb").read_bytes()
WISP = (FIXTURES / "floating_wisp.glb").read_bytes()


def mutate(base: bytes, fn) -> bytes:
    doc = glb_json(base)
    fn(doc)
    return replace_json(base, doc)


class Containers(unittest.TestCase):
    def test_corrupt_header_version(self):
        bad = STATIC[:4] + struct.pack("<I", 3) + STATIC[8:]
        _, r = rep_bytes(bad)
        self.assertEqual(codes(r), {"FVA-CON-002"})
        self.assertEqual(r["validation"]["status"], "invalid")
        self.assertFalse(r["validation"]["inspection_complete"])

    def test_not_gltf(self):
        _, r = rep_bytes(b"\x00\x01binary garbage" * 4)
        self.assertEqual(codes(r), {"FVA-CON-001"})

    def test_truncated_binary(self):
        for cut in (5, 11, 19, 40, len(STATIC) // 2, len(STATIC) - 1):
            with self.subTest(cut=cut):
                _, r = rep_bytes(STATIC[:cut])
                self.assertEqual(r["validation"]["status"], "invalid")
                self.assertTrue(codes(r) & {"FVA-CON-003", "FVA-CON-004", "FVA-CON-001"})

    def test_truncated_with_patched_length_hits_chunk_bounds(self):
        cut = STATIC[: len(STATIC) - 64]
        cut = cut[:8] + struct.pack("<I", len(cut)) + cut[12:]
        _, r = rep_bytes(cut)
        self.assertIn("FVA-CON-004", codes(r))

    def test_misaligned_chunk(self):
        doc = glb_json(STATIC)
        j = json.dumps(doc, separators=(",", ":")).encode()
        j += b" " * ((-len(j) % 4) + 1)
        n = struct.unpack_from("<I", STATIC, 12)[0]
        body = struct.pack("<I4s", len(j), b"JSON") + j + STATIC[20 + n :]
        _, r = rep_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
        self.assertIn("FVA-CON-005", codes(r))

    def test_bom_and_duplicates_and_nonfinite(self):
        text = (
            '{"asset":{"version":"2.0","version":"2.0"},"scenes":[{"nodes":[0]}],"nodes":[{"translation":[0,1e999,0]}]}'
        )
        _, r = rep_bytes(b"\xef\xbb\xbf" + text.encode(), name="t.gltf")
        self.assertTrue({"FVA-CON-006", "FVA-CON-007", "FVA-CON-008", "FVA-SCN-002"} <= codes(r))

    def test_untrusted_metadata_never_reaches_report_raw(self):
        """Regression (fuzz seed 102): a non-string asset.generator holding NaN broke the digest."""
        text = '{"asset":{"version":"2.0","generator":[{"translation":[0,NaN,0]}],"copyright":7}}'
        _, r = rep_bytes(text.encode(), name="t.gltf")
        self.assertIsNone(r["asset"]["generator"])
        self.assertEqual(r["inspection"]["asset"]["copyright"], None)
        json.dumps(r, allow_nan=False)

    def test_unsupported_version(self):
        _, r = rep_bytes(b'{"asset":{"version":"3.0"}}', name="t.gltf")
        self.assertEqual(codes(r), {"FVA-CON-010"})

    def test_json_depth_bomb_is_refused_before_parsing(self):
        bomb = b'{"asset":{"version":"2.0"},"extras":' + b"[" * 100000 + b"]" * 100000 + b"}"
        _, r = rep_bytes(bomb, name="t.gltf")
        self.assertEqual(codes(r), {"FVA-RES-002"})
        self.assertEqual(r["validation"]["status"], "refused")


class Accessors(unittest.TestCase):
    def test_accessor_out_of_bounds(self):
        _, r = rep_bytes(mutate(STATIC, lambda d: d["accessors"][1].__setitem__("count", 10_000)))
        self.assertIn("FVA-BUF-005", codes(r))
        self.assertEqual(r["validation"]["status"], "invalid")

    def test_accessor_bad_component_type(self):
        _, r = rep_bytes(mutate(STATIC, lambda d: d["accessors"][0].__setitem__("componentType", 1234)))
        self.assertIn("FVA-BUF-007", codes(r))

    def test_misaligned_accessor(self):
        _, r = rep_bytes(mutate(STATIC, lambda d: d["accessors"][0].__setitem__("byteOffset", 2)))
        self.assertIn("FVA-BUF-006", codes(r))

    def test_bounds_mismatch_and_missing(self):
        def f(d):
            d["accessors"][1]["max"] = [9.0, 9.0, 9.0]
            del d["accessors"][5]["min"]

        _, r = rep_bytes(mutate(STATIC, f))
        self.assertTrue({"FVA-BUF-008", "FVA-BUF-009"} <= codes(r))

    def test_buffer_view_out_of_buffer(self):
        _, r = rep_bytes(mutate(STATIC, lambda d: d["bufferViews"][0].__setitem__("byteLength", 10**7)))
        self.assertIn("FVA-BUF-003", codes(r))

    def test_bad_stride(self):
        _, r = rep_bytes(mutate(STATIC, lambda d: d["bufferViews"][0].__setitem__("byteStride", 6)))
        self.assertIn("FVA-BUF-004", codes(r))

    def test_nonfinite_float_data(self):
        doc = glb_json(STATIC)
        n = struct.unpack_from("<I", STATIC, 12)[0]
        bin_start = 20 + n + 8
        off = bin_start + doc["bufferViews"][doc["accessors"][1]["bufferView"]]["byteOffset"]
        bad = STATIC[:off] + struct.pack("<f", float("nan")) + STATIC[off + 4 :]
        _, r = rep_bytes(bad)
        self.assertIn("FVA-BUF-010", codes(r))

    def test_invalid_index(self):
        doc = glb_json(STATIC)
        n = struct.unpack_from("<I", STATIC, 12)[0]
        off = 20 + n + 8 + doc["bufferViews"][doc["accessors"][3]["bufferView"]]["byteOffset"]
        bad = STATIC[:off] + struct.pack("<I", 4000) + STATIC[off + 4 :]
        _, r = rep_bytes(bad)
        f = finding(r, "FVA-GEO-003")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["evidence"]["out_of_range"], 1)
        self.assertEqual(f[0]["component"], "/meshes/0/primitives/0/indices")
        ec = next(p for p in r["compatibility"]["runtime"] if p["id"] == "finalverse.ec-static-glb/v1")
        self.assertEqual(ec["status"], "incompatible")

    def test_sparse_accessor_applied_and_validated(self):
        b = __import__("gltf_builder").Builder()
        pos = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        a = b.accessor(pos, 5126, "VEC3", minmax=True)
        iv = b.view(struct.pack("<2H", 2, 1))
        vv = b.view(struct.pack("<6f", 0, 2, 0, 0, 0, 3))
        b.doc["accessors"][a]["sparse"] = {
            "count": 2,
            "indices": {"bufferView": iv, "componentType": 5123},
            "values": {"bufferView": vv},
        }
        b.add("meshes", {"primitives": [{"attributes": {"POSITION": a}}]})
        b.add("nodes", {"mesh": 0})
        b.doc["scenes"], b.doc["scene"] = [{"nodes": [0]}], 0
        _, r = rep_bytes(b.glb())
        self.assertIn("FVA-BUF-011", codes(r))  # indices 2,1 not increasing


class Materials(unittest.TestCase):
    def test_missing_local_texture(self):
        with tempfile.TemporaryDirectory() as td:
            for name in ("textured_crate.gltf", "textured_crate.bin"):
                (Path(td) / name).write_bytes((FIXTURES / name).read_bytes())
            _, r = rep_path(Path(td) / "textured_crate.gltf")
        self.assertIn("FVA-DEP-001", codes(r))
        self.assertEqual(r["validation"]["status"], "invalid")
        self.assertFalse(
            r["quality"]["categories"]["material_completeness"]["checklist"]["texture_dependencies_complete"]
        )

    def test_texture_reference_and_alpha(self):
        def f(d):
            d["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 7}
            d["materials"][0]["alphaMode"] = "GLOW"
            d["materials"][1]["alphaCutoff"] = 0.5

        _, r = rep_bytes(mutate(STATIC, f))
        self.assertTrue({"FVA-MAT-004", "FVA-MAT-002", "FVA-MAT-003"} <= codes(r))

    def test_image_mime_mismatch_and_dimensions(self):
        from gltf_builder import png

        b = __import__("gltf_builder").Builder()
        img = b.view(png(8192, 3, (1, 2, 3, 255)))
        b.add("images", {"bufferView": img, "mimeType": "image/jpeg"})
        b.add("textures", {"source": 0})
        _, r = rep_bytes(b.glb())
        self.assertTrue({"FVA-MAT-005", "FVA-MAT-007", "FVA-MAT-008"} <= codes(r))


class Skeletons(unittest.TestCase):
    def test_invalid_skeleton_disconnected_joints(self):
        def f(d):
            d["nodes"][3]["children"] = [4]  # chest no longer parents shoulders -> still one tree
            d["nodes"].append({"name": "orphan"})
            d["skins"][0]["joints"][25] = len(d["nodes"]) - 1

        _, r = rep_bytes(mutate(HUMANOID, f))
        self.assertIn("FVA-SKN-003", codes(r))

    def test_inverse_bind_count(self):
        def f(d):
            d["accessors"][d["skins"][0]["inverseBindMatrices"]]["count"] = 3

        _, r = rep_bytes(mutate(HUMANOID, f))
        self.assertIn("FVA-SKN-002", codes(r))

    def test_skeleton_root_not_ancestor(self):
        _, r = rep_bytes(mutate(HUMANOID, lambda d: d["skins"][0].__setitem__("skeleton", 5)))
        self.assertIn("FVA-SKN-003", codes(r))

    def test_hierarchy_cycle_and_multiple_parents(self):
        def f(d):
            d["nodes"][5]["children"] = [20, 21, 22, 25, 1]

        _, r = rep_bytes(mutate(HUMANOID, f))
        self.assertIn("FVA-SCN-001", codes(r))

    def test_bind_pose_mismatch_breaks_humanoid_rig(self):
        _, r = rep_bytes(
            mutate(HUMANOID, lambda d: d["nodes"][15].__setitem__("translation", [0.0, -0.5, 0.0])),
            embodiment_profile="biological_humanoid",
        )
        self.assertIn("FVA-SKN-009", codes(r))
        self.assertIn("FVA-EMB-001", codes(r))
        bh = next(e for e in r["compatibility"]["embodiment"] if e["profile"] == "biological_humanoid")
        self.assertEqual(bh["status"], "incompatible")

    def test_names_alone_do_not_make_a_humanoid(self):
        def f(d):
            d["nodes"][3]["translation"] = [0.0, 0.2, 0.0]
            d["nodes"][3]["rotation"] = [0.0, 0.7071068, 0.0, 0.7071068]

        _, r = rep_bytes(mutate(HUMANOID, f), embodiment_profile="biological_humanoid")
        bh = next(e for e in r["compatibility"]["embodiment"] if e["profile"] == "biological_humanoid")
        self.assertEqual(bh["requirements"][0]["outcome"], "fail")


class Animations(unittest.TestCase):
    def test_output_count_mismatch(self):
        def f(d):
            out = d["animations"][0]["samplers"][0]["output"]
            d["accessors"][out]["count"] -= 1

        _, r = rep_bytes(mutate(HUMANOID, f))
        self.assertIn("FVA-ANM-004", codes(r))

    def test_bad_interpolation_and_path(self):
        def f(d):
            d["animations"][0]["samplers"][0]["interpolation"] = "BEZIER"
            d["animations"][1]["channels"][0]["target"]["path"] = "colour"

        _, r = rep_bytes(mutate(HUMANOID, f))
        self.assertTrue({"FVA-ANM-002", "FVA-ANM-001"} <= codes(r))

    def test_duplicate_channel_and_weights_without_targets(self):
        def f(d):
            ch = d["animations"][0]["channels"]
            ch.append(copy.deepcopy(ch[0]))

        _, r = rep_bytes(mutate(HUMANOID, f))
        self.assertIn("FVA-ANM-005", codes(r))

        def g(d):
            d["meshes"][0]["primitives"][0].pop("targets")
            d["meshes"][0].pop("weights")

        _, r = rep_bytes(mutate(WISP, g))
        self.assertIn("FVA-ANM-007", codes(r))

    def test_empty_animation(self):
        _, r = rep_bytes(mutate(HUMANOID, lambda d: d["animations"].append({"channels": [], "samplers": []})))
        self.assertIn("FVA-ANM-008", codes(r))


class Extensions(unittest.TestCase):
    def test_required_must_be_used_and_declared(self):
        def f(d):
            d["extensionsRequired"] = ["KHR_materials_unlit"]
            d["materials"][0]["extensions"] = {"KHR_materials_unlit": {}, "EXT_vendor_thing": {}}

        _, r = rep_bytes(mutate(STATIC, f))
        self.assertTrue({"FVA-EXT-001", "FVA-EXT-002", "FVA-EXT-003"} <= codes(r))
        rt = {p["id"]: p for p in r["compatibility"]["runtime"]}
        self.assertEqual(rt["infinity.entry-glb/observed"]["status"], "incompatible")

    def test_optional_extension_is_unverified_not_unsupported(self):
        def f(d):
            d["extensionsUsed"] = ["KHR_materials_emissive_strength"]
            d["materials"][0]["extensions"] = {"KHR_materials_emissive_strength": {"emissiveStrength": 4.0}}

        _, r = rep_bytes(mutate(STATIC, f))
        f4 = finding(r, "FVA-EXT-004")
        self.assertEqual(len(f4), 1)
        self.assertEqual(f4[0]["severity"], "info")
        self.assertEqual(r["validation"]["status"], "valid")


class Limits_(unittest.TestCase):
    def test_oversized_file_refused(self):
        _, r = rep_bytes(HUMANOID, limits=Limits(max_file_bytes=1024))
        self.assertEqual(codes(r), {"FVA-RES-001"})
        self.assertEqual(r["validation"]["status"], "refused")

    def test_oversized_file_not_read_from_disk(self):
        m, r = rep_path(FIXTURES / "humanoid_walker.glb", limits=Limits(max_file_bytes=1024))
        self.assertEqual(m.data, b"")
        self.assertEqual(r["asset"]["byte_length"], len(HUMANOID))

    def test_runtime_budget_exceeded_is_valid_but_flagged(self):
        budget = RuntimeBudget(name="tight", max_triangles=BudgetValue(10, "test"), max_joints=BudgetValue(8, "test"))
        _, r = rep_bytes(HUMANOID, budget=budget)
        self.assertEqual(r["validation"]["status"], "valid_exceeds_limits")
        self.assertTrue(r["validation"]["spec_valid"])
        self.assertTrue({"FVA-CPX-001", "FVA-CPX-006"} <= codes(r))
        self.assertEqual(r["quality"]["tier"]["certified"], "Q0")

    def test_decode_budget_makes_inspection_incomplete(self):
        _, r = rep_bytes(HUMANOID, limits=Limits(max_decoded_components=1000))
        self.assertIn("FVA-RES-003", codes(r))
        self.assertFalse(r["validation"]["inspection_complete"])
        self.assertEqual(r["validation"]["status"], "refused")

    def test_array_length_limit(self):
        _, r = rep_bytes(HUMANOID, limits=Limits(max_array_length=10))
        self.assertEqual(codes(r), {"FVA-RES-002"})

    def test_node_depth_limit(self):
        nodes = [{"children": [i + 1]} for i in range(400)] + [{}]
        doc = {"asset": {"version": "2.0"}, "nodes": nodes, "scenes": [{"nodes": [0]}], "scene": 0}
        _, r = rep_bytes(json.dumps(doc).encode(), name="t.gltf")
        self.assertIn("FVA-RES-005", codes(r))


class HostileUris(unittest.TestCase):
    def _gltf(self, td: Path, uri: str) -> Path:
        doc = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 4, "uri": uri}],
            "images": [{"uri": uri}],
            "textures": [{"source": 0}],
        }
        p = td / "evil.gltf"
        p.write_text(json.dumps(doc))
        return p

    def test_remote_and_unsafe_uris_never_resolved(self):
        cases = {
            "http://169.254.169.254/latest/meta-data": "FVA-SEC-001",
            "https://example.invalid/a.bin": "FVA-SEC-001",
            "file:///etc/passwd": "FVA-SEC-001",
            "ftp://x/y": "FVA-SEC-001",
            "../../../../etc/passwd": "FVA-SEC-002",
            "/etc/passwd": "FVA-SEC-002",
            "..%2F..%2Fetc%2Fpasswd": "FVA-SEC-002",
            "C:\\Windows\\win.ini": "FVA-SEC-002",
            "sub/../../outside.bin": "FVA-SEC-002",
        }
        with tempfile.TemporaryDirectory() as td:
            for uri, code in cases.items():
                with self.subTest(uri=uri):
                    m, r = rep_path(self._gltf(Path(td), uri))
                    self.assertIn(code, codes(r))
                    self.assertEqual(r["validation"]["status"], "refused")
                    self.assertTrue(all("sha256" not in d for d in r["inspection"]["dependencies"]["items"]))

    def test_symlink_escape_refused(self):
        with tempfile.TemporaryDirectory() as outer:
            secret = Path(outer) / "secret.bin"
            secret.write_bytes(b"SECRET!!")
            inner = Path(outer) / "asset"
            inner.mkdir()
            os.symlink(secret, inner / "link.bin")
            _, r = rep_path(self._gltf(inner, "link.bin"))
        self.assertIn("FVA-SEC-002", codes(r))

    def test_bytes_input_never_reads_local_files(self):
        doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 4, "uri": "data.bin"}]}
        m, r = rep_bytes(json.dumps(doc).encode(), name="t.gltf")
        dep = r["inspection"]["dependencies"]["items"][0]
        self.assertEqual(dep["status"], "unresolved")

    def test_data_uri(self):
        good = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 4, "uri": "data:application/octet-stream;base64,AAAAAA=="}],
        }
        _, r = rep_bytes(json.dumps(good).encode(), name="t.gltf")
        self.assertNotIn("FVA-SEC-003", codes(r))
        bad = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 4, "uri": "data:application/octet-stream,AAAA"}]}
        _, r = rep_bytes(json.dumps(bad).encode(), name="t.gltf")
        self.assertIn("FVA-SEC-003", codes(r))


if __name__ == "__main__":
    unittest.main()
