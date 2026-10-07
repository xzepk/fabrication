from pathlib import Path
from cladding_delivery.geometry.occt import OcctProvider

def test_planar_plate(tmp_path:Path):
    p=OcctProvider(); c={'id':'P-1','kind':'panel','geometry':{'type':'planar_plate','width_mm':100,'height_mm':200,'thickness_mm':3},'material':{'name':'al'},'source':{'drawing_sha256':'x'}}
    built=p.build_component(c,tmp_path/'g'); flat=p.unfold_component(c,tmp_path/'f')
    assert Path(built['step']).exists(); assert Path(flat['dxf']).exists(); assert built['metrics']['volume_mm3']==60000
