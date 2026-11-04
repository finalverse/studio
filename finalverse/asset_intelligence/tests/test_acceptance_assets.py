"""The three acceptance assets plus the supporting fixtures, executed through the real parser."""

from __future__ import annotations

import unittest

from helpers import FIXTURES, build_fixtures, codes, rep_path


class Reproducible(unittest.TestCase):
    def test_committed_fixtures_are_rebuilt_bit_for_bit(self):
        for name, data in build_fixtures.all_fixtures().items():
            with self.subTest(name=name):
                self.assertEqual((FIXTURES / name).read_bytes(), data)


class AnimatedHumanoid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.r = rep_path(FIXTURES / "humanoid_walker.glb", embodiment_profile="biological_humanoid")

    def test_valid_and_clean(self):
        self.assertEqual(self.r["validation"]["status"], "valid")
        self.assertEqual([f for f in self.r["findings"] if f["severity"] != "info"], [])

    def test_inspection_extracts_rig_and_clips(self):
        mt = self.r["metrics"]
        self.assertEqual((mt["joints"], mt["skins"], mt["animations"], mt["nodes"]), (26, 1, 5, 27))
        caps = self.r["inspection"]["capabilities"]
        self.assertTrue(caps["skinned"] and caps["animated"])
        self.assertEqual(caps["clip_names"], ["greet", "idle", "speak", "turn", "walk"])
        self.assertAlmostEqual(self.r["inspection"]["bounds"]["size"][1], 1.79, places=4)

    def test_embodiment(self):
        emb = {e["profile"]: e for e in self.r["compatibility"]["embodiment"]}
        self.assertEqual(emb["biological_humanoid"]["status"], "compatible")
        self.assertEqual(emb["biological_humanoid"]["recommendations_unmet"], [])
        self.assertEqual(emb["floating_spirit"]["status"], "incompatible")
        self.assertEqual(self.r["quality"]["categories"]["embodiment_compatibility"]["score"], 1.0)

    def test_strict_e0_admission_fails_only_on_generator_identity(self):
        e0 = next(p for p in self.r["compatibility"]["runtime"] if p["id"] == "finalverse.humanoid/v1")
        fails = [r["rule"] for r in e0["rules"] if r["outcome"] == "fail"]
        self.assertEqual(fails, ["E0-06"])
        self.assertTrue(all(r["outcome"] == "pass" for r in e0["rules"][:5]))

    def test_tier_capped_without_visual_evidence(self):
        t = self.r["quality"]["tier"]
        self.assertEqual((t["certified"], t["deterministic_ceiling"], t["visual_evidence"]), ("Q1", "Q1", "absent"))


class FloatingCreature(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.r = rep_path(FIXTURES / "floating_wisp.glb", embodiment_profile="floating_spirit")

    def test_valid_without_any_skeleton(self):
        self.assertEqual(self.r["validation"]["status"], "valid")
        self.assertEqual(self.r["metrics"]["skins"], 0)
        caps = self.r["inspection"]["capabilities"]
        self.assertTrue(caps["morph_targets"] and caps["emissive"] and caps["translucent"])

    def test_distinct_embodiment_handling(self):
        emb = {e["profile"]: e["status"] for e in self.r["compatibility"]["embodiment"]}
        self.assertEqual(
            emb,
            {
                "biological_humanoid": "incompatible",
                "synthetic_humanoid": "incompatible",
                "floating_spirit": "compatible",
                "botanical_sprite": "incompatible",
                "nature_elemental": "incompatible",
                "fire_elemental": "incompatible",
            },
        )
        fs = next(e for e in self.r["compatibility"]["embodiment"] if e["profile"] == "floating_spirit")
        self.assertEqual(fs["recommendations_unmet"], [])
        self.assertFalse(any(f["code"].startswith("FVA-EMB") for f in self.r["findings"]))

    def test_animation_kinds(self):
        a = self.r["inspection"]["animations"]["items"][0]
        self.assertEqual(a["kinds"], ["morph", "node"])
        self.assertTrue(a["loops"])


class DefectiveAsset(unittest.TestCase):
    EXPECTED = {
        "FVA-ANM-001",
        "FVA-ANM-003",
        "FVA-CON-008",
        "FVA-EXT-001",
        "FVA-GEO-003",
        "FVA-GEO-006",
        "FVA-GEO-007",
        "FVA-GEO-013",
        "FVA-MAT-001",
        "FVA-SCN-002",
        "FVA-SEC-001",
        "FVA-SKN-001",
    }

    @classmethod
    def setUpClass(cls):
        cls.m, cls.r = rep_path(FIXTURES / "defective_creature.glb")

    def test_every_planted_defect_detected(self):
        self.assertEqual(codes(self.r) & self.EXPECTED, self.EXPECTED)

    def test_no_unexpected_errors(self):
        errors = {f["code"] for f in self.r["findings"] if f["severity"] in ("critical", "error")}
        self.assertLessEqual(errors, self.EXPECTED)

    def test_status_and_proposals(self):
        self.assertEqual(self.r["validation"]["status"], "invalid")
        self.assertFalse(self.r["validation"]["spec_valid"])
        self.assertIsNone(self.r["quality"]["tier"]["certified"])
        ids = {fid for p in self.r["proposals"] for fid in p["finding_ids"]}
        self.assertEqual(ids, {f["id"] for f in self.r["findings"]})
        for p in self.r["proposals"]:
            self.assertTrue(p["advisory"])
            self.assertFalse(p["modifies_asset"])
            for k in (
                "id",
                "severity",
                "evidence",
                "component",
                "action",
                "expected_impact",
                "confidence",
                "required_validation",
            ):
                self.assertIn(k, p)

    def test_remote_uri_was_not_fetched(self):
        dep = self.r["inspection"]["dependencies"]["items"]
        remote = [d for d in dep if d["uri_class"] == "remote"]
        self.assertEqual(len(remote), 1)
        self.assertEqual(remote[0]["status"], "refused")
        self.assertNotIn("sha256", remote[0])
        self.assertEqual(self.r["provenance"]["network_access"], "none")


class SupportingFixtures(unittest.TestCase):
    def test_static_prop_satisfies_ec_profile(self):
        _, r = rep_path(FIXTURES / "static_prop.glb", target="finalverse.ec-static-glb/v1")
        rt = {p["id"]: p["status"] for p in r["compatibility"]["runtime"]}
        self.assertEqual(rt["finalverse.ec-static-glb/v1"], "compatible")
        self.assertEqual(rt["infinity.entry-glb/observed"], "unverified")
        self.assertEqual(r["validation"]["status"], "valid")

    def test_textured_gltf_resolves_local_dependencies(self):
        _, r = rep_path(FIXTURES / "textured_crate.gltf")
        self.assertEqual(r["validation"]["status"], "valid")
        img = r["inspection"]["images"]["items"][0]
        self.assertEqual((img["media_type"], img["width"], img["height"]), ("image/png", 16, 16))
        self.assertEqual(r["asset"]["media_type"], "model/gltf+json")
        self.assertIn("FVA-DEP-002", codes(r))
        roles = [i["role"] for i in r["provenance"]["inputs"]]
        self.assertEqual(roles, ["asset", "dependency:buffer", "dependency:image"])


if __name__ == "__main__":
    unittest.main()
