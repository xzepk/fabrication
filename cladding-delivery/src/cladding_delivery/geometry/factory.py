"""Lazy provider imports keep optional runtimes optional."""


def get_provider(name: str):
    name = (name or 'occt').lower()
    if name == 'occt':
        from .occt import OcctProvider
        return OcctProvider()
    if name == 'build123d':
        from .build123d_provider import Build123dProvider
        return Build123dProvider()
    if name == 'rhino':
        from .rhino import RhinoAdapterProvider
        return RhinoAdapterProvider()
    raise ValueError(f'unknown geometry provider: {name}; choose occt, build123d or rhino (no automatic fallback)')
