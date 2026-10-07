from __future__ import annotations
import json, os, shlex, subprocess
from pathlib import Path
from ..util import sha256_file

class ACadSharpUnavailable(RuntimeError): pass


def command_path():
    raw_argv=os.environ.get('CADFAB_ACADSHARP_DUMP_ARGV','').strip()
    if raw_argv:
        try:
            argv=json.loads(raw_argv)
        except json.JSONDecodeError as error:
            raise ACadSharpUnavailable('CADFAB_ACADSHARP_DUMP_ARGV must be a JSON string array') from error
        if not isinstance(argv,list) or not argv or any(not isinstance(x,str) or not x for x in argv):
            raise ACadSharpUnavailable('CADFAB_ACADSHARP_DUMP_ARGV must be a nonempty JSON string array')
        return argv
    raw=os.environ.get('CADFAB_ACADSHARP_DUMP','').strip()
    return raw or None


def inspect_dwg(path: Path):
    cmd=command_path()
    if not cmd:
        raise ACadSharpUnavailable('CADFAB_ACADSHARP_DUMP is not configured')
    argv=(cmd if isinstance(cmd,list) else shlex.split(cmd)) + ['inspect', str(path.resolve())]
    p=subprocess.run(argv, capture_output=True, encoding='utf-8', errors='strict', timeout=300)
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
