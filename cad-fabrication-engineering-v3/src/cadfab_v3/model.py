from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
from typing import Any


@dataclass(frozen=True)
class Panel:
    id: str
    type_key: str
    kind: str
    bay: int
    band: int | None
    width: float
    height: float
    thickness: float
    x: float
    y: float
    z: float
    orientation: str
    geometry_level: str = "NOMINAL_SKIN"
    qty: int = 1

    @property
    def area_m2(self) -> float:
        return self.width * self.height / 1_000_000.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["area_m2"] = round(self.area_m2, 6)
        return d


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _assumption_dicts(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw or [], 1):
        if isinstance(item, str):
            out.append({
                "id": f"A-{i:03d}",
                "severity": "BLOCKING_FOR_PRODUCTION",
                "statement": item,
                "affects": ["geometry", "drawing", "bom"],
            })
        else:
            out.append({
                "id": item.get("id", f"A-{i:03d}"),
                "severity": item.get("severity", "BLOCKING_FOR_PRODUCTION"),
                "statement": item.get("statement", ""),
                "affects": item.get("affects", ["geometry", "drawing", "bom"]),
            })
    return out


def build_geometry_ir(cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical, engineering-facing Geometry IR.

    v3.2 deliberately separates *plan projection* from a developed/profile chain.
    A horizontal top run plus a vertical fascia drop must never be called an
    "overall depth" merely because their numbers add up.
    """
    g = cfg["geometry"]
    n = int(g["bay_count"])
    pitch = float(g["bay_pitch"])
    depth_bands = [float(v) for v in g.get("top_depth_bands", g.get("depth_bands", []))]
    if not depth_bands:
        raise ValueError("geometry.top_depth_bands (or legacy depth_bands) is required")
    t = float(g["panel_thickness"])
    gap = float(g.get("joint_gap", 0.0))
    margin_left = float(g.get("end_margin_left", g.get("end_margin_each", 0.0)))
    margin_right = float(g.get("end_margin_right", g.get("end_margin_each", 0.0)))
    fascia_h = float(g.get("front_fascia_drop", g.get("front_fascia_height", 0.0)))
    overall_length = float(g["overall_length"])
    top_depth = sum(depth_bands)
    profile_path = float(g.get("profile_path_length_ref", top_depth + fascia_h))

    if pitch <= 0 or n <= 0 or t <= 0:
        raise ValueError("bay_count, bay_pitch and panel_thickness must be positive")
    if gap < 0 or gap >= pitch:
        raise ValueError("joint_gap must be >= 0 and smaller than bay_pitch")
    if any(d <= gap for d in depth_bands):
        raise ValueError("each top depth band must be larger than joint_gap")

    parts: list[Panel] = []
    usable = pitch - gap
    x0 = margin_left + gap / 2.0
    y = 0.0
    # Type keys are stable across runs and intentionally independent of row order.
    for bi, dep in enumerate(depth_bands, 1):
        type_key = f"TP-H{dep-gap:.3f}"
        for bay in range(1, n + 1):
            parts.append(Panel(
                id=f"TP-{bay:02d}-{bi:02d}", type_key=type_key, kind="top_panel",
                bay=bay, band=bi, width=usable, height=dep-gap, thickness=t,
                x=x0 + (bay-1)*pitch, y=y+gap/2.0, z=0.0, orientation="XY",
            ))
        y += dep

    if fascia_h > 0:
        for bay in range(1, n + 1):
            parts.append(Panel(
                id=f"FF-{bay:02d}", type_key=f"FF-H{fascia_h-gap:.3f}", kind="front_fascia",
                bay=bay, band=None, width=usable, height=fascia_h-gap,
                thickness=t, x=x0 + (bay-1)*pitch, y=top_depth,
                z=-fascia_h, orientation="XZ",
            ))

    material = cfg.get("material", {})
    density = float(material.get("density_kg_m3", 2730))
    net_area = sum(p.area_m2 for p in parts)
    net_mass = net_area * (t/1000.0) * density

    assumptions = _assumption_dicts(cfg.get("assumptions", []))
    release = cfg.get("release_gates", {})
    source_dims = cfg.get("source_dimensions", [])
    if not source_dims:
        source_dims = [
            {"id": "SD-L-001", "value_mm": overall_length, "semantic": "overall_setout_length", "confidence": "RECOVERED"},
            {"id": "SD-L-002", "value_mm": pitch, "semantic": "bay_pitch", "repeat": n, "confidence": "RECOVERED"},
            {"id": "SD-P-001", "segments_mm": depth_bands + ([fascia_h] if fascia_h else []),
             "value_mm": profile_path, "semantic": "developed_cladding_profile_chain", "confidence": "INFERRED"},
        ]

    normalized_geometry = {
        "overall_length": overall_length,
        "bay_count": n,
        "bay_pitch": pitch,
        "end_margin_left": margin_left,
        "end_margin_right": margin_right,
        "top_depth_bands": depth_bands,
        "top_projection_depth": top_depth,
        "front_fascia_drop": fascia_h,
        "profile_path_length_ref": profile_path,
        "panel_thickness": t,
        "joint_gap": gap,
        "joint_strategy": g.get("joint_strategy", "CENTERED_REFERENCE"),
    }

    return {
        "ir_version": "1.1",
        "project": cfg["project"],
        "status": cfg["status"],
        "units": cfg.get("units", "mm"),
        "source": cfg.get("source", {}),
        "source_dimensions": source_dims,
        "release_gates": release,
        "geometry_level": cfg.get("geometry_level", "NOMINAL_SKIN"),
        "geometry": normalized_geometry,
        "material": material,
        "fabrication": cfg.get("fabrication", {}),
        "assumptions": assumptions,
        "parts": [p.to_dict() for p in parts],
        "metrics": {
            "panel_count": len(parts),
            "net_visible_sheet_area_m2": round(net_area, 3),
            "estimated_net_sheet_mass_kg": round(net_mass, 1),
            "blank_area_m2": None,
            "purchase_area_m2": None,
            "flat_pattern_released": False,
        },
    }
