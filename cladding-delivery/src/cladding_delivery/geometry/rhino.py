from __future__ import annotations
import json, os, urllib.request
from pathlib import Path
from typing import Any
from .base import GeometryProvider, GeometryUnsupported
from .contract import capabilities, validate_component
from .acceptance import inspect_step
from .artifacts import reserve_outputs, write_identity, unfold_plate


class RhinoAdapterProvider(GeometryProvider):
    name = 'rhino'

    def __init__(self):
        self.url = os.environ.get('CADFAB_RHINO_ADAPTER_URL', '').rstrip('/')
        self.key = os.environ.get('CADFAB_RHINO_ADAPTER_KEY', '')
        if not self.url:
            raise RuntimeError('CADFAB_RHINO_ADAPTER_URL is not configured')

    def _call(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.url+path, data=body, method='GET' if body is None else 'POST',
                                     headers={'Content-Type': 'application/json', **({'X-Adapter-Key': self.key} if self.key else {})})
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode('utf-8'))

    def health(self) -> dict[str, Any]:
        result = self._call('/health')
        return {**result, 'provider': self.name, 'local_capabilities': capabilities(),
                'artifact_contract': 'STEP on shared filesystem at requested output_step'}

    def build_component(self, component: dict, out_dir: Path) -> dict:
        validate_component(component)  # no implicit manufacturing capability from server claims
        identity, (step,) = reserve_outputs(component, out_dir, ('.step',))
        try:
            result = self._call('/v1/build-component', {'component': component, 'identity': identity,
                                                        'output_step': str(step.resolve()), 'units': 'mm'})
            if Path(result.get('step', '')).resolve() != step.resolve():
                raise GeometryUnsupported('Rhino adapter must return STEP at the exact requested shared-filesystem path')
            acceptance = inspect_step(step, component)
            write_identity(out_dir, identity)
        except Exception:
            step.unlink(missing_ok=True)
            raise
        return {**identity, 'provider': self.name, 'type': component['geometry']['type'],
                'review_only': True, 'step': str(step), 'metrics': acceptance['measured'],
                'step_acceptance': acceptance}

    def unfold_component(self, component: dict, out_dir: Path) -> dict:
        # Flat rectangles are locally reproducible; complex Rhino unroll is deliberately disabled
        # until a project-specific, validated fabrication contract is supplied.
        return unfold_plate(component, out_dir, self.name)
