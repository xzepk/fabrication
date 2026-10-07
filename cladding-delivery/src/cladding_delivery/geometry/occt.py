from __future__ import annotations
from pathlib import Path
from typing import Any
import math
from .base import GeometryProvider, GeometryUnsupported

class OcctProvider(GeometryProvider):
    name='occt'
    def __init__(self):
        import cadquery as cq
        self.cq=cq

    def health(self) -> dict[str,Any]:
        import cadquery
        try:
            import OCP
            ocp_version=getattr(OCP,'__version__','unknown')
        except Exception:
            ocp_version='unknown'
        return {'provider':'occt','ok':True,'cadquery':getattr(cadquery,'__version__','unknown'),'ocp':ocp_version}

    def _safe_id(self, component):
        return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in str(component['id']))

    def build_component(self, component: dict, out_dir: Path) -> dict:
        cq=self.cq; g=component.get('geometry',{}); t=g.get('type'); cid=self._safe_id(component)
        out_dir.mkdir(parents=True, exist_ok=True)
        if t=='planar_plate':
            w=float(g['width_mm']); h=float(g['height_mm']); th=float(g['thickness_mm'])
            shape=cq.Workplane('XY').box(w,h,th,centered=(False,False,False))
            metrics={'volume_mm3':w*h*th,'surface_area_mm2':2*(w*h+w*th+h*th),'bbox_mm':[w,h,th]}
        elif t=='rect_tube':
            w=float(g['width_mm']); h=float(g['height_mm']); wall=float(g['wall_mm']); length=float(g['length_mm'])
            if wall <= 0 or wall*2 >= min(w,h): raise GeometryUnsupported(f'{cid}: invalid rect_tube wall')
            outer=cq.Workplane('XY').rect(w,h).extrude(length)
            inner=cq.Workplane('XY').rect(w-2*wall,h-2*wall).extrude(length)
            shape=outer.cut(inner)
            area=w*h-(w-2*wall)*(h-2*wall)
            metrics={'volume_mm3':area*length,'cross_section_area_mm2':area,'bbox_mm':[w,h,length]}
        else:
            raise GeometryUnsupported(f'{cid}: unsupported geometry.type={t}')
        step=out_dir/f'{cid}.step'; stl=out_dir/f'{cid}.stl'
        cq.exporters.export(shape,str(step))
        cq.exporters.export(shape,str(stl),tolerance=0.1,angularTolerance=0.1)
        return {'component_id':component['id'],'provider':'occt','type':t,'step':str(step),'stl':str(stl),'metrics':metrics}

    def unfold_component(self, component: dict, out_dir: Path) -> dict:
        g=component.get('geometry',{}); t=g.get('type'); cid=self._safe_id(component)
        if t!='planar_plate':
            raise GeometryUnsupported(f'{cid}: builtin unfold only supports planar_plate')
        if g.get('folds') or g.get('holes') or g.get('profile'):
            raise GeometryUnsupported(f'{cid}: folded/holed/custom-profile plates require a validated fabrication adapter')
        import ezdxf
        w=float(g['width_mm']); h=float(g['height_mm'])
        out_dir.mkdir(parents=True,exist_ok=True)
        path=out_dir/f'{cid}_flat.dxf'
        doc=ezdxf.new('R2018'); msp=doc.modelspace()
        msp.add_lwpolyline([(0,0),(w,0),(w,h),(0,h)], close=True, dxfattribs={'layer':'CUT'})
        doc.layers.add('INFO') if 'INFO' not in doc.layers else None
        msp.add_text(cid,height=max(3.0,min(w,h)*0.02),dxfattribs={'layer':'INFO'}).set_placement((0,h+10))
        doc.saveas(path)
        return {'component_id':component['id'],'provider':'occt','developable':True,'review_only':True,'dxf':str(path),'blank_width_mm':w,'blank_height_mm':h,'blank_area_mm2':w*h}
