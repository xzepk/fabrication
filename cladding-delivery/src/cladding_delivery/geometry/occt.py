from __future__ import annotations
from pathlib import Path
from typing import Any
from .base import GeometryProvider
from .contract import capabilities, validate_component
from .acceptance import inspect_step
from .artifacts import reserve_outputs, write_identity, unfold_plate


class OcctProvider(GeometryProvider):
    name = 'occt'

    def __init__(self):
        import cadquery as cq
        self.cq = cq

    def health(self) -> dict[str, Any]:
        import OCP
        return {'provider': self.name, 'ok': True, 'cadquery': self.cq.__version__,
                'ocp': getattr(OCP, '__version__', 'unknown'), 'capabilities': capabilities()}

    def build_component(self, component: dict, out_dir: Path) -> dict:
        validate_component(component)
        cq, g = self.cq, component['geometry']
        identity, (step, stl) = reserve_outputs(component, out_dir, ('.step', '.stl'))
        w, h = float(g['width_mm']), float(g['height_mm'])
        if g['type'] == 'planar_plate':
            shape = cq.Workplane('XY').box(w, h, float(g['thickness_mm']), centered=(False, False, False))
        else:
            wall, length = float(g['wall_mm']), float(g['length_mm'])
            outer = cq.Workplane('XY').rect(w, h).extrude(length)
            inner = cq.Workplane('XY').rect(w-2*wall, h-2*wall).extrude(length)
            shape = outer.cut(inner)
        try:
            cq.exporters.export(shape, str(step))
            acceptance = inspect_step(step, component)
            cq.exporters.export(shape, str(stl), tolerance=0.1, angularTolerance=0.1)
            write_identity(out_dir, identity)
        except Exception:
            step.unlink(missing_ok=True)
            stl.unlink(missing_ok=True)
            raise
        return {**identity, 'provider': self.name, 'type': g['type'], 'review_only': True,
                'step': str(step), 'stl': str(stl), 'metrics': acceptance['measured'],
                'step_acceptance': acceptance}

    def unfold_component(self, component: dict, out_dir: Path) -> dict:
        return unfold_plate(component, out_dir, self.name)
