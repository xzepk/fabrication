from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _pdf_preflight(path: Path, expected_panel_ids: set[str], expected_pages: int) -> dict[str, Any]:
    import fitz
    doc = fitz.open(path)
    out: dict[str, Any] = {
        "page_count": len(doc),
        "page_count_expected": expected_pages,
        "all_text_inside_page": True,
        "status_on_every_page": True,
        "panel_ids_found": 0,
        "panel_id_coverage": 0.0,
        "minimum_text_size_pt": None,
    }
    found_ids: set[str] = set()
    min_size = None
    for page in doc:
        page_text = page.get_text("text")
        if "REFERENCE_VALIDATION" not in page_text and "PRELIMINARY" not in page_text and "PRODUCTION_CANDIDATE" not in page_text and "SURVEY_PENDING" not in page_text:
            out["status_on_every_page"] = False
        found_ids.update(re.findall(r"\b(?:TP-\d{2}-\d{2}|FF-\d{2})\b", page_text))
        raw = page.get_text("dict")
        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = float(span.get("size", 0))
                    if size > 0:
                        min_size = size if min_size is None else min(min_size, size)
                    x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                    # allow tiny renderer tolerance at frame edges.
                    if x0 < -0.5 or y0 < -0.5 or x1 > page.rect.width + 0.5 or y1 > page.rect.height + 0.5:
                        out["all_text_inside_page"] = False
    out["panel_ids_found"] = len(found_ids & expected_panel_ids)
    out["panel_id_coverage"] = round(out["panel_ids_found"] / max(len(expected_panel_ids), 1), 6)
    out["minimum_text_size_pt"] = round(min_size, 3) if min_size is not None else None
    doc.close()
    return out


def _dxf_preflight(path: Path, required_layers: set[str]) -> dict[str, Any]:
    import ezdxf
    doc = ezdxf.readfile(path)
    audit = doc.audit()
    layers = {layer.dxf.name for layer in doc.layers}
    msp = doc.modelspace()
    counts: dict[str, int] = {}
    for e in msp:
        counts[e.dxftype()] = counts.get(e.dxftype(), 0) + 1
    return {
        "auditor_errors": len(audit.errors),
        "auditor_fixes": len(audit.fixes),
        "required_layers_present": required_layers.issubset(layers),
        "missing_layers": sorted(required_layers - layers),
        "entity_counts": counts,
    }


def _step_preflight(path: Path) -> dict[str, Any]:
    import cadquery as cq
    shape = cq.importers.importStep(str(path))
    vals = shape.vals()
    # importStep normally returns one compound; count all contained solids.
    solid_count = sum(len(v.Solids()) for v in vals)
    valid = all(v.isValid() for v in vals)
    bb = shape.val().BoundingBox()
    return {
        "readback_valid": bool(valid),
        "readback_solid_count": solid_count,
        "readback_bbox_mm": [round(bb.xlen, 6), round(bb.ylen, 6), round(bb.zlen, 6)],
    }


