from .occt import OcctProvider
from .rhino import RhinoAdapterProvider


def get_provider(name: str):
    name=(name or 'occt').lower()
    if name=='occt': return OcctProvider()
    if name=='rhino': return RhinoAdapterProvider()
    raise ValueError(f'unknown geometry provider: {name}')
