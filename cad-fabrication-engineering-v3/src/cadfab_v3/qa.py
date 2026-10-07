from __future__ import annotations

import re
import unicodedata

from .labels import is_ascii_text, stable_display_id
from pathlib import Path
from typing import Any


def _pdf_preflight(path: Path, expected_panel_ids: set[str], expected_pages: int, label_mapping=None) -> dict[str, Any]:
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
        "unicode_fonts_embedded": True,
        "missing_glyph_count": 0,
        "replacement_character_count": 0,
        "rendered_pages": [],
        "label_readback_complete": True,
    }
    found_ids: set[str] = set()
    min_size = None
    text_all = ""
    preview = path.parent / (path.stem + "_qa_preview")
    preview.mkdir(parents=True, exist_ok=True)
    for page_index, page in enumerate(doc):
        page_text = page.get_text("text")
        text_all += "\n" + page_text
        out["replacement_character_count"] += page_text.count("\ufffd")
        fonts = {}
        for row in page.get_fonts():
            xref, extension, typ, basefont, resource = row[:5]
            embedded = bool(doc.extract_font(xref)[3]) if xref else False
            fonts[re.sub(r"[^a-z0-9]", "", basefont.split("+")[-1].lower())] = embedded
        for span in page.get_texttrace():
            chars = span.get("chars", [])
            out["missing_glyph_count"] += sum(1 for ch in chars if ch[1] == 0 and ch[0] != 32)
            if any(ch[0] > 127 for ch in chars):
                trace_name = re.sub(r"[^a-z0-9]", "", span.get("font", "").split("+")[-1].lower())
                if not fonts.get(trace_name, False):
                    out["unicode_fonts_embedded"] = False
        # Rendering is an acceptance step, not inferred from strings in the file.
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        png = preview / f"page-{page_index+1:02d}.png"
        pix.save(png)
        ink = sum(value < 240 for value in pix.samples)
        out["rendered_pages"].append({"path": str(png), "nonwhite_channel_samples": ink,
                                      "width": pix.width, "height": pix.height})
        if "REFERENCE_VALIDATION" not in page_text and "PRELIMINARY" not in page_text and "PRODUCTION_CANDIDATE" not in page_text and "SURVEY_PENDING" not in page_text:
            out["status_on_every_page"] = False
        # Token boundaries prevent FF-01 matching FF-010, and allow mapped IDs.
        for panel_id in expected_panel_ids:
            if re.search(r"(?<![A-Za-z0-9_.-])" + re.escape(panel_id) + r"(?![A-Za-z0-9_.-])", page_text):
                found_ids.add(panel_id)
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
    if label_mapping:
        normalize = lambda text: "".join(unicodedata.normalize("NFKC", text).replace("\u2011", "-").replace("\u2010", "-").split())
        whole = normalize(text_all)
        missing = [row["display_label"] for row in label_mapping.get("labels", [])
                   if row["target"] == "pdf" and normalize(row["display_label"]) not in whole]
        out["labels_missing_from_readback"] = sorted(set(missing))
        out["label_readback_complete"] = not missing
    out["raster_render_passed"] = bool(out["rendered_pages"]) and all(p["nonwhite_channel_samples"] > 100 for p in out["rendered_pages"])
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
    texts = []
    for entity in doc.entitydb.values():
        if entity.is_alive and entity.dxftype() in {"TEXT", "ATTRIB", "ATTDEF"}:
            texts.append(str(entity.dxf.text))
        elif entity.is_alive and entity.dxftype() == "MTEXT":
            texts.append(entity.plain_text())
    nonportable = [value for value in texts if not is_ascii_text(value)]
    render = _render_dxf(path, doc)
    return {
        "ascii_display_text_only": not nonportable,
        "nonportable_text": nonportable,
        "text_entity_count_including_blocks": len(texts),
        "raster_preview": render,
        "auditor_errors": len(audit.errors),
        "auditor_fixes": len(audit.fixes),
        "required_layers_present": required_layers.issubset(layers),
        "missing_layers": sorted(required_layers - layers),
        "entity_counts": counts,
    }


def _render_dxf(path: Path, doc=None) -> dict:
    """Independent DXF reopen -> ezdxf drawing frontend -> MuPDF raster."""
    import fitz
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext, layout, pymupdf
    from ezdxf.addons.drawing.config import Configuration, ColorPolicy, BackgroundPolicy
    doc = doc or ezdxf.readfile(path)
    backend = pymupdf.PyMuPdfBackend()
    config = Configuration(color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE)
    Frontend(RenderContext(doc), backend, config=config).draw_layout(doc.modelspace(), finalize=True)
    pdf_data = backend.get_pdf_bytes(layout.Page(420, 297, margins=layout.Margins.all(10)))
    pdf = path.with_suffix(".rendered.pdf")
    pdf.write_bytes(pdf_data)
    with fitz.open(stream=pdf_data, filetype="pdf") as rendered:
        pix = rendered[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        png = path.with_suffix(".rendered.png")
        pix.save(png)
        ink = sum(value < 240 for value in pix.samples)
    return {"pdf": str(pdf), "png": str(png), "passed": ink > 100,
            "nonwhite_channel_samples": ink, "renderer": "ezdxf+PyMuPDF"}


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
    expected_ids = {stable_display_id(value) for value in ids}
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
        pdf_check = _pdf_preflight(pdf_path, expected_ids, int(drawing_meta.get("sheet_count", 0)), drawing_meta.get("label_mapping"))
        checks["pdf_preflight"] = pdf_check
        for key in ("unicode_fonts_embedded", "raster_render_passed", "label_readback_complete"):
            if not pdf_check[key]: issues.append("pdf_" + key + "_failed")
        if pdf_check["missing_glyph_count"] or pdf_check["replacement_character_count"]:
            issues.append("pdf_missing_or_replacement_glyphs")
        for name, meta in (("pdf", drawing_meta), ("engineering_dxf", dxf_meta), ("blank_dxf", blank_meta)):
            mapping = meta.get("label_mapping", {})
            if mapping.get("untranslated_labels"):
                issues.append(name + "_untranslated_labels_require_display_labels")
            if mapping.get("layout_issues"):
                issues.append(name + "_label_layout_failure")
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
        if not dxf_check["ascii_display_text_only"]: issues.append("engineering_dxf_nonportable_text")
        if not dxf_check["raster_preview"]["passed"]: issues.append("engineering_dxf_render_failure")
        if dxf_check["auditor_errors"]:
            issues.append(f"engineering_dxf_audit_errors={dxf_check['auditor_errors']}")
        if not dxf_check["required_layers_present"]:
            issues.append("engineering_dxf_missing_required_layers")
    if blank_dxf_path:
        blank_check = _dxf_preflight(blank_dxf_path, {"A-PANEL-CUT", "A-WARNING"})
        checks["reference_blank_dxf_preflight"] = blank_check
        if not blank_check["ascii_display_text_only"]: issues.append("reference_blank_dxf_nonportable_text")
        if not blank_check["raster_preview"]["passed"]: issues.append("reference_blank_dxf_render_failure")
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
