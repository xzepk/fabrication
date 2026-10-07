from __future__ import annotations
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import csv, json, uuid
from .geometry.factory import get_provider
from .geometry.base import GeometryUnsupported
from .gates import require_gate
from .project import load_config, current_snapshot
from .util import read_json, write_json
from .bom import bom_row
from .nesting import shelf_nest

class PipelineBlocked(RuntimeError): pass

def _now(): return datetime.now(timezone.utc).isoformat()


def run_pipeline(project:Path, mode:str):
    if mode not in ('preview','remeasured'): raise ValueError('mode must be preview or remeasured')
    require_gate(project,'scope')
    if mode=='remeasured': require_gate(project,'survey')
    cfg=load_config(project); provider=get_provider(cfg.get('geometry',{}).get('provider','occt'))
    components=read_json(project/'work'/'components.json',[])
    if not components: raise PipelineBlocked('work/components.json is empty')
    survey_applied=[]
    if mode=='remeasured':
        components=deepcopy(components)
        survey=read_json(project/'work'/'survey.json',{}) or {}
        by_id={c.get('id'):c for c in components}
        for m in survey.get('measurements',[]):
            cid=m.get('target_component_id'); field=m.get('field'); adopted=m.get('adopted_value_mm')
            if cid not in by_id: raise PipelineBlocked(f'survey {m.get("id")}: unknown component {cid}')
            geom=by_id[cid].setdefault('geometry',{})
            if field not in geom: raise PipelineBlocked(f'survey {m.get("id")}: geometry field {field} missing on {cid}')
            design=m.get('design_value_mm')
            if design is not None and abs(float(geom[field])-float(design))>1e-6:
                raise PipelineBlocked(f'survey {m.get("id")}: design value mismatch for {cid}.{field}: model={geom[field]} survey={design}')
            if adopted is None: raise PipelineBlocked(f'survey {m.get("id")}: adopted_value_mm missing')
            survey_applied.append({'measurement_id':m.get('id'),'component_id':cid,'field':field,'design_value_mm':geom[field],'measured_value_mm':m.get('measured_value_mm'),'adopted_value_mm':adopted,'evidence':m.get('evidence')})
            geom[field]=float(adopted)
    run_id=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    run_dir=project/'runs'/run_id; (run_dir/'geometry').mkdir(parents=True); (run_dir/'flat').mkdir();
    results=[]; issues=[]; bom=[]; rectangles=[]
    for c in components:
        try:
            built=provider.build_component(c,run_dir/'geometry')
            flat=None
            if c.get('kind')=='panel':
                try:
                    flat=provider.unfold_component(c,run_dir/'flat')
                    rectangles.append({'id':c['id'],'w':flat['blank_width_mm'],'h':flat['blank_height_mm'],'qty':c.get('quantity',1)})
                except GeometryUnsupported as e:
                    issues.append({'component_id':c['id'],'stage':'unfold','severity':'BLOCK_PRODUCTION','message':str(e)})
            bom.append(bom_row(c,built.get('metrics',{})))
            results.append({'component_id':c['id'],'geometry':built,'flat':flat})
        except GeometryUnsupported as e:
            issues.append({'component_id':c.get('id'),'stage':'geometry','severity':'BLOCK_PRODUCTION','message':str(e)})
        except Exception as e:
            issues.append({'component_id':c.get('id'),'stage':'geometry','severity':'ERROR','message':f'{type(e).__name__}: {e}'})
    nestcfg=cfg.get('nesting',{}); nesting=shelf_nest(rectangles,float(nestcfg.get('stock_width_mm',1500)),float(nestcfg.get('stock_height_mm',4000)),float(nestcfg.get('gap_mm',10)),float(nestcfg.get('edge_margin_mm',10))) if rectangles else None
    write_json(run_dir/'results.json',results); write_json(run_dir/'issues.json',issues); write_json(run_dir/'nesting.json',nesting)
    write_json(run_dir/'bom.json',bom)
    with (run_dir/'bom.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['component_id','kind','geometry_type','material','grade','quantity','volume_mm3_each','theoretical_weight_kg_total']; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(bom)
    manifest={'run_id':run_id,'created_at':_now(),'mode':mode,'status':'REVIEW','snapshot':current_snapshot(project),'geometry_provider':provider.health(),'component_count':len(components),'survey_applied_count':len(survey_applied),'survey_applied':survey_applied,'successful_geometry':len(results),'issue_count':len(issues),'production_blocked':any(i['severity'] in ('BLOCK_PRODUCTION','ERROR') for i in issues),'artifacts':['results.json','issues.json','bom.json','bom.csv','nesting.json','geometry/','flat/']}
    write_json(run_dir/'run_manifest.json',manifest)
    return manifest


def verify_run(project:Path,run_id:str):
    d=project/'runs'/run_id; m=read_json(d/'run_manifest.json')
    if not m: raise FileNotFoundError(d/'run_manifest.json')
    required=['results.json','issues.json','bom.json','bom.csv','run_manifest.json']
    missing=[x for x in required if not (d/x).exists()]
    return {'run_id':run_id,'ok':not missing,'missing':missing,'status':m.get('status'),'production_blocked':m.get('production_blocked')}
