#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
import argparse
from importlib import metadata
from pathlib import Path
import csv
import hashlib
import json
import math
import sys

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cadfab_v3.model import build_geometry_ir
from cadfab_v3 import __version__
from cadfab_v3.backends.provider import build_step, select_backend, validate_capabilities, BackendError
from cadfab_v3.drawing import engineering_dxf, reference_blank_dxf, engineering_pdf
from cadfab_v3.qa import run_qa
from cadfab_v3.labels import stable_display_id, portable_file_stem


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
        w.writerow(["panel_id", "display_id", "type_key", "kind", "bay", "band", "width_mm", "height_mm", "thickness_mm", "net_face_area_m2", "geometry_level"])
        for p in ir["parts"]:
            w.writerow([p["id"], stable_display_id(p["id"]), p["type_key"], p["kind"], p["bay"], p["band"], f"{p['width']:.3f}", f"{p['height']:.3f}", f"{p['thickness']:.3f}", f"{p['area_m2']:.6f}", p["geometry_level"]])

    agg = Counter((p["kind"], round(p["width"], 3), round(p["height"], 3), round(p["thickness"], 3)) for p in ir["parts"])
    sched = out_dir / f"{project}_type_schedule.csv"
    with sched.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["type", "kind", "width_mm", "height_mm", "thickness_mm", "qty", "total_net_face_area_m2", "flat_pattern_status"])
        for idx, (k, count) in enumerate(sorted(agg.items()), 1):
            kind, ww, hh, tt = k
            w.writerow([f"T{idx:02d}", kind, f"{ww:.3f}", f"{hh:.3f}", f"{tt:.3f}", count, f"{ww*hh/1e6*count:.6f}", "NOT_RELEASED"])
    return [bom, sched]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate reference CAD artifacts without overwriting inputs or prior outputs")
    ap.add_argument("config", type=Path)
    ap.add_argument("output_dir", nargs="?", type=Path)
    ap.add_argument("--backend", choices=("cadquery", "build123d", "cadgen", "auto"))
    ap.add_argument("--runtime-python", help="Python executable of an externally installed build123d/cadgen runtime")
    ap.add_argument("--runtime-timeout", type=float, default=180)
    args = ap.parse_args(argv)
    cfgp = args.config.resolve(strict=True)
    config_bytes = cfgp.read_bytes()
    cfg = yaml.safe_load(config_bytes.decode("utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError("Project configuration must be a mapping")
    def check_finite(value, trail="config"):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Non-finite number at {trail}")
        if isinstance(value, dict):
            for key, child in value.items():
                check_finite(child, f"{trail}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                check_finite(child, f"{trail}[{index}]")
    check_finite(cfg)
    project = cfg.get("project")
    if not isinstance(project, str) or not project.strip() or project in {".", ".."} or any(c in project for c in "/\\\r\n\x00"):
        raise ValueError("project must be a safe single filename component")
    artifact_stem = portable_file_stem(project)
    out = args.output_dir.absolute() if args.output_dir else ROOT / "outputs" / artifact_stem
    # Never clean, merge or replace an earlier run; even a symlink to a missing directory is refused.
    if out.exists() or out.is_symlink():
        raise ValueError(f"Output already exists; choose a new run directory: {out}")
    if not math.isfinite(args.runtime_timeout) or args.runtime_timeout <= 0:
        raise ValueError("runtime timeout must be positive")
    runtime = cfg.get("cad_runtime", {})
    if not isinstance(runtime, dict) or set(runtime) - {"backend", "python", "requirements"}:
        raise ValueError("cad_runtime allows only backend, python and requirements")
    requirements = runtime.get("requirements", [])
    if not isinstance(requirements, list) or any(not isinstance(v, str) for v in requirements):
        raise ValueError("cad_runtime.requirements must be a list of capability names")
    allowed_geometry = {"overall_length", "bay_count", "bay_pitch", "end_margin_left", "end_margin_right", "end_margin_each", "top_depth_bands", "depth_bands", "front_fascia_drop", "front_fascia_height", "profile_path_length_ref", "panel_thickness", "joint_gap", "joint_strategy"}
    extra_geometry = set(cfg.get("geometry", {})) - allowed_geometry
    if extra_geometry:
        raise BackendError(f"Unimplemented geometry fields cannot be ignored: {sorted(extra_geometry)}")
    selection = select_backend(args.backend or runtime.get("backend", "cadquery"), args.runtime_python or runtime.get("python"))
    ir = build_geometry_ir(cfg)
    if "display_labels" in cfg:
        if not isinstance(cfg["display_labels"], dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in cfg["display_labels"].items()):
            raise ValueError("display_labels must map raw text to reviewed English/pinyin labels")
        ir["display_labels"] = dict(cfg["display_labels"])
    validate_ir(ir)
    validate_capabilities(ir, requirements)
    out.mkdir(parents=True, exist_ok=False)
    for directory in ["STEP", "DXF", "PDF", "BOM", "QA", "PREVIEW", "INPUTS"]:
        (out / directory).mkdir()
    (out / "INPUTS" / "config.yaml").write_bytes(config_bytes)
    (out / "geometry_ir.json").write_text(json.dumps(ir, ensure_ascii=False, indent=2), encoding="utf-8")
    project = cfg["project"]

    step_path = out / "STEP" / f"{artifact_stem}.step"
    eng_dxf_path = out / "DXF" / f"{artifact_stem}_engineering.dxf"
    blank_dxf_path = out / "DXF" / f"{artifact_stem}_reference_blank_layout.dxf"
    pdf_path = out / "PDF" / f"{artifact_stem}_engineering.pdf"

    step_meta = build_step(ir, step_path, selection=selection, requirements=requirements, timeout=args.runtime_timeout)
    import cadquery as cq
    saved_shape = cq.importers.importStep(str(step_path)).val()
    dxf_meta = engineering_dxf(ir, eng_dxf_path, shape=saved_shape)
    blank_meta = reference_blank_dxf(ir, blank_dxf_path)
    drawing_meta = engineering_pdf(ir, pdf_path, shape=saved_shape)
    for drawing in (drawing_meta, dxf_meta):
        drawing["model_input"] = "saved_step_readback"
        drawing["model_input_sha256"] = sha(step_path)
        drawing["geometry_provider"] = selection.selected
    bom_paths = write_bom(ir, out / "BOM", artifact_stem)
    preview_paths = render_pdf_previews(pdf_path, out / "PREVIEW")

    qa = run_qa(
        ir, step_meta, drawing_meta, dxf_meta, blank_meta,
        pdf_path=pdf_path, eng_dxf_path=eng_dxf_path,
        blank_dxf_path=blank_dxf_path, step_path=step_path,
    )
    qa_path = out / "QA" / f"{artifact_stem}_qa.json"
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
        "artifact_stem": artifact_stem,
        "status": ir["status"],
        "skill_version": __version__,
        "build_status": "LOCAL_REVIEW_BUILD",
        "ir_version": ir["ir_version"],
        "geometry_level": ir["geometry_level"],
        "backend": selection.selected,
        "backend_provenance": step_meta["provider"],
        "step_verification": step_meta,
        "drawing_backend": "CadQuery/OCP STEP readback + OCCT HLR / ReportLab + PyMuPDF / ezdxf",
        "production_qualified": False,
        "capabilities": ["nominal_rectangular_panels", "orthographic_views", "reference_layout"],
        "unsupported_capabilities": ["sections", "node_details", "curved_panels", "true_flat_patterns", "production_release"],
        "inputs": {"config_path": str(cfgp), "config_sha256": hashlib.sha256(config_bytes).hexdigest(), "config_snapshot": "INPUTS/config.yaml", "geometry_ir_sha256": sha(out / "geometry_ir.json")},
        "runtime_versions": {
            "python": sys.version.split()[0],
            "cadquery": pkg_ver("cadquery"),
            "ezdxf": pkg_ver("ezdxf"),
            "reportlab": pkg_ver("reportlab"),
            "pymupdf": pkg_ver("PyMuPDF"),
            "fonttools": pkg_ver("fontTools"),
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
    if cfgp.read_bytes() != config_bytes:
        raise BackendError("Input configuration changed during generation; result is not accepted")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    if not qa["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
