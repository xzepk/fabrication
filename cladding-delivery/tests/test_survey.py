from pathlib import Path
from cladding_delivery.project import init_project, create_snapshot
from cladding_delivery.gates import record_gate
from cladding_delivery.pipeline import run_pipeline
from cladding_delivery.util import write_json, read_json

def test_remeasured_applies_adopted_value(tmp_path:Path):
    skill=Path(__file__).resolve().parents[1]; project=tmp_path/'p'; init_project(project,skill)
    comps=[{'id':'P','kind':'panel','geometry':{'type':'planar_plate','width_mm':100,'height_mm':200,'thickness_mm':3},'material':{'name':'al'},'source':{'drawing_sha256':'x'}}]
    write_json(project/'work'/'components.json',comps)
    write_json(project/'work'/'survey.json',{'measurements':[{'id':'S1','target_component_id':'P','field':'width_mm','design_value_mm':100,'measured_value_mm':102,'adopted_value_mm':102,'evidence':'x'}]})
    create_snapshot(project); record_gate(project,'scope','eng','ok',None); record_gate(project,'survey','surveyor','ok',None)
    m=run_pipeline(project,'remeasured')
    assert m['survey_applied_count']==1
    run=project/'runs'/m['run_id']; results=read_json(run/'results.json')
    assert results[0]['flat']['blank_width_mm']==102
