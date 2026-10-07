from copy import deepcopy
from pathlib import Path
import json
import math
import pytest
from cladding_delivery.geometry.base import GeometryUnsupported
from cladding_delivery.geometry.factory import get_provider
from cladding_delivery.geometry.contract import validate_component
from cladding_delivery.geometry.acceptance import inspect_step
from cladding_delivery.identity import component_identity, identity_map, IdentityError


def plate(cid='P-1'):
    return {'id': cid, 'kind': 'panel', 'geometry': {'type': 'planar_plate', 'width_mm': 100, 'height_mm': 200, 'thickness_mm': 3},
            'material': {'name': 'aluminum', 'density_kg_m3': 2730}, 'source': {'drawing_sha256': 'TEST'}}


def tube():
    c = plate('M-1'); c['kind'] = 'member'
    c['geometry'] = {'type': 'rect_tube', 'width_mm': 80, 'height_mm': 120, 'wall_mm': 4, 'length_mm': 1000}
    return c


@pytest.fixture(params=['occt', 'build123d'])
def provider(request):
    if request.param == 'build123d':
        pytest.importorskip('build123d')
    return get_provider(request.param)


@pytest.mark.parametrize('make_component', [plate, tube])
def test_provider_real_step_roundtrip(provider, make_component, tmp_path):
    c = make_component()
    result = provider.build_component(c, tmp_path)
    acceptance = inspect_step(Path(result['step']), c)
    assert acceptance['ok']
    assert acceptance['measured']['solid_count'] == 1
    assert acceptance['measured']['volume_mm3'] == pytest.approx(acceptance['expected']['volume_mm3'])
    assert result['metrics'] == acceptance['measured']
    assert Path(result['stl']).stat().st_size > 100


@pytest.mark.parametrize('feature,value', [('holes', [{'diameter_mm': 10}]), ('folds', [90]), ('bends', [{'radius_mm': 5}]),
                                         ('profile', [[0, 0], [10, 10]]), ('slots', [1]), ('unknown_feature', True)])
def test_features_rejected_before_any_export(provider, feature, value, tmp_path):
    c = plate(); c['geometry'][feature] = value
    with pytest.raises(GeometryUnsupported):
        provider.build_component(c, tmp_path / 'g')
    with pytest.raises(GeometryUnsupported):
        provider.unfold_component(c, tmp_path / 'f')
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('extra', [{'fabrication': {'holes': [{'diameter_mm': 10}]}}, {'returns': [20]}, {'bends': [90]}])
def test_root_manufacturing_features_rejected(extra):
    with pytest.raises(GeometryUnsupported):
        validate_component({**plate(), **extra})


@pytest.mark.parametrize('number', [0, -1, float('nan'), float('inf'), True, '10'])
def test_invalid_dimensions_fail_before_export(provider, number, tmp_path):
    c = plate(); c['geometry']['thickness_mm'] = number
    with pytest.raises(GeometryUnsupported):
        provider.build_component(c, tmp_path / 'g')
    assert list(tmp_path.iterdir()) == []


def test_tube_wall_blocks_solid_tube(provider, tmp_path):
    c = tube(); c['geometry']['wall_mm'] = 40
    with pytest.raises(GeometryUnsupported):
        provider.build_component(c, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('cid', ['东立面/一号板', '../escape', 'CON', 'a.b', 'LPT9', 'a'*80])
def test_unsafe_or_unicode_ids_are_portable_stable(cid):
    a = component_identity(plate(cid)); b = component_identity(plate(cid))
    assert a == b and a['raw_id'] == cid and a['display_label'] == cid
    assert a['machine_id'].isascii() and '/' not in a['machine_id'] and '.' not in a['machine_id']


def test_chinese_labels_roundtrip_and_ascii_dxf(provider, tmp_path):
    import ezdxf
    c = plate('东立面/一号板'); c['display_label'] = '铝板：东立面，甲组'
    built = provider.build_component(c, tmp_path / 'g')
    flat = provider.unfold_component(c, tmp_path / 'f')
    identity = json.loads((tmp_path / 'g' / (built['machine_id'] + '.identity.json')).read_text(encoding='utf-8'))
    assert identity['raw_id'] == c['id'] and identity['display_label'] == c['display_label']
    d = ezdxf.readfile(flat['dxf'])
    assert d.units == 4
    assert [e.dxf.text for e in d.modelspace().query('TEXT')] == [built['machine_id']]
    assert all(p.name.isascii() for p in tmp_path.rglob('*'))
    cut = list(d.modelspace().query("LWPOLYLINE[layer=='CUT']"))
    assert len(cut) == 1 and cut[0].closed and len(cut[0]) == 4


@pytest.mark.parametrize('ids', [('P-1', 'p-1'), ('P-1', 'P-1')])
def test_portable_identity_collisions_rejected(ids):
    with pytest.raises(IdentityError):
        identity_map([plate(ids[0]), plate(ids[1])])


def test_artifacts_are_not_overwritten(provider, tmp_path):
    c = plate(); built = provider.build_component(c, tmp_path)
    before = Path(built['step']).read_bytes()
    with pytest.raises(GeometryUnsupported, match='already exists'):
        provider.build_component(c, tmp_path)
    assert Path(built['step']).read_bytes() == before


def test_step_readback_rejects_wrong_real_geometry(tmp_path):
    import cadquery as cq
    path = tmp_path / 'wrong.step'
    cq.exporters.export(cq.Workplane('XY').box(100, 200, 4, centered=(False, False, False)), str(path))
    with pytest.raises(GeometryUnsupported, match='STEP acceptance failed'):
        inspect_step(path, plate())


def test_step_readback_rejects_translated_geometry(tmp_path):
    import cadquery as cq
    path = tmp_path / 'moved.step'
    cq.exporters.export(cq.Workplane('XY').box(100, 200, 3, centered=(False, False, False)).translate((1, 0, 0)), str(path))
    with pytest.raises(GeometryUnsupported, match='bbox_min_mm'):
        inspect_step(path, plate())


def test_step_readback_rejects_invalid_bytes(tmp_path):
    path = tmp_path / 'fake.step'; path.write_text('not a STEP file')
    with pytest.raises(GeometryUnsupported, match='STEP acceptance failed'):
        inspect_step(path, plate())


def test_unknown_provider_does_not_fallback():
    with pytest.raises(ValueError, match='no automatic fallback'):
        get_provider('cadgen')


def test_rhino_does_not_trust_server_metrics(monkeypatch, tmp_path):
    from cladding_delivery.geometry.rhino import RhinoAdapterProvider
    monkeypatch.setenv('CADFAB_RHINO_ADAPTER_URL', 'http://unused.test')
    provider = RhinoAdapterProvider()
    monkeypatch.setattr(provider, '_call', lambda *a: {'step': str(tmp_path / 'P-1.step'), 'metrics': {'volume_mm3': 60000}})
    with pytest.raises(GeometryUnsupported, match='missing/empty'):
        provider.build_component(plate(), tmp_path)


def test_rhino_blocks_unsupported_before_network(monkeypatch, tmp_path):
    from cladding_delivery.geometry.rhino import RhinoAdapterProvider
    monkeypatch.setenv('CADFAB_RHINO_ADAPTER_URL', 'http://unused.test')
    provider = RhinoAdapterProvider()
    monkeypatch.setattr(provider, '_call', lambda *a: pytest.fail('network call must not happen'))
    c = plate(); c['geometry']['holes'] = [10]
    with pytest.raises(GeometryUnsupported):
        provider.build_component(c, tmp_path)
