"""Stable report generation, schema conformance, CLI behaviour, isolation and visual evidence."""

from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import CATALOGUE, FIXTURES, ROOT, TS, cli, codes, digest, dumps, rep_bytes, rep_path

SCHEMA = json.loads((ROOT / "schema" / "finalverse.asset-intelligence.v1.schema.json").read_text())
ALL = sorted(p.name for p in FIXTURES.iterdir() if p.suffix in (".glb", ".gltf"))


class Determinism(unittest.TestCase):
    def test_same_input_same_bytes(self):
        for name in ALL:
            with self.subTest(name=name):
                a = dumps(rep_path(FIXTURES / name)[1])
                b = dumps(rep_path(FIXTURES / name)[1])
                self.assertEqual(a, b)

    def test_digest_ignores_timestamp_only(self):
        _, a = rep_path(FIXTURES / "defective_creature.glb")
        from helpers import inspect_path, report

        b = report(inspect_path(FIXTURES / "defective_creature.glb"), generated_at="2030-01-01T00:00:00Z")
        self.assertNotEqual(a["generated_at"], b["generated_at"])
        self.assertEqual(a["report_digest"], b["report_digest"])
        self.assertEqual(a["report_digest"], digest(a))

    def test_report_does_not_mutate_model(self):
        m, a = rep_path(
            FIXTURES / "humanoid_walker.glb", embodiment_profile="floating_spirit", target="finalverse.ec-static-glb/v1"
        )
        from helpers import report

        b = report(m, generated_at=TS, embodiment_profile="floating_spirit", target="finalverse.ec-static-glb/v1")
        self.assertEqual(a, b)
        self.assertFalse(any(f.code.startswith(("FVA-EMB", "FVA-CMP")) for f in m.findings.all()))

    def test_findings_sorted_and_ids_unique(self):
        rank = {"critical": 0, "error": 1, "warning": 2, "info": 3}
        _, r = rep_path(FIXTURES / "defective_creature.glb")
        keys = [(rank[f["severity"]], f["code"], f["component"]) for f in r["findings"]]
        self.assertEqual(keys, sorted(keys))
        ids = [f["id"] for f in r["findings"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_cross_process_stability(self):
        """A fresh interpreter (different hash seed) produces the identical report."""
        code = (
            "import sys;sys.path.insert(0,'src');from finalverse_asset_intelligence import *;"
            "from finalverse_asset_intelligence.reporting import dumps;"
            f"print(dumps(report_for_path('fixtures/floating_wisp.glb',generated_at='{TS}')),end='')"
        )
        outs = {
            subprocess.run(
                [sys.executable, "-c", code],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONHASHSEED": seed},
                check=True,
            ).stdout
            for seed in ("1", "2", "3")
        }
        self.assertEqual(len(outs), 1)
        self.assertEqual(outs.pop(), dumps(rep_path(FIXTURES / "floating_wisp.glb")[1]))


class Schema(unittest.TestCase):
    def test_reports_conform_to_json_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed (optional dev dependency)")
        v = jsonschema.Draft202012Validator(SCHEMA)
        for name in ALL:
            for kw in ({}, {"embodiment_profile": "fire_elemental", "target": "finalverse.humanoid/v1"}):
                with self.subTest(name=name, kw=kw):
                    errs = sorted(v.iter_errors(rep_path(FIXTURES / name, **kw)[1]), key=str)
                    self.assertEqual(errs, [])
        _, r = rep_bytes(b"garbage")
        self.assertEqual(sorted(v.iter_errors(r), key=str), [])

    def test_schema_lists_every_code(self):
        self.assertEqual(sorted(SCHEMA["$defs"]["finding"]["properties"]["code"]["enum"]), sorted(CATALOGUE))

    def test_catalogue_codes_are_stable_format(self):
        for code in CATALOGUE:
            self.assertRegex(code, r"^FVA-[A-Z]{3}-\d{3}$")


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(list(args))
        return rc, buf.getvalue()

    def test_exit_codes(self):
        self.assertEqual(self.run_cli("validate", str(FIXTURES / "humanoid_walker.glb"))[0], 0)
        self.assertEqual(self.run_cli("validate", str(FIXTURES / "defective_creature.glb"))[0], 1)
        self.assertEqual(
            self.run_cli("validate", str(FIXTURES / "static_prop.glb"), "--target", "finalverse.humanoid/v1")[0], 5
        )
        with tempfile.TemporaryDirectory() as td:
            b = Path(td) / "b.json"
            b.write_text(json.dumps({"name": "tiny", "max_triangles": 1}))
            self.assertEqual(self.run_cli("validate", str(FIXTURES / "static_prop.glb"), "--budget", str(b))[0], 4)
            lim = Path(td) / "l.json"
            lim.write_text(json.dumps({"max_file_bytes": 100}))
            self.assertEqual(self.run_cli("validate", str(FIXTURES / "static_prop.glb"), "--limits", str(lim))[0], 3)
            bad = Path(td) / "bad.json"
            bad.write_text(json.dumps({"max_trianglez": 1}))
            self.assertEqual(self.run_cli("validate", str(FIXTURES / "static_prop.glb"), "--budget", str(bad))[0], 2)
        self.assertEqual(self.run_cli("validate", "/nonexistent.glb")[0], 2)

    def test_report_json_and_out(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "r.json"
            rc, text = self.run_cli(
                "report", str(FIXTURES / "floating_wisp.glb"), "--json", "--out", str(out), "--timestamp", TS
            )
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(text), json.loads(out.read_text()))
            self.assertEqual(json.loads(text)["schema"], "finalverse.asset-intelligence/v1")

    def test_inspect_and_listing_commands(self):
        rc, text = self.run_cli("inspect", str(FIXTURES / "humanoid_walker.glb"))
        self.assertEqual(rc, 0)
        self.assertIn("joints=26", text)
        rc, text = self.run_cli("inspect", str(FIXTURES / "humanoid_walker.glb"), "--json")
        self.assertIn("inspection", json.loads(text))
        self.assertIn("floating_spirit", self.run_cli("profiles")[1])
        self.assertIn("FVA-GEO-003", self.run_cli("codes")[1])

    def test_console_entry_module(self):
        p = subprocess.run(
            [
                sys.executable,
                "-m",
                "finalverse_asset_intelligence",
                "validate",
                str(FIXTURES / "defective_creature.glb"),
                "--json",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        )
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["validation"]["status"], "invalid")


class Isolation(unittest.TestCase):
    def test_no_network_access(self):
        real = socket.socket

        class Forbidden(socket.socket):
            def __init__(self, *a, **k):
                raise AssertionError("network access attempted")

        socket.socket = Forbidden
        try:
            for name in ALL:
                rep_path(FIXTURES / name)
        finally:
            socket.socket = real

    def test_no_blender_dependency(self):
        code = (
            "import sys\nclass Block:\n  def find_spec(self, n, *a):\n"
            "    if n.split('.')[0] in ('bpy','bmesh','mathutils','numpy'): raise ImportError('blocked '+n)\n"
            "sys.meta_path.insert(0, Block())\nsys.path.insert(0,'src')\n"
            "from finalverse_asset_intelligence import report_for_path\n"
            "r=report_for_path('fixtures/humanoid_walker.glb')\nprint(r['validation']['status'])\n"
        )
        p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "valid")
        for f in (ROOT / "src").rglob("*.py"):
            text = f.read_text()
            self.assertNotIn("import bpy", text, f)

    def test_input_files_are_not_modified(self):
        before = {n: hashlib.sha256((FIXTURES / n).read_bytes()).hexdigest() for n in os.listdir(FIXTURES)}
        for name in ALL:
            rep_path(FIXTURES / name)
        after = {n: hashlib.sha256((FIXTURES / n).read_bytes()).hexdigest() for n in os.listdir(FIXTURES)}
        self.assertEqual(before, after)


class VisualEvidence(unittest.TestCase):
    def write(
        self, td: Path, asset: Path, renders: int, humans: int, score: float, style="stylized", corrupt=False
    ) -> Path:
        from gltf_builder import png

        sha = hashlib.sha256(asset.read_bytes()).hexdigest()
        rs = []
        for i in range(renders):
            data = png(32, 32, (i * 20 % 255, 100, 150, 255))
            (td / f"r{i}.png").write_bytes(data)
            rs.append(
                {
                    "path": f"r{i}.png",
                    "sha256": hashlib.sha256(data).hexdigest() if not corrupt else "0" * 64,
                    "view": f"view{i}",
                    "renderer": "test",
                }
            )
        digests = [r["sha256"] for r in rs]
        assess = [
            {
                "assessor": f"human:reviewer{i}" if i < humans else f"model:test{i}",
                "kind": "human" if i < humans else "model",
                "visual_reference_alignment": score,
                "artistic_coherence": score,
                "renders": digests,
            }
            for i in range(max(1, humans))
        ]
        p = td / "evidence.json"
        p.write_text(
            json.dumps(
                {
                    "schema": "finalverse.visual-evidence/v0",
                    "asset_sha256": sha,
                    "style": style,
                    "renders": rs,
                    "assessments": assess,
                }
            )
        )
        return p

    def test_q2_requires_and_accepts_verified_evidence(self):
        asset = FIXTURES / "static_prop.glb"
        with tempfile.TemporaryDirectory() as td:
            ev = self.write(Path(td), asset, renders=2, humans=0, score=0.7)
            _, r = rep_path(asset, visual_evidence=ev)
        t = r["quality"]["tier"]
        self.assertEqual((t["certified"], t["visual_evidence"]), ("Q2", "verified"))
        self.assertEqual(r["quality"]["categories"]["artistic_coherence"]["score"], 0.7)
        self.assertIn(">= 4 verified renders", t["next_tier_blockers"])

    def test_q3_requires_a_human_and_textures(self):
        asset = FIXTURES / "static_prop.glb"
        with tempfile.TemporaryDirectory() as td:
            ev = self.write(Path(td), asset, renders=4, humans=0, score=0.95)
            _, r = rep_path(asset, visual_evidence=ev)
        self.assertEqual(r["quality"]["tier"]["certified"], "Q2")
        self.assertIn(">= 1 human assessment", r["quality"]["tier"]["next_tier_blockers"])
        self.assertIn("textured materials", r["quality"]["tier"]["next_tier_blockers"])

    def test_tampered_evidence_rejected(self):
        asset = FIXTURES / "static_prop.glb"
        with tempfile.TemporaryDirectory() as td:
            ev = self.write(Path(td), asset, renders=3, humans=1, score=0.9, corrupt=True)
            _, r = rep_path(asset, visual_evidence=ev)
        self.assertIn("FVA-QLT-001", codes(r))
        self.assertEqual(r["quality"]["tier"]["certified"], "Q1")
        self.assertEqual(r["quality"]["categories"]["visual_reference_alignment"]["status"], "not_assessed")

    def test_evidence_for_another_asset_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ev = self.write(Path(td), FIXTURES / "floating_wisp.glb", renders=2, humans=1, score=0.9)
            _, r = rep_path(FIXTURES / "static_prop.glb", visual_evidence=ev)
        self.assertIn("FVA-QLT-001", codes(r))

    def test_subjective_scores_never_inferred(self):
        for name in ALL:
            _, r = rep_path(FIXTURES / name)
            for k in ("visual_reference_alignment", "artistic_coherence"):
                self.assertIsNone(r["quality"]["categories"][k]["score"])
            self.assertIn(r["quality"]["tier"]["certified"], (None, "Q0", "Q1"))


class GoldenEvidence(unittest.TestCase):
    def test_acceptance_evidence_reproduces_exactly(self):
        p = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "acceptance.py"), "--check"], capture_output=True, text=True
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_schema_and_fixtures_not_stale(self):
        for tool in ("write_schema.py", "build_fixtures.py"):
            p = subprocess.run([sys.executable, str(ROOT / "tools" / tool), "--check"], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
