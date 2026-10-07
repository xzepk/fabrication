"""Fail-closed deterministic provider contract; no generated Python is executed."""
from __future__ import annotations

import math
from .base import GeometryUnsupported
from ..identity import component_identity


DIMENSIONS = {
    "planar_plate": ("width_mm", "height_mm", "thickness_mm"),
    "rect_tube": ("width_mm", "height_mm", "wall_mm", "length_mm"),
}
FEATURES = {"holes", "folds", "bends", "profile", "custom_profile", "slots", "cutouts",
            "flanges", "ribs", "fillets", "chamfers", "beads", "perforations", "notches"}


def capabilities() -> dict:
    return {"build": sorted(DIMENSIONS), "unfold": ["planar_plate"],
            "features": [], "units": ["mm"], "arbitrary_code": False,
            "unsupported_features": sorted(FEATURES), "production_release": False}


def validate_component(component: dict, *, unfold: bool = False) -> dict:
    ident = component_identity(component)
    cid = ident["machine_id"]
    allowed_root = {'id', 'display_label', 'kind', 'quantity', 'geometry', 'material', 'source', 'metadata'} | FEATURES
    unknown_root = set(component) - allowed_root
    if unknown_root:
        raise GeometryUnsupported(f"{cid}: unsupported component fields {sorted(unknown_root)}; place inert annotations in metadata, never geometry requirements")
    g = component.get("geometry")
    if not isinstance(g, dict) or g.get("type") not in DIMENSIONS:
        raise GeometryUnsupported(f"{cid}: supported geometry types are {', '.join(DIMENSIONS)}")
    typ = g["type"]
    if unfold and typ != "planar_plate":
        raise GeometryUnsupported(f"{cid}: builtin unfold only supports planar_plate")
    for name in FEATURES:
        for source in (g, component):
            if name in source and source[name] not in (None, [], {}):
                raise GeometryUnsupported(f"{cid}: {name} requires a validated fabrication adapter; no export written")
    unknown = set(g) - {"type", *DIMENSIONS[typ]} - FEATURES
    if unknown:
        raise GeometryUnsupported(f"{cid}: unsupported geometry fields {sorted(unknown)}; refusing to ignore them")
    for name in DIMENSIONS[typ]:
        value = g.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise GeometryUnsupported(f"{cid}: {name} must be a finite positive number in mm")
    if typ == "rect_tube" and 2 * g["wall_mm"] >= min(g["width_mm"], g["height_mm"]):
        raise GeometryUnsupported(f"{cid}: rect_tube wall must leave an open inner section")
    quantity = component.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise GeometryUnsupported(f"{cid}: quantity must be a positive integer")
    density = component.get("material", {}).get("density_kg_m3")
    if density is not None and (isinstance(density, bool) or not isinstance(density, (int, float)) or
                                not math.isfinite(density) or density <= 0):
        raise GeometryUnsupported(f"{cid}: density_kg_m3 must be finite and positive")
    return ident


def expected_metrics(component: dict) -> dict:
    validate_component(component)
    g = component["geometry"]
    w, h = float(g["width_mm"]), float(g["height_mm"])
    if g["type"] == "planar_plate":
        z = float(g["thickness_mm"])
        return {"volume_mm3": w*h*z, "surface_area_mm2": 2*(w*h+w*z+h*z),
                "bbox_mm": [w, h, z], "bbox_min_mm": [0, 0, 0], "solid_count": 1}
    wall, z = float(g["wall_mm"]), float(g["length_mm"])
    area = w*h - (w-2*wall)*(h-2*wall)
    return {"volume_mm3": area*z, "surface_area_mm2": 2*area + (4*(w+h)-8*wall)*z,
            "cross_section_area_mm2": area, "bbox_mm": [w, h, z],
            "bbox_min_mm": [-w/2, -h/2, 0], "solid_count": 1}
