from pathlib import Path
from .dxf import inspect_dxf
from .acadsharp import inspect_dwg


def inspect_drawing(path: Path):
    ext=path.suffix.lower()
    if ext=='.dxf': return inspect_dxf(path)
    if ext=='.dwg': return inspect_dwg(path)
    raise ValueError(f'unsupported drawing extension: {ext}')
