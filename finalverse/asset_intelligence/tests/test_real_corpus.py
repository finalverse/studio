"""Conformance against real Finalverse-produced GLBs.

The corpus is read from a finalverse/finalverse checkout (FINALVERSE_REPO, default
/home/user/fv-main).  Assets are not copied into Studio.  Expected outcomes come
from that repository's own acceptance evidence:

* examples/embodiment-e0/assets/*.glb: accepted E0 bodies, admitted by
  crates/embodiment Asset::load (docs/genesis/E0-ACCEPTANCE.md);
* docs/m8/generated-assets/*.glb: produced by ec::geometry::generate, which calls
  validate_glb before returning (crates/ec/src/geometry.rs).

Targeted mutations then check that each reproduced rule rejects what it should.
"""

from __future__ import annotations

import struct
import unittest

from helpers import FINALVERSE_REPO, codes, glb_json, rep_bytes, rep_path, replace_json

E0 = sorted((FINALVERSE_REPO / "examples/embodiment-e0/assets").glob("*.glb"))
M8 = sorted((FINALVERSE_REPO / "docs/m8/generated-assets").glob("*.glb"))


def runtime(r, pid):
    return next(p for p in r["compatibility"]["runtime"] if p["id"] == pid)


def failed(r, pid):
    return [x["rule"] for x in runtime(r, pid)["rules"] if x["outcome"] == "fail"]


@unittest.skipUnless(E0 and M8, "finalverse/finalverse checkout not available (set FINALVERSE_REPO)")
class RealCorpus(unittest.TestCase):
    def test_accepted_e0_bodies_pass_strict_e0(self):
        self.assertEqual(len(E0), 7)
        for p in E0:
            with self.subTest(asset=p.name):
                _, r = rep_path(p, embodiment_profile="biological_humanoid")
                self.assertEqual(runtime(r, "finalverse.humanoid/v1")["status"], "compatible")
                self.assertEqual(r["metrics"]["joints"], 26)
                self.assertEqual(r["metrics"]["animations"], 12)
                emb = {e["profile"]: e["status"] for e in r["compatibility"]["embodiment"]}
                self.assertEqual(emb["biological_humanoid"], "compatible")
                self.assertEqual(emb["floating_spirit"], "incompatible")
                self.assertEqual(failed(r, "finalverse.ec-static-glb/v1"), ["EC-04"])

    def test_e0_generator_omits_sampler_input_bounds(self):
        """Real defect: glTF 2.0 requires min/max on animation sampler inputs; E0 bodies omit them.

        Source: finalverse/finalverse scripts/embodiment_blender.py writes sampler inputs with
        acc(times, ...) without minmax=True.  The E0 loader does not require bounds, so E0
        admission passes while generic glTF validation does not.
        """
        for p in E0:
            with self.subTest(asset=p.name):
                _, r = rep_path(p)
                errs = {f["code"] for f in r["findings"] if f["severity"] == "error"}
                self.assertEqual(errs, {"FVA-BUF-009"})
                self.assertTrue(
                    all(
                        f["evidence"]["used_by"].startswith("/animations/")
                        for f in r["findings"]
                        if f["code"] == "FVA-BUF-009"
                    )
                )
                self.assertEqual(r["quality"]["categories"]["geometry_integrity"]["score"], 1.0)

    def test_m8_generated_assets_pass_ec(self):
        self.assertEqual(len(M8), 7)
        for p in M8:
            with self.subTest(asset=p.name):
                _, r = rep_path(p)
                self.assertEqual(runtime(r, "finalverse.ec-static-glb/v1")["status"], "compatible")
                self.assertEqual(r["validation"]["status"], "valid")
                self.assertNotEqual(runtime(r, "infinity.entry-glb/observed")["status"], "compatible")

    def test_e0_rule_mutations(self):
        base = E0[0].read_bytes()
        cases = {
            "E0-06": lambda d: d["asset"].__setitem__("generator", "Somebody else"),
            "E0-04": lambda d: d["nodes"][0].__setitem__("extensions", {}),
            "E0-05": lambda d: d.__setitem__("extras", {}),
            "E0-07": lambda d: d["scenes"][0].__setitem__("nodes", [26, 0]),
            "E0-09": lambda d: d["nodes"][7].__setitem__("name", "arm"),
            "E0-11": lambda d: d["meshes"][0]["primitives"][0].pop("mode"),
            "E0-16": lambda d: d["animations"][0].__setitem__("name", "dance"),
            "E0-17": lambda d: d["animations"][0]["samplers"][0].pop("interpolation"),
        }
        for rule, fn in cases.items():
            with self.subTest(rule=rule):
                doc = glb_json(base)
                fn(doc)
                _, r = rep_bytes(replace_json(base, doc))
                self.assertEqual(failed(r, "finalverse.humanoid/v1"), [rule])

    def test_e0_inverse_bind_tamper(self):
        base = E0[0].read_bytes()
        doc = glb_json(base)
        n = struct.unpack_from("<I", base, 12)[0]
        acc = doc["accessors"][doc["skins"][0]["inverseBindMatrices"]]
        off = 20 + n + 8 + doc["bufferViews"][acc["bufferView"]]["byteOffset"] + 16 * 4 * 5 + 13 * 4
        bad = base[:off] + struct.pack("<f", 0.5) + base[off + 4 :]
        _, r = rep_bytes(bad)
        self.assertEqual(failed(r, "finalverse.humanoid/v1"), ["E0-10"])
        self.assertIn("FVA-SKN-009", codes(r))

    def test_ec_rule_mutations(self):
        base = M8[0].read_bytes()
        cases = {
            "EC-04": lambda d: d["scenes"][0].__setitem__("name", "x"),
            "EC-05": lambda d: d.__setitem__("extras", {"uri": "x"}),
            "EC-08": lambda d: d["materials"][0].__setitem__("alphaMode", "BLEND"),
            "EC-09": lambda d: d["materials"][0]["pbrMetallicRoughness"].__setitem__("metallicFactor", 2),
            "EC-10": lambda d: d["meshes"][0]["primitives"][0].__setitem__("mode", 5),
            "EC-11": lambda d: d["meshes"][0]["primitives"][0]["attributes"].__setitem__("COLOR_0", 0),
        }
        for rule, fn in cases.items():
            with self.subTest(rule=rule):
                doc = glb_json(base)
                fn(doc)
                _, r = rep_bytes(replace_json(base, doc))
                self.assertEqual(failed(r, "finalverse.ec-static-glb/v1"), [rule])

    def test_ec_flipped_normal_detected(self):
        base = M8[0].read_bytes()
        doc = glb_json(base)
        n = struct.unpack_from("<I", base, 12)[0]
        prim = doc["meshes"][0]["primitives"][0]
        acc = doc["accessors"][prim["attributes"]["NORMAL"]]
        off = 20 + n + 8 + doc["bufferViews"][acc["bufferView"]]["byteOffset"] + acc.get("byteOffset", 0)
        x, y, z = struct.unpack_from("<3f", base, off)
        bad = base[:off] + struct.pack("<3f", -x, -y, -z) + base[off + 12 :]
        _, r = rep_bytes(bad)
        self.assertEqual(failed(r, "finalverse.ec-static-glb/v1"), ["EC-16"])
        self.assertEqual(r["validation"]["status"], "valid")  # still valid glTF: only the EC profile refuses


if __name__ == "__main__":
    unittest.main()
