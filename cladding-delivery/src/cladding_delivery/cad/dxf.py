from __future__ import annotations
from collections import Counter
from pathlib import Path
import ezdxf
from ..util import sha256_file


def inspect_dxf(path: Path):
    doc=ezdxf.readfile(path)
    msp=doc.modelspace()
    types=Counter(e.dxftype() for e in msp)
    layers=[l.dxf.name for l in doc.layers]
    blocks=[b.name for b in doc.blocks if not b.name.startswith('*')]
    return {
        'adapter':'ezdxf', 'format':'dxf', 'file':str(path.resolve()), 'sha256':sha256_file(path),
        'entity_count':sum(types.values()), 'entity_types':dict(sorted(types.items())),
        'layers':sorted(layers), 'blocks':sorted(blocks), 'notifications':[]
    }
