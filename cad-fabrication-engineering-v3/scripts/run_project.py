#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from importlib import metadata
from pathlib import Path
import csv
import hashlib
import json
import shutil
import sys

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cadfab_v3.model import build_geometry_ir
from cadfab_v3.backends.cadquery_backend import build_step
from cadfab_v3.drawing import engineering_dxf, reference_blank_dxf, engineering_pdf
from cadfab_v3.qa import run_qa


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def render_pdf_previews(pdf: Path, out_dir: Path, dpi: int = 180) -> list[Path]:
    import fitz
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf)
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    outputs = []
    for idx, page in enumerate(doc, 1):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        p = out_dir / f"engineering-sheet-{idx:02d}.png"
        pix.save(p)
        outputs.append(p)
    doc.close()
    return outputs


def validate_ir(ir: dict):
    schema = json.loads((ROOT / "schemas" / "geometry-ir.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(ir), key=lambda e: list(e.path))
    if errors:
        msg = "\n".join(f"IR schema: {'/'.join(map(str,e.path)) or '<root>'}: {e.message}" for e in errors)
        raise ValueError(msg)


def pkg_ver(name: str) -> str | None:
    try:
        return metadata.version(name)
    except Exception:
        return None


def write_bom(ir: dict, out_dir: Path, project: str):
    bom = out_dir / f"{project}_bom.csv"
    with bom.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["panel_id", "type_key", "kind", "bay", "band", "width_mm", "height_mm", "thickness_mm", "net_face_area_m2", "geometry_level"])
        for p in ir["parts"]:
            w.writerow([p["id"], p["type_key"], p["kind"], p["bay"], p["band"], f"{p['width']:.3f}", f"{p['height']:.3f}", f"{p['thickness']:.3f}", f"{p['area_m2']:.6f}", p["geometry_level"]])

    agg = Counter((p["kind"], round(p["width"], 3), round(p["height"], 3), round(p["thickness"], 3)) for p in ir["parts"])
    sched = out_dir / f"{project}_type_schedule.csv"
    with sched.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["type", "kind", "width_mm", "height_mm", "thickness_mm", "qty", "total_net_face_area_m2", "flat_pattern_status"])
        for idx, (k, count) in enumerate(sorted(agg.items()), 1):
            kind, ww, hh, tt = k
            w.writerow([f"T{idx:02d}", kind, f"{ww:.3f}", f"{hh:.3f}", f"{tt:.3f}", count, f"{ww*hh/1e6*count:.6f}", "NOT_RELEASED"])
    return [bom, sched]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: run_project.py <config.yaml> [output_dir]")
    cfgp = Path(sys.argv[1]).resolve()
    cfg = yaml.safe_load(cfgp.read_text(encoding="utf-8"))
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / "outputs" / cfg["project"]
    if out.exists():
        shutil.rmtree(out)
    for d in ["STEP", "DXF", "PDF", "BOM", "QA", "PREVIEW"]:
        (out / d).mkdir(parents=True, exist_ok=True)

    ir = build_geometry_ir(cfg)
    validate_ir(ir)
    (out / "geometry_ir.json").write_text(json.dumps(ir, ensure_ascii=False, indent=2), encoding="utf-8")
    project = cfg["project"]

    step_path = out / "STEP" / f"{project}.step"
    eng_dxf_path = out / "DXF" / f"{project}_engineering.dxf"
    blank_dxf_path = out / "DXF" / f"{project}_reference_blank_layout.dxf"
    pdf_path = out / "PDF" / f"{project}_engineering.pdf"

    step_meta = build_step(ir, step_path)
    dxf_meta = engineering_dxf(ir, eng_dxf_path)
    blank_meta = reference_blank_dxf(ir, blank_dxf_path)
    drawing_meta = engineering_pdf(ir, pdf_path)
    bom_paths = write_bom(ir, out / "BOM", project)
    preview_paths = render_pdf_previews(pdf_path, out / "PREVIEW")

    qa = run_qa(
        ir, step_meta, drawing_meta, dxf_meta, blank_meta,
        pdf_path=pdf_path, eng_dxf_path=eng_dxf_path,
        blank_dxf_path=blank_dxf_path, step_path=step_path,
    )
    qa_path = out / "QA" / f"{project}_qa.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")

    role_map = {
        "geometry_ir.json": "canonical_geometry_ir",
        str(step_path.relative_to(out)): "nominal_brep_step",
        str(eng_dxf_path.relative_to(out)): "engineering_modelspace_dxf",
        str(blank_dxf_path.relative_to(out)): "reference_nominal_face_layout_not_flat_pattern",
        str(pdf_path.relative_to(out)): "controlled_engineering_document",
        str(qa_path.relative_to(out)): "qa_report",
    }
    for p in bom_paths:
        role_map[str(p.relative_to(out))] = "bom_or_type_schedule"
    for p in preview_paths:
        role_map[str(p.relative_to(out))] = "rendered_pdf_review_preview"

    artifacts = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            rel = str(p.relative_to(out))
            artifacts.append({"path": rel, "role": role_map.get(rel, "supporting_artifact"), "sha256": sha(p), "bytes": p.stat().st_size})

    manifest = {
        "project": project,
        "status": ir["status"],
        "skill_version": "3.2.0",
        "ir_version": ir["ir_version"],
        "geometry_level": ir["geometry_level"],
        "backend": "CadQuery/OCP deterministic compatibility backend",
        "preferred_backend": "cadgen/build123d/OCP when installed",
        "runtime_versions": {
            "python": sys.version.split()[0],
            "cadquery": pkg_ver("cadquery"),
            "ezdxf": pkg_ver("ezdxf"),
            "reportlab": pkg_ver("reportlab"),
        },
        "source": ir["source"],
        "source_dimensions": ir["source_dimensions"],
        "release_gates": ir["release_gates"],
        "assumptions": ir["assumptions"],
        "metrics": ir["metrics"],
        "qa_passed": qa["passed"],
        "qa_issues": qa["issues"],
        "qa_warnings": qa["warnings"],
        "artifacts": artifacts,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    if not qa["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
