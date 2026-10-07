"""Shared artifact checks, ASCII identification, and verified planar DXF output."""
from __future__ import annotations

from pathlib import Path
from .base import GeometryUnsupported
from .contract import validate_component
from ..util import write_json


def reserve_outputs(component: dict, out_dir: Path, suffixes: tuple[str, ...]):
    identity = validate_component(component)
    cid = identity["machine_id"]
    # Never overwrite a prior artifact, including on a case-insensitive platform.
    wanted = {f"{cid}{suffix}".casefold() for suffix in (*suffixes, ".identity.json")}
    if out_dir.exists():
        existing = {p.name.casefold() for p in out_dir.iterdir()}
        if wanted & existing:
            raise GeometryUnsupported(f"{cid}: artifact already exists; use a new run directory")
    out_dir.mkdir(parents=True, exist_ok=True)
    return identity, [out_dir / f"{cid}{suffix}" for suffix in suffixes]


def write_identity(out_dir: Path, identity: dict):
    write_json(out_dir / f"{identity['machine_id']}.identity.json", identity)


def unfold_plate(component: dict, out_dir: Path, provider: str) -> dict:
    import ezdxf
    validate_component(component, unfold=True)
    identity, (path,) = reserve_outputs(component, out_dir, ("_flat.dxf",))
    g, cid = component["geometry"], identity["machine_id"]
    w, h = float(g["width_mm"]), float(g["height_mm"])
    try:
        doc = ezdxf.new("R2018")
        doc.units = 4  # millimetres, explicitly present in the DXF header
        doc.layers.new("CUT")
        doc.layers.new("INFO")
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True, dxfattribs={"layer": "CUT"})
        msp.add_text(cid, height=max(3.0, min(w, h)*0.02), dxfattribs={"layer": "INFO"}).set_placement((0, h+10))
        doc.saveas(path)
        reread = ezdxf.readfile(path)
        outlines = list(reread.modelspace().query("LWPOLYLINE[layer=='CUT']"))
        if reread.audit().has_errors or reread.units != 4 or len(outlines) != 1 or not outlines[0].closed:
            raise GeometryUnsupported(f"{cid}: flat DXF readback failed")
        actual = [(x, y) for x, y, *_ in outlines[0].get_points()]
        if actual != [(0, 0), (w, 0), (w, h), (0, h)]:
            raise GeometryUnsupported(f"{cid}: flat DXF readback dimensions differ")
        write_identity(out_dir, identity)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {**identity, "provider": provider, "developable": True, "review_only": True,
            "dxf": str(path), "blank_width_mm": w, "blank_height_mm": h,
            "blank_area_mm2": w*h, "dxf_acceptance": {"ok": True, "units": "mm", "closed_cut_contours": 1}}