def run_qa(
    ir: dict,
    step_meta: dict,
    drawing_meta: dict,
    dxf_meta: dict,
    blank_meta: dict,
    *,
    pdf_path: Path | None = None,
    eng_dxf_path: Path | None = None,
    blank_dxf_path: Path | None = None,
    step_path: Path | None = None,
) -> dict:
    issues: list[str] = []
    warnings: list[str] = []
    parts = ir["parts"]
    ids = [p["id"] for p in parts]
    expected_ids = set(ids)
    g = ir["geometry"]

    if len(ids) != len(set(ids)):
        issues.append("duplicate_panel_ids")
    if any(float(p["width"]) <= 0 or float(p["height"]) <= 0 or float(p["thickness"]) <= 0 for p in parts):
        issues.append("non_positive_panel_dimension")
    if not step_meta.get("valid"):
        issues.append("invalid_brep_compound")
    if int(step_meta.get("solid_count", -1)) != len(parts):
        issues.append(f"step_solid_count_mismatch expected={len(parts)} actual={step_meta.get('solid_count')}")

    expected_count = int(g["bay_count"]) * (len(g["top_depth_bands"]) + (1 if float(g["front_fascia_drop"]) > 0 else 0))
    if len(parts) != expected_count:
        issues.append(f"panel_count_mismatch expected={expected_count} actual={len(parts)}")

    # Dimensional closure is explicit and unit-consistent.
    length_closure = float(g["end_margin_left"]) + int(g["bay_count"]) * float(g["bay_pitch"]) + float(g["end_margin_right"])
    length_delta = length_closure - float(g["overall_length"])
    if abs(length_delta) > 0.01:
        issues.append(f"overall_length_closure_delta_mm={length_delta:.6f}")
    profile_sum = sum(float(x) for x in g["top_depth_bands"]) + float(g["front_fascia_drop"])
    profile_delta = profile_sum - float(g["profile_path_length_ref"])
    if abs(profile_delta) > 0.01:
        warnings.append(f"reference_profile_chain_delta_mm={profile_delta:.6f}")

    if abs(float(ir.get("material", {}).get("thickness", g["panel_thickness"])) - float(g["panel_thickness"])) > 1e-6:
        issues.append("material_thickness_differs_from_geometry")

    blocking_assumptions = [a for a in ir.get("assumptions", []) if isinstance(a, dict) and a.get("severity") == "BLOCKING_FOR_PRODUCTION"]
    if blocking_assumptions:
        warnings.append(f"blocking_assumptions_present={len(blocking_assumptions)}")

    release = ir.get("release_gates", {})
    if ir["status"] == "PRODUCTION_CANDIDATE":
        for key in ("gate_a_confirmed", "survey_applied", "production_release_authorized"):
            if not release.get(key, False):
                issues.append(f"production_candidate_missing_gate:{key}")
        if blocking_assumptions:
            issues.append("production_candidate_has_blocking_assumptions")
        if not ir["metrics"].get("flat_pattern_released"):
            issues.append("production_candidate_without_true_flat_pattern")
    else:
        warnings.append("not_production_release_status")

    if drawing_meta.get("view_source") != "OCCT_HLR_FROM_BREP":
        issues.append("engineering_views_not_projected_from_brep")
    coverage = float(drawing_meta.get("panel_mark_coverage", {}).get("ratio", 0))
    if coverage < 1.0:
        issues.append(f"panel_mark_coverage_incomplete={coverage}")
    if drawing_meta.get("flat_pattern_claimed"):
        issues.append("drawing_claims_flat_pattern_without_release")
    if not blank_meta.get("reference_only", False):
        issues.append("nominal_blank_layout_missing_reference_only_flag")

    checks: dict[str, Any] = {
        "step_valid": bool(step_meta.get("valid")),
        "step_solid_count_equals_panel_count": int(step_meta.get("solid_count", -1)) == len(parts),
        "overall_length_closure_delta_mm": round(length_delta, 6),
        "reference_profile_chain_delta_mm": round(profile_delta, 6),
        "panel_mark_coverage": coverage,
        "engineering_view_source": drawing_meta.get("view_source"),
        "standard_scales": drawing_meta.get("scales"),
        "semantic_layers_used": bool(dxf_meta.get("semantic_layers")),
        "flat_pattern_released": bool(ir["metrics"].get("flat_pattern_released")),
        "geometry_level": ir.get("geometry_level"),
        "manual_final_geometry_edits": False,
    }

    if pdf_path:
        pdf_check = _pdf_preflight(pdf_path, expected_ids, int(drawing_meta.get("sheet_count", 0)))
        checks["pdf_preflight"] = pdf_check
        if pdf_check["page_count"] != pdf_check["page_count_expected"]:
            issues.append("pdf_page_count_mismatch")
        if not pdf_check["all_text_inside_page"]:
            issues.append("pdf_text_outside_page")
        if not pdf_check["status_on_every_page"]:
            issues.append("pdf_status_missing_on_page")
        if pdf_check["panel_id_coverage"] < 1.0:
            issues.append(f"pdf_panel_id_coverage_incomplete={pdf_check['panel_id_coverage']}")
        if pdf_check["minimum_text_size_pt"] is not None and pdf_check["minimum_text_size_pt"] < 4.0:
            warnings.append(f"pdf_minimum_text_size_below_4pt={pdf_check['minimum_text_size_pt']}")

    required_layers = {"A-VIEW-VISIBLE", "A-VIEW-HIDDEN", "A-PANEL-JOINT", "A-DIM", "A-TEXT", "A-REF", "A-WARNING"}
    if eng_dxf_path:
        dxf_check = _dxf_preflight(eng_dxf_path, required_layers)
        checks["engineering_dxf_preflight"] = dxf_check
        if dxf_check["auditor_errors"]:
            issues.append(f"engineering_dxf_audit_errors={dxf_check['auditor_errors']}")
        if not dxf_check["required_layers_present"]:
            issues.append("engineering_dxf_missing_required_layers")
    if blank_dxf_path:
        blank_check = _dxf_preflight(blank_dxf_path, {"A-PANEL-CUT", "A-WARNING"})
        checks["reference_blank_dxf_preflight"] = blank_check
        if blank_check["auditor_errors"]:
            issues.append(f"reference_blank_dxf_audit_errors={blank_check['auditor_errors']}")

    if step_path:
        step_readback = _step_preflight(step_path)
        checks["step_readback"] = step_readback
        if not step_readback["readback_valid"]:
            issues.append("step_readback_invalid")
        if step_readback["readback_solid_count"] != len(parts):
            issues.append(f"step_readback_solid_count_mismatch={step_readback['readback_solid_count']}")

    return {
        "passed": not issues,
        "issues": issues,
        "warnings": warnings,
        "checks": checks,
        "step": step_meta,
        "drawing": drawing_meta,
        "engineering_dxf": dxf_meta,
        "reference_blank": blank_meta,
    }
