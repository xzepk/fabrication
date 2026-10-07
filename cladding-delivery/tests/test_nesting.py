from cladding_delivery.nesting import shelf_nest

def test_shelf_nest_basic():
    r=shelf_nest([{'id':'A','w':500,'h':1000,'qty':2}],1500,4000,10,10)
    assert not r['unplaced']
    assert len(r['sheets'])==1
    assert len(r['sheets'][0]['placements'])==2
