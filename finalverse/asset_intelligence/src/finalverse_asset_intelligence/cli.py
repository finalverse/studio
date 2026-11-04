"""finalverse-asset command-line interface.

Exit codes for ``validate`` (other commands return 0 when they produce output):
  0 valid, 4 valid but exceeds configured limits, 1 invalid glTF,
  3 refused (security policy or incomplete inspection), 5 --target profile refuses,
  2 usage or I/O error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .analyze import load_path
from .embodiment import PROFILES as EMBODIMENT_PROFILES
from .findings import CATALOGUE
from .limits import Limits, RuntimeBudget, load_budget, load_limits
from .profiles import RUNTIME_PROFILES
from .reporting import build, dumps

EXIT = {"valid": 0, "invalid": 1, "refused": 3, "valid_exceeds_limits": 4}


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("asset", type=Path, help=".glb or .gltf file")
    p.add_argument("--budget", type=Path, help="runtime budget JSON (see S3A-ASSET-REPORT-SCHEMA.md)")
    p.add_argument("--limits", type=Path, help="inspection safety limits JSON")
    p.add_argument(
        "--profile",
        action="append",
        choices=sorted(RUNTIME_PROFILES),
        help="runtime profiles to evaluate (default: all)",
    )
    p.add_argument("--target", choices=sorted(RUNTIME_PROFILES), help="runtime profile the asset must satisfy")
    p.add_argument("--embodiment", choices=sorted(EMBODIMENT_PROFILES), help="intended embodiment profile")
    p.add_argument("--visual-evidence", type=Path, help="finalverse.visual-evidence/v0 JSON file")
    p.add_argument(
        "--timestamp", help="fixed generated_at (RFC 3339) for reproducible output; SOURCE_DATE_EPOCH is also honoured"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="finalverse-asset", description="Finalverse asset intelligence (S3-A)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("inspect", help="summarize scene, geometry, materials, skins and animation")
    _common(pi)
    pi.add_argument("--json", action="store_true", help="print the inspection section as JSON")
    pv = sub.add_parser("validate", help="validate and set the exit status")
    _common(pv)
    pv.add_argument("--json", action="store_true", help="print validation and findings as JSON")
    pv.add_argument("--all", action="store_true", help="include info-level findings")
    pr = sub.add_parser("report", help="full finalverse.asset-intelligence/v1 report")
    _common(pr)
    pr.add_argument("--json", action="store_true", help="print the JSON report")
    pr.add_argument("--out", type=Path, help="write the JSON report to this file")
    pr.add_argument("--compact", action="store_true", help="canonical compact JSON")
    pr.add_argument("--no-inspection", action="store_true", help="omit the inspection section")
    sub.add_parser("profiles", help="list runtime and embodiment profiles")
    sub.add_parser("codes", help="list the finding catalogue")
    args = ap.parse_args(argv)

    if args.cmd == "profiles":
        for pid in RUNTIME_PROFILES:
            print(f"runtime     {pid}")
        for pid, p in EMBODIMENT_PROFILES.items():
            print(f"embodiment  {pid:20s} {p['contract_status']}")
        return 0
    if args.cmd == "codes":
        for c in CATALOGUE.values():
            print(f"{c.code}  {c.severity:8s} {c.cls:13s} {c.name}")
        return 0

    try:
        limits = load_limits(args.limits) if args.limits else Limits()
        budget = load_budget(args.budget) if args.budget else RuntimeBudget()
        if not args.asset.is_file():
            raise FileNotFoundError(str(args.asset))
        model = load_path(args.asset, limits, budget)
    except (OSError, ValueError) as e:
        print(f"finalverse-asset: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    rep = build(
        model,
        runtime_profiles=args.profile,
        target=args.target,
        embodiment_profile=args.embodiment,
        visual_evidence=args.visual_evidence,
        generated_at=args.timestamp,
        include_inspection=not getattr(args, "no_inspection", False),
    )
    status = rep["validation"]["status"]

    if args.cmd == "inspect":
        if args.json:
            sys.stdout.write(
                dumps({"asset": rep["asset"], "metrics": rep["metrics"], "inspection": rep.get("inspection")})
            )
        else:
            _print_inspect(rep)
        return 0
    if args.cmd == "validate":
        shown = [f for f in rep["findings"] if args.all or f["severity"] != "info"]
        if args.json:
            sys.stdout.write(dumps({"asset": rep["asset"], "validation": rep["validation"], "findings": shown}))
        else:
            print(f"{rep['asset']['file_name']}: {status}  ({rep['asset']['identity']})")
            for f in shown:
                print(f"  {f['severity']:8s} {f['code']} {f['component']}: {f['message']}")
        code = EXIT[status]
        if code == 0 and args.target and rep["validation"]["target_profile_status"] == "incompatible":
            code = 5
        return code
    # report
    if args.out:
        args.out.write_text(dumps(rep, pretty=not args.compact), encoding="utf-8")
    if args.json:
        sys.stdout.write(dumps(rep, pretty=not args.compact))
    elif not args.out:
        _print_report(rep)
    return 0


def _print_inspect(rep: dict) -> None:
    a, mt, ins = rep["asset"], rep["metrics"], rep.get("inspection") or {}
    print(f"{a['file_name']}  {a['media_type']}  {a['byte_length']} bytes  sha256:{a['sha256'][:16]}")
    if not ins.get("container"):
        print("  (not parsed)")
        return
    print(f"  generator   {ins['asset'].get('generator')}")
    print(
        f"  scene       nodes={mt['nodes']} meshes={mt['meshes']} primitives={mt['primitives']} "
        f"vertices={mt['vertices']} triangles={mt['triangles']}"
    )
    print(
        f"  materials   {mt['materials']}  textures={mt['textures']} images={mt['images']} "
        f"max_texture={mt['max_texture_dimension']}"
    )
    print(f"  skins       {mt['skins']}  joints={mt['joints']}  morph_targets={mt['morph_targets']}")
    clips = ", ".join(f"{x['name']}({x['duration']}s)" for x in ins["animations"]["items"])
    print(f"  animations  {mt['animations']}  {clips}")
    print(f"  bounds      {ins['bounds']}")
    print(f"  extensions  used={ins['extensions'].get('used')} required={ins['extensions'].get('required')}")
    print(f"  capabilities {json.dumps(ins['capabilities'], sort_keys=True)}")


def _print_report(rep: dict) -> None:
    v = rep["validation"]
    print(f"{rep['asset']['file_name']}: {v['status']}  findings={v['finding_counts']}")
    for r in rep["compatibility"]["runtime"]:
        fails = [x["rule"] for x in r["rules"] if x["outcome"] == "fail"]
        print(f"  runtime    {r['id']:32s} {r['status']:13s} {' '.join(fails)}".rstrip())
    for e in rep["compatibility"]["embodiment"]:
        print(f"  embodiment {e['profile']:32s} {e['status']:13s} unmet={e.get('recommendations_unmet')}")
    t = rep["quality"]["tier"]
    print(
        f"  quality    certified={t['certified']} ceiling={t['deterministic_ceiling']} "
        f"next={t['next_tier']} blockers={t['next_tier_blockers']}"
    )
    for k, c in rep["quality"]["categories"].items():
        print(f"    {k:28s} {c['score'] if c['score'] is not None else c['status']}")
    for p in rep["proposals"]:
        if p["severity"] != "info":
            print(f"  proposal   [{p['severity']}] {p['component']}: {p['action']}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
