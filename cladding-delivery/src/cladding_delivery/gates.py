from __future__ import annotations
from pathlib import Path
from .project import current_snapshot, now_iso
from .util import read_json, write_json, sha256_file

class GateBlocked(RuntimeError): pass


def record_gate(project: Path, gate: str, actor: str, statement: str, evidence: Path | None):
    if gate not in ('scope','survey','order'):
        raise ValueError('gate must be scope, survey, or order')
    snap=current_snapshot(project)
    rec={'gate':gate,'actor':actor,'statement':statement,'snapshot':snap,'recorded_at':now_iso()}
    if evidence:
        if not evidence.exists(): raise FileNotFoundError(evidence)
        rec['evidence']={'path':str(evidence.resolve()),'sha256':sha256_file(evidence)}
    state_path=project/'state'/'state.json'
    state=read_json(state_path, {'confirmations':{}})
    state.setdefault('confirmations',{})[gate]=rec
    write_json(state_path,state)
    return rec


def require_gate(project: Path, gate: str):
    snap=current_snapshot(project)
    state=read_json(project/'state'/'state.json', {})
    rec=state.get('confirmations',{}).get(gate)
    if not rec:
        raise GateBlocked(f'{gate} confirmation missing')
    if rec.get('snapshot') != snap:
        raise GateBlocked(f'{gate} confirmation belongs to snapshot {rec.get("snapshot")}, current is {snap}')
    return rec
