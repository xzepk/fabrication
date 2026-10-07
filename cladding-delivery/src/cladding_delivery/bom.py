from __future__ import annotations

def bom_row(component:dict, metrics:dict):
    q=int(component.get('quantity',1)); mat=component.get('material',{}); density=mat.get('density_kg_m3')
    vol_mm3=float(metrics.get('volume_mm3',0))
    weight=None if density is None else vol_mm3*1e-9*float(density)*q
    return {
        'component_id':component['id'],'kind':component.get('kind'),'geometry_type':component.get('geometry',{}).get('type'),
        'material':mat.get('name'),'grade':mat.get('grade'),'quantity':q,
        'volume_mm3_each':vol_mm3,'theoretical_weight_kg_total':weight
    }
