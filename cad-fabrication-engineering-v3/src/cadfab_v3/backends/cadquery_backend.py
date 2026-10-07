from __future__ import annotations
from pathlib import Path
import cadquery as cq
from cadquery import exporters


def build_shape(ir: dict) -> cq.Compound:
    shapes = []
    for p in ir["parts"]:
        w, h, t = float(p["width"]), float(p["height"]), float(p["thickness"])
        if p["orientation"] == "XY":
            wp = cq.Workplane("XY").box(w, h, t, centered=(False, False, False)).translate((p["x"], p["y"], p["z"]))
        elif p["orientation"] == "XZ":
            # width X, thickness Y, height Z; nominal skin only, not a bent tray.
            wp = cq.Workplane("XY").box(w, t, h, centered=(False, False, False)).translate((p["x"], p["y"], p["z"]))
        else:
            raise ValueError(f"unsupported orientation: {p['orientation']}")
        shapes.append(wp.val())
    return cq.Compound.makeCompound(shapes)


def build_step(ir: dict, out: Path) -> dict:
    comp = build_shape(ir)
    out.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(comp, str(out), exportType="STEP")
    bb = comp.BoundingBox()
    solids = comp.Solids()
    invalid = [i for i, s in enumerate(solids, 1) if not s.isValid()]
    return {
        "solid_count": len(solids),
        "bbox_mm": [round(bb.xlen, 6), round(bb.ylen, 6), round(bb.zlen, 6)],
        "valid": bool(comp.isValid()) and not invalid,
        "invalid_solid_indices": invalid,
        "geometry_level": ir.get("geometry_level", "NOMINAL_SKIN"),
    }
