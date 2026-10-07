from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from cadquery import Shape
from OCP.BRepLib import BRepLib
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt


@dataclass
class ProjectedView:
    name: str
    visible: list[list[tuple[float, float]]]
    hidden: list[list[tuple[float, float]]]
    bounds: tuple[float, float, float, float]

    @property
    def width(self) -> float:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> float:
        return self.bounds[3] - self.bounds[1]


def _polyline(edge, transform: Callable[[float, float], tuple[float, float]], deflection: float = 0.25):
    curve = edge._geomAdaptor()
    start, end = curve.FirstParameter(), curve.LastParameter()
    pts = GCPnts_QuasiUniformDeflection(curve, deflection, start, end)
    out: list[tuple[float, float]] = []
    if pts.IsDone() and pts.NbPoints() >= 2:
        for i in range(1, pts.NbPoints() + 1):
            p = pts.Value(i)
            out.append(transform(p.X(), p.Y()))
    else:
        for u in (start, end):
            p = curve.Value(u)
            out.append(transform(p.X(), p.Y()))
    return out


def _dedupe(lines: Iterable[list[tuple[float, float]]], ndigits: int = 3):
    seen = set()
    out = []
    for line in lines:
        if len(line) < 2:
            continue
        key = tuple((round(x, ndigits), round(y, ndigits)) for x, y in line)
        rkey = tuple(reversed(key))
        canon = key if key <= rkey else rkey
        if canon in seen:
            continue
        seen.add(canon)
        out.append(line)
    return out


def project_shape(shape, name: str, direction: tuple[float, float, float], transform: Callable[[float, float], tuple[float, float]] | None = None, include_hidden: bool = True) -> ProjectedView:
    """Project a CQ/OCC shape with OCCT HLR and return 2D linework in model mm.

    The returned coordinates are geometric projection coordinates, not page
    pixels. This lets the drawing layer apply a real engineering scale.
    """
    if transform is None:
        transform = lambda x, y: (x, y)

    hlr = HLRBRep_Algo()
    hlr.Add(shape.wrapped)
    hlr.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(), gp_Dir(*direction))))
    hlr.Update()
    hlr.Hide()
    hshape = HLRBRep_HLRToShape(hlr)

    visible_native = []
    for getter in (hshape.VCompound, hshape.Rg1LineVCompound, hshape.OutLineVCompound):
        s = getter()
        if not s.IsNull():
            BRepLib.BuildCurves3d_s(s, 1e-7)
            visible_native.append(Shape(s))

    hidden_native = []
    if include_hidden:
        for getter in (hshape.HCompound, hshape.OutLineHCompound):
            s = getter()
            if not s.IsNull():
                BRepLib.BuildCurves3d_s(s, 1e-7)
                hidden_native.append(Shape(s))

    visible = _dedupe(_polyline(e, transform) for s in visible_native for e in s.Edges())
    hidden = _dedupe(_polyline(e, transform) for s in hidden_native for e in s.Edges())
    all_pts = [p for line in (visible + hidden) for p in line]
    if not all_pts:
        raise ValueError(f"projection {name} returned no linework")
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    bounds = (min(xs), min(ys), max(xs), max(ys))
    return ProjectedView(name=name, visible=visible, hidden=hidden, bounds=bounds)


def standard_views(shape) -> dict[str, ProjectedView]:
    return {
        "top": project_shape(shape, "top", (0, 0, 1), transform=lambda x, y: (x, y), include_hidden=False),
        "front": project_shape(shape, "front", (0, -1, 0), transform=lambda x, y: (y, x), include_hidden=True),
        "end": project_shape(shape, "end", (1, 0, 0), transform=lambda x, y: (-y, x), include_hidden=True),
        "iso": project_shape(shape, "iso", (-1.75, 1.1, 5), transform=lambda x, y: (x, y), include_hidden=False),
    }
