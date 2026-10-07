"""Optional template-based build123d provider, independent of any CAD skill/cadgen runtime."""
from __future__ import annotations
from pathlib import Path
from .base import GeometryProvider, GeometryUnsupported
from .contract import capabilities, validate_component
from .acceptance import inspect_step
from .artifacts import reserve_outputs, write_identity, unfold_plate


class Build123dProvider(GeometryProvider):
    name = 'build123d'

    def __init__(self):
        try:
            import build123d as bd
        except ImportError as exc:
            raise RuntimeError('build123d provider requires the optional [build123d] dependency in the external runtime') from exc
        self.bd = bd

    def health(self):
        from importlib.metadata import version
        return {'provider': self.name, 'ok': True, 'build123d': version('build123d'),
                'capabilities': capabilities(), 'execution': 'deterministic templates only'}

    def build_component(self, component: dict, out_dir: Path) -> dict:
        validate_component(component)
        bd, g = self.bd, component['geometry']
        identity, (step, stl) = reserve_outputs(component, out_dir, ('.step', '.stl'))
        w, h = float(g['width_mm']), float(g['height_mm'])
        if g['type'] == 'planar_plate':
            shape = bd.Box(w, h, float(g['thickness_mm']), align=(bd.Align.MIN,)*3)
        else:
            wall, length = float(g['wall_mm']), float(g['length_mm'])
            alignment = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
            shape = bd.Box(w, h, length, align=alignment) - bd.Box(w-2*wall, h-2*wall, length, align=alignment)
        shape.label = identity['machine_id']
        try:
            if not bd.export_step(shape, str(step), unit=bd.Unit.MM):
                raise GeometryUnsupported('build123d STEP exporter returned failure')
            acceptance = inspect_step(step, component)
            if not bd.export_stl(shape, str(stl), tolerance=0.1, angular_tolerance=0.1):
                raise GeometryUnsupported('build123d STL exporter returned failure')
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
