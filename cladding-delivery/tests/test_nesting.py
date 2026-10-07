from cladding_delivery.nesting import shelf_nest

def test_shelf_nest_basic():
    r=shelf_nest([{'id':'A','w':500,'h':1000,'qty':2}],1500,4000,10,10)
    assert not r['unplaced']
    assert len(r['sheets'])==1
    assert len(r['sheets'][0]['placements'])==2

import math
import pytest

@pytest.mark.parametrize('index,value', [(0,0),(0,float('nan')),(1,-1),(2,-100),(2,float('inf')),(3,-1)])
def test_invalid_stock_gap_margin_rejected(index,value):
    args=[150,150,10,0];args[index]=value
    with pytest.raises(ValueError):
        shelf_nest([{'id':'A','w':100,'h':100,'qty':2}],*args)


def test_nesting_no_overlap_and_within_stock():
    result=shelf_nest([{'id':'A','w':100,'h':100,'qty':9}],350,350,10,10)
    assert not result['unplaced']
    for sheet in result['sheets']:
        for i,a in enumerate(sheet['placements']):
            assert a['x']>=10 and a['y']>=10 and a['x']+a['w']<=340 and a['y']+a['h']<=340
            for b in sheet['placements'][i+1:]:
                assert (a['x']+a['w']+10<=b['x'] or b['x']+b['w']+10<=a['x'] or
                        a['y']+a['h']+10<=b['y'] or b['y']+b['h']+10<=a['y'])
