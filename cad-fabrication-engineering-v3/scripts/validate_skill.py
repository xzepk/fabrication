#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import zipfile

import yaml

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
errors = []

skill = root / "SKILL.md"
if not skill.exists():
    errors.append("SKILL.md missing")
else:
    text = skill.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append("SKILL.md front matter missing")
    else:
        try:
            _, fm, _ = text.split("---", 2)
            meta = yaml.safe_load(fm)
            if meta.get("name") != "cad-fabrication-engineering-v3": errors.append("front matter name mismatch")
            if root.name != meta.get("name"): errors.append(f"package root name must equal skill name: root={root.name} skill={meta.get('name')}")
            if meta.get("metadata", {}).get("version") != "3.3.0": errors.append("front matter version mismatch")
            if not meta.get("description"): errors.append("description missing")
            if not meta.get("compatibility"): errors.append("compatibility missing")
        except Exception as exc:
            errors.append(f"front matter parse failed: {exc}")

required = [
    "README.md", "requirements.txt", "schemas/geometry-ir.schema.json",
    "scripts/run_project.py", "scripts/dwg_preflight.py", "scripts/normalize_acadsharp_dump.py", "scripts/golden_regression.py",
    "references/architecture.md", "references/text-to-cad-integration.md",
    "references/cad-quality-standard.md", "references/dwg-adapter-contract.md",
    "references/v3.1-review.md", "references/golden-samples.yaml",
]
for rel in required:
    if not (root / rel).exists(): errors.append(f"missing {rel}")

try:
    json.loads((root / "schemas/geometry-ir.schema.json").read_text(encoding="utf-8"))
except Exception as exc:
    errors.append(f"schema invalid JSON: {exc}")

for p in root.rglob("*.py"):
    try:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except Exception as exc:
        errors.append(f"python syntax error {p.relative_to(root)}: {exc}")

for bad in root.rglob("__pycache__"):
    errors.append(f"package contains __pycache__: {bad.relative_to(root)}")
for ext in ("*.ttf", "*.otf", "*.woff", "*.woff2"):
    for bad in root.rglob(ext):
        errors.append(f"font file must not be bundled: {bad.relative_to(root)}")

if errors:
    print("skill validation: FAIL")
    for e in errors: print("-", e)
    raise SystemExit(2)
print("skill validation: PASS")
