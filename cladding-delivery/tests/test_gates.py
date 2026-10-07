from pathlib import Path
from cladding_delivery.project import init_project
from cladding_delivery.gates import record_gate, require_gate, GateBlocked

def test_gate_invalidates_when_components_change(tmp_path:Path):
    skill=Path(__file__).resolve().parents[1]; project=tmp_path/'p'; init_project(project,skill)
    record_gate(project,'scope','eng','ok',None); require_gate(project,'scope')
    (project/'work'/'components.json').write_text('[{"id":"x"}]',encoding='utf-8')
    try: require_gate(project,'scope'); assert False
    except GateBlocked: pass
