"""Read exported STEP geometry back; never accept a provider's reported metrics alone."""
from __future__ import annotations

import math
from pathlib import Path
from .base import GeometryUnsupported
from .contract import expected_metrics
from ..util import sha256_file


def inspect_step(path: Path, component: dict) -> dict:
    import cadquery as cq
    from OCP.BRepCheck import BRepCheck_Analyzer
    expected = expected_metrics(component)
    if not path.is_file() or path.stat().st_size == 0:
        raise GeometryUnsupported(f"STEP acceptance failed: missing/empty artifact {path.name}")
    try:
        shape = cq.importers.importStep(str(path)).val()
        box = shape.BoundingBox()
        solids = shape.Solids()
        actual = {"volume_mm3": shape.Volume(), "surface_area_mm2": shape.Area(),
                  "bbox_mm": [box.xlen, box.ylen, box.zlen],
                  "bbox_min_mm": [box.xmin, box.ymin, box.zmin],
                  "solid_count": len(solids)}
        problems = []
        if not BRepCheck_Analyzer(shape.wrapped).IsValid():
            problems.append("invalid BRep")
        if len(solids) != 1 or not all(s.Shells() and all(shell.Closed() for shell in s.Shells()) for s in solids):
            problems.append("expected exactly one closed solid")
        for key in ("volume_mm3", "surface_area_mm2"):
            if not math.isclose(actual[key], expected[key], rel_tol=1e-7, abs_tol=1e-5):
                problems.append(f"{key}: expected {expected[key]}, read {actual[key]}")
        for key in ("bbox_mm", "bbox_min_mm"):
            if any(not math.isclose(a, e, rel_tol=1e-8, abs_tol=1e-5)
                   for a, e in zip(actual[key], expected[key])):
                problems.append(f"{key}: expected {expected[key]}, read {actual[key]}")
        # A section check catches a plugged/open section independently of volume.
        g = component["geometry"]
        if g["type"] == "rect_tube":
            p = (0, 0, float(g["length_mm"])/2)
            wall_point = (float(g["width_mm"])/2-float(g["wall_mm"])/2, 0, p[2])
            if any(s.isInside(p, 1e-7) for s in solids):
                problems.append("tube center should be void")
            if not any(s.isInside(wall_point, 1e-7) for s in solids):
                problems.append("tube wall probe should be solid")
        if problems:
            raise GeometryUnsupported("STEP acceptance failed: " + "; ".join(problems))
        metrics = dict(actual)
        if "cross_section_area_mm2" in expected:
            metrics["cross_section_area_mm2"] = actual["volume_mm3"] / float(component["geometry"]["length_mm"])
        return {"ok": True, "method": "STEP readback: BRep validity, closed solid, measured mass/bounds, tube probes",
                "sha256": sha256_file(path), "expected": expected, "measured": metrics,
                "length_absolute_tolerance_mm": 1e-5, "mass_relative_tolerance": 1e-7}
    except GeometryUnsupported:
        raise
    except Exception as exc:
        raise GeometryUnsupported(f"STEP acceptance failed: {type(exc).__name__}: {exc}") from exc
