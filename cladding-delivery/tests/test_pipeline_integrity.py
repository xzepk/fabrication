from copy import deepcopy
from pathlib import Path
import json
import pytest
from cladding_delivery.project import init_project, current_snapshot
from cladding_delivery.gates import record_gate, GateBlocked
from cladding_delivery.pipeline import run_pipeline, verify_run
from cladding_delivery.cli import main
from cladding_delivery.proposals import stage_proposal
from cladding_delivery.util import write_json, read_json
from cladding_delivery.geometry.occt import OcctProvider
from test_provider_contract import plate


@pytest.fixture
def project(tmp_path):
    p = tmp_path / 'project'
    init_project(p, Path(__file__).resolve().parents[1])
    write_json(p / 'work' / 'components.json', [plate('东区-板一')])
    record_gate(p, 'scope', 'test-engineer', 'Test fixture only', None)
    return p


def test_preview_manifest_bom_identity_and_verified_package(project):
    manifest = run_pipeline(project, 'preview')
    assert manifest['status'] == 'REVIEW' and not manifest['production_blocked']
    d = project / 'runs' / manifest['run_id']
    assert read_json(d / 'label_map.json')[0]['raw_id'] == '东区-板一'
    assert read_json(d / 'bom.json')[0]['theoretical_weight_kg_total'] == pytest.approx(0.1638)
    checked = verify_run(project, manifest['run_id'])
    assert checked['ok'] and not checked['manufacturing_release']
    assert len(checked['geometries_checked']) == 1
    assert main(['--project', str(project), 'package', '--run-id', manifest['run_id']]) == 0


def test_run_preserves_confirmed_snapshot_when_inputs_change_during_build(project, monkeypatch):
    import cladding_delivery.pipeline as pipeline
    original = current_snapshot(project)
    class ChangingProvider(OcctProvider):
        def build_component(self, component, out_dir):
            result = super().build_component(component, out_dir)
            changed = deepcopy(component); changed['geometry']['width_mm'] = 500
            write_json(project / 'work' / 'components.json', [changed])
            return result
    monkeypatch.setattr(pipeline, 'get_provider', lambda name: ChangingProvider())
    manifest = run_pipeline(project, 'preview')
    assert manifest['snapshot'] == original != current_snapshot(project)
    assert manifest['production_blocked']
    d = project / 'runs' / manifest['run_id']
    assert read_json(d / 'effective_components.json')[0]['geometry']['width_mm'] == 100
    assert any(x['stage'] == 'snapshot' for x in read_json(d / 'issues.json'))
    check = verify_run(project, manifest['run_id'])
    assert not check['ok'] and check['stale'] and check['artifact_integrity_ok']
    assert main(['--project', str(project), 'package', '--run-id', manifest['run_id']]) == 2


def test_old_run_blocks_after_post_run_change(project):
    manifest = run_pipeline(project, 'preview')
    c = plate('东区-板一'); c['geometry']['width_mm'] = 102
    write_json(project / 'work' / 'components.json', [c])
    assert verify_run(project, manifest['run_id'])['stale']
    with pytest.raises(GateBlocked):
        run_pipeline(project, 'preview')


@pytest.mark.parametrize('change', ['tamper_step', 'delete_bom', 'extra_step', 'nested_manifest'])
def test_verify_and_package_reject_modified_artifacts(project, change):
    manifest = run_pipeline(project, 'preview'); d = project / 'runs' / manifest['run_id']
    if change == 'tamper_step':
        next((d / 'geometry').glob('*.step')).write_text('FAKE STEP')
    elif change == 'delete_bom':
        (d / 'bom.csv').unlink()
    elif change == 'extra_step':
        (d / 'UNVERIFIED.step').write_text('not manifested')
    else:
        (d / 'geometry' / 'run_manifest.json').write_text('{}')
    checked = verify_run(project, manifest['run_id'])
    assert not checked['ok'] and checked['production_blocked']
    assert main(['--project', str(project), 'package', '--run-id', manifest['run_id']]) == 2


def test_copied_project_keeps_verifiable_relative_artifact_paths(project, tmp_path):
    import shutil
    manifest=run_pipeline(project, 'preview')
    copied=tmp_path/'copied-project'
    shutil.copytree(project,copied)
    assert verify_run(copied,manifest['run_id'])['ok']


