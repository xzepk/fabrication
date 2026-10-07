from __future__ import annotations
import shutil
from pathlib import Path
from datetime import datetime, timezone
import yaml
from .util import read_json, write_json, sha256_file, canonical_hash

DIRS = ['inputs','evidence','config','work','runs','deliveries','state']


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_project(project: Path, skill_root: Path):
    project.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        (project/d).mkdir(exist_ok=True)
    cfg = project/'config'/'project.yaml'
    if not cfg.exists():
        shutil.copy2(skill_root/'config'/'project.example.yaml', cfg)
    comp = project/'work'/'components.json'
    if not comp.exists():
        comp.write_text('[]\n', encoding='utf-8')
    state = project/'state'/'state.json'
    if not state.exists():
        write_json(state, {'created_at': now_iso(), 'confirmations': {}, 'snapshots': []})
    return {'project': str(project), 'config': str(cfg)}


def load_config(project: Path):
    p=project/'config'/'project.yaml'
    if not p.exists():
        raise FileNotFoundError(f'missing {p}; run init')
    return yaml.safe_load(p.read_text(encoding='utf-8')) or {}


def snapshot_payload(project: Path):
    config = load_config(project)
    inputs=[]
    for p in sorted((project/'inputs').glob('*')):
        if p.is_file(): inputs.append({'name':p.name,'sha256':sha256_file(p),'size':p.stat().st_size})
    components = read_json(project/'work'/'components.json', [])
    surveys = read_json(project/'work'/'survey.json', {})
    payload={'config':config,'inputs':inputs,'components':components,'survey':surveys}
    return payload


def create_snapshot(project: Path):
    payload=snapshot_payload(project)
    h=canonical_hash(payload)
    state_path=project/'state'/'state.json'
    state=read_json(state_path, {'confirmations':{},'snapshots':[]})
    entry={'hash':h,'created_at':now_iso(),'input_count':len(payload['inputs']),'component_count':len(payload['components'])}
    if not state.get('snapshots') or state['snapshots'][-1]['hash'] != h:
        state.setdefault('snapshots',[]).append(entry)
    state['current_snapshot']=h
    write_json(project/'state'/'snapshot.json', {'hash':h,'payload':payload})
    write_json(state_path,state)
    return entry


def current_snapshot(project: Path):
    return create_snapshot(project)['hash']
