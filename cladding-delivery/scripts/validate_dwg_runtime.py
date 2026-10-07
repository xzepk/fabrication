#!/usr/bin/env python3
"""Exercise an external ACadSharp inspection runtime against supplied DWGs.

This is a fixture inventory and byte-integrity test, never production qualification.
No dependency on another skill or its sample folder is required.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cladding_delivery.cad.acadsharp import inspect_dwg
from cladding_delivery.util import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="DWG file or directory containing DWGs")
    parser.add_argument("--out", required=True, type=Path, help="Fresh output directory")
    args = parser.parse_args()
    source = args.input.resolve()
    files = [source] if source.is_file() else sorted(p for p in source.iterdir() if p.suffix.lower() == ".dwg")
    if not files or any(p.suffix.lower() != ".dwg" for p in files):
        raise SystemExit("input must identify at least one DWG")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    for number, path in enumerate(files, 1):
        original_sha = sha256_file(path)
        try:
            evidence = inspect_dwg(path)
            accepted = (
                evidence.get("success") is True
                and evidence.get("sha256") == original_sha == sha256_file(path)
                and isinstance(evidence.get("entity_count"), int)
                and evidence["entity_count"] > 0
                and evidence.get("canonical_level") == "INSPECTION_ONLY"
                and evidence.get("production_geometry_ready") is False
            )
            (out / f"source-{number:02d}.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            checks.append({"source": path.name, "sha256": original_sha, "passed": accepted,
                           "modelspace_entities": evidence.get("entity_count"),
                           "notification_count": len(evidence.get("notifications", [])),
                           "evidence": f"source-{number:02d}.json"})
        except Exception as error:
            checks.append({"source": path.name, "sha256": original_sha, "passed": False,
                           "error": f"{type(error).__name__}: {error}"})
    report = {"passed": all(c["passed"] for c in checks), "checks": checks,
              "scope": "Real-file parser inventory and unchanged source bytes only",
              "production_geometry_ready": False,
              "production_blockers": ["Block/XRef expansion and transforms not verified",
                                       "Dimension semantics and drawing coverage not verified",
                                       "All parser notifications require engineering review"]}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