def test_unsupported_component_has_no_geometry_and_blocks_production(project):
    c = plate(); c['geometry']['holes'] = [{'diameter_mm': 10}]
    write_json(project / 'work' / 'components.json', [c])
    record_gate(project, 'scope', 'test-engineer', 'Test fixture only', None)
    manifest = run_pipeline(project, 'preview')
    assert manifest['production_blocked'] and manifest['successful_geometry'] == 0
    d = project / 'runs' / manifest['run_id']
    assert not list((d / 'geometry').iterdir()) and read_json(d / 'bom.json') == []
    assert verify_run(project, manifest['run_id'])['production_blocked']


def test_duplicate_ids_block_before_run_outputs(project):
    write_json(project / 'work' / 'components.json', [plate('A'), plate('a')])
    record_gate(project, 'scope', 'test-engineer', 'Test fixture only', None)
    with pytest.raises(ValueError, match='collision'):
        run_pipeline(project, 'preview')
    assert list((project / 'runs').iterdir()) == []


def test_proposal_import_does_not_mutate_active_model_or_confirmation(project, tmp_path):
    candidate = tmp_path / 'candidate.json'; write_json(candidate, [plate('候选')])
    before = (project / 'work' / 'components.json').read_bytes(); snap = current_snapshot(project)
    schema = read_json(Path(__file__).resolve().parents[1] / 'schemas' / 'component.schema.json')
    report = stage_proposal(project, candidate, schema, 'cadgen')
    assert report['status'] == 'CANDIDATE_REVIEW' and not report['scripts_executed'] and not report['active_model_changed']
    assert (project / 'work' / 'components.json').read_bytes() == before
    assert current_snapshot(project) == snap
    assert Path(report['candidate']).read_bytes() == candidate.read_bytes()


def test_proposal_rejects_script_and_blocks_unsupported_feature(project, tmp_path):
    source = tmp_path / 'candidate.py'; source.write_text("raise RuntimeError('must never execute')")
    schema = read_json(Path(__file__).resolve().parents[1] / 'schemas' / 'component.schema.json')
    with pytest.raises(ValueError, match='data-only'):
        stage_proposal(project, source, schema, 'cadgen')
    source = tmp_path / 'candidate.json'; c = plate(); c['geometry']['bends'] = [90]; write_json(source, [c])
    assert stage_proposal(project, source, schema, 'text-to-cad')['status'] == 'CANDIDATE_BLOCKED'


def test_remeasured_needs_current_survey_confirmation(project):
    with pytest.raises(GateBlocked, match='survey'):
        run_pipeline(project, 'remeasured')


@pytest.mark.parametrize('run_id', ['..', '../outside', 'nested/run', 'nested\\run'])
def test_run_id_path_traversal_rejected(project, run_id):
    with pytest.raises(ValueError):
        verify_run(project, run_id)


@pytest.mark.parametrize('field,value', [('adopted_value_mm', True), ('adopted_value_mm', float('nan')),
    ('adopted_value_mm', float('inf')), ('adopted_value_mm', '102'), ('adopted_value_mm', -1),
    ('adopted_value_mm', 0), ('design_value_mm', True), ('measured_value_mm', float('nan'))])
def test_survey_rejects_raw_nonnumeric_or_invalid_dimensions(project,field,value):
    from cladding_delivery.pipeline import PipelineBlocked
    measurement={'id':'S1','target_component_id':'东区-板一','field':'width_mm',
                 'design_value_mm':100,'measured_value_mm':102,'adopted_value_mm':102,'evidence':'test'}
    measurement[field]=value
    write_json(project/'work'/'survey.json',{'measurements':[measurement]})
    record_gate(project,'scope','test-engineer','Test fixture only',None)
    record_gate(project,'survey','test-surveyor','Test fixture only',None)
    with pytest.raises(PipelineBlocked,match='finite positive number'):
        run_pipeline(project,'remeasured')
    assert list((project/'runs').iterdir())==[]


@pytest.mark.parametrize('field,value',[('stock_width_mm',True),('gap_mm',True),('edge_margin_mm','10')])
def test_nesting_config_rejects_raw_boolean_and_numeric_string(project,field,value):
    import yaml
    from cladding_delivery.pipeline import PipelineBlocked
    path=project/'config'/'project.yaml'
    config=yaml.safe_load(path.read_text());config['nesting'][field]=value
    path.write_text(yaml.safe_dump(config))
    record_gate(project,'scope','test-engineer','Test fixture only',None)
    with pytest.raises(PipelineBlocked,match='invalid nesting configuration'):
        run_pipeline(project,'preview')
    assert list((project/'runs').iterdir())==[]
