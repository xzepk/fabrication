from __future__ import annotations
import json, os, shlex, subprocess
from pathlib import Path
from ..util import sha256_file

class ACadSharpUnavailable(RuntimeError): pass


def command_path():
    raw=os.environ.get('CADFAB_ACADSHARP_DUMP','').strip()
    return raw or None


def inspect_dwg(path: Path):
    cmd=command_path()
    if not cmd:
        raise ACadSharpUnavailable('CADFAB_ACADSHARP_DUMP is not configured')
    argv=shlex.split(cmd) + ['inspect', str(path.resolve())]
    p=subprocess.run(argv, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f'ACadSharp helper failed ({p.returncode}): {p.stderr.strip()}')
    try:
        data=json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError('ACadSharp helper did not return JSON') from e
    data.setdefault('adapter','acadsharp')
    data.setdefault('file',str(path.resolve()))
    data.setdefault('sha256',sha256_file(path))
    return data
