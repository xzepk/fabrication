from __future__ import annotations
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import csv, json, math, uuid
from .geometry.factory import get_provider
from .geometry.base import GeometryUnsupported
from .gates import require_gate
from .project import snapshot_payload, current_snapshot
from .util import read_json, write_json, sha256_file, canonical_hash
from .identity import identity_map
from .geometry.acceptance import inspect_step
from .bom import bom_row
from .nesting import shelf_nest

class PipelineBlocked(RuntimeError): pass

def _now(): return datetime.now(timezone.utc).isoformat()


def _survey_dimension(value, label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
        raise PipelineBlocked(f'{label} must be a finite positive number, not a boolean or numeric string')
    return float(value)


def run_pipeline(project:Path, mode:str):
    if mode not in ('preview','remeasured'): raise ValueError('mode must be preview or remeasured')
    confirmations={'scope':require_gate(project,'scope')}
    if mode=='remeasured': confirmations['survey']=require_gate(project,'survey')
    # Bind generation to exactly the data covered by the confirmations. Never reread
    # mutable model/config/survey files after this point for geometry construction.
    inputs=snapshot_payload(project)
    bound_snapshot=canonical_hash(inputs)
    if any(rec.get('snapshot')!=bound_snapshot for rec in confirmations.values()):
        raise PipelineBlocked('inputs changed while reading confirmations; confirm the current snapshot and retry')
    cfg=deepcopy(inputs['config'])
    if cfg.get('project',{}).get('units','mm') != 'mm' or cfg.get('geometry',{}).get('units','mm') != 'mm':
        raise PipelineBlocked('built-in engineering model uses mm; convert and confirm input units explicitly')
    nestcfg=cfg.get('nesting',{})
    try:
        # Preserve raw types so bool/string inputs cannot bypass nesting validation.
        stock=(nestcfg.get('stock_width_mm',1500),nestcfg.get('stock_height_mm',4000),nestcfg.get('gap_mm',10),nestcfg.get('edge_margin_mm',10))
        shelf_nest([],*stock)
    except (ValueError,TypeError) as exc:
        raise PipelineBlocked(f'invalid nesting configuration: {exc}') from exc
    provider=get_provider(cfg.get('geometry',{}).get('provider','occt'))
    components=deepcopy(inputs['components'])
    if not components: raise PipelineBlocked('work/components.json is empty')
    labels=identity_map(components)  # fail before any export on duplicate/case-colliding IDs
    survey_applied=[]
    if mode=='remeasured':
        components=deepcopy(components)
        survey=inputs['survey'] or {}
        by_id={c.get('id'):c for c in components}
        for m in survey.get('measurements',[]):
            cid=m.get('target_component_id'); field=m.get('field'); adopted=m.get('adopted_value_mm')
            if cid not in by_id: raise PipelineBlocked(f'survey {m.get("id")}: unknown component {cid}')
            geom=by_id[cid].setdefault('geometry',{})
            if field not in geom: raise PipelineBlocked(f'survey {m.get("id")}: geometry field {field} missing on {cid}')
            original=_survey_dimension(geom[field],f'{cid}.{field} design geometry')
            design=m.get('design_value_mm')
            if design is not None: design=_survey_dimension(design,f'survey {m.get("id")} design_value_mm')
            if m.get('measured_value_mm') is not None:
                _survey_dimension(m['measured_value_mm'],f'survey {m.get("id")} measured_value_mm')
            if design is not None and abs(original-design)>1e-6:
                raise PipelineBlocked(f'survey {m.get("id")}: design value mismatch for {cid}.{field}: model={geom[field]} survey={design}')
            if adopted is None: raise PipelineBlocked(f'survey {m.get("id")}: adopted_value_mm missing')
            adopted=_survey_dimension(adopted,f'survey {m.get("id")} adopted_value_mm')
            survey_applied.append({'measurement_id':m.get('id'),'component_id':cid,'field':field,'design_value_mm':geom[field],'measured_value_mm':m.get('measured_value_mm'),'adopted_value_mm':adopted,'evidence':m.get('evidence')})
            geom[field]=adopted
    run_id=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    run_dir=project/'runs'/run_id; (run_dir/'geometry').mkdir(parents=True); (run_dir/'flat').mkdir();
    write_json(run_dir/'label_map.json',labels)
    write_json(run_dir/'input_snapshot.json',{'hash':bound_snapshot,'payload':inputs,'confirmations':confirmations})
    write_json(run_dir/'effective_components.json',components)
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
            # Run-relative paths survive copying a project to another workstation.
            for key in ('step','stl'):
                if built.get(key): built[key]=Path(built[key]).relative_to(run_dir).as_posix()
            if flat and flat.get('dxf'): flat['dxf']=Path(flat['dxf']).relative_to(run_dir).as_posix()
            results.append({'component_id':c['id'],'geometry':built,'flat':flat})
        except GeometryUnsupported as e:
            issues.append({'component_id':c.get('id'),'stage':'geometry','severity':'BLOCK_PRODUCTION','message':str(e)})
        except Exception as e:
            issues.append({'component_id':c.get('id'),'stage':'geometry','severity':'ERROR','message':f'{type(e).__name__}: {e}'})
    nesting=shelf_nest(rectangles,*stock) if rectangles else None
    if nesting and nesting['unplaced']:
        issues.append({'stage':'nesting','severity':'BLOCK_PRODUCTION','message':'one or more blanks exceed stock size','unplaced':nesting['unplaced']})
    if current_snapshot(project)!=bound_snapshot:
        issues.append({'stage':'snapshot','severity':'BLOCK_PRODUCTION',
                       'message':'inputs changed during generation; artifacts remain bound to the original confirmed snapshot and must be regenerated'})
    write_json(run_dir/'results.json',results); write_json(run_dir/'issues.json',issues); write_json(run_dir/'nesting.json',nesting)
    write_json(run_dir/'bom.json',bom)
    with (run_dir/'bom.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['component_id','machine_id','display_label','kind','geometry_type','material','grade','quantity','volume_mm3_each','theoretical_weight_kg_total']; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(bom)
    hashes={str(p.relative_to(run_dir)).replace('\\','/'):sha256_file(p) for p in sorted(run_dir.rglob('*')) if p.is_file()}
    manifest={'run_id':run_id,'created_at':_now(),'mode':mode,'status':'REVIEW','manufacturing_release':False,'production_qualified':False,'snapshot':bound_snapshot,'geometry_provider':provider.health(),'component_count':len(components),'survey_applied_count':len(survey_applied),'survey_applied':survey_applied,'successful_geometry':len(results),'issue_count':len(issues),'production_blocked':any(i['severity'] in ('BLOCK_PRODUCTION','ERROR') for i in issues),'artifacts':list(hashes),'artifact_sha256':hashes}
    write_json(run_dir/'run_manifest.json',manifest)
    return manifest


def verify_run(project:Path,run_id:str):
    if not run_id or Path(run_id).name != run_id or run_id in ('.','..') or '\\' in run_id:
        raise ValueError('run-id must be a single run directory name')
    d=project/'runs'/run_id; m=read_json(d/'run_manifest.json')
    if not m: raise FileNotFoundError(d/'run_manifest.json')
    required=['results.json','issues.json','bom.json','bom.csv','run_manifest.json','label_map.json','effective_components.json','nesting.json','input_snapshot.json']
    missing=[x for x in required if not (d/x).exists()]
    errors=[]; checked=[]
    hashes=m.get('artifact_sha256',{})
    if not hashes: errors.append('artifact hashes missing; legacy runs must be regenerated')
    actual_files={p.relative_to(d).as_posix() for p in d.rglob('*') if p.is_file() and p!=d/'run_manifest.json'}
    if set(hashes)!=actual_files: errors.append('artifact hash coverage differs from run files')
    for rel,digest in hashes.items():
        path=(d/rel).resolve()
        if not path.is_relative_to(d.resolve()):
            errors.append(f'unsafe artifact path: {rel}'); continue
        if not path.is_file() or sha256_file(path)!=digest:
            errors.append(f'artifact missing or changed: {rel}')
    if not missing:
        try:
            captured=read_json(d/'input_snapshot.json')
            if canonical_hash(captured['payload'])!=m.get('snapshot') or captured['hash']!=m.get('snapshot'):
                errors.append('captured input snapshot differs from manifest')
            expected_gates=['scope']+(['survey'] if m.get('mode')=='remeasured' else [])
            for gate in expected_gates:
                if captured.get('confirmations',{}).get(gate,{}).get('snapshot')!=m.get('snapshot'):
                    errors.append(f'{gate} confirmation not bound to run snapshot')
            components=read_json(d/'effective_components.json')
            identity_map(components)
            by_id={c['id']:c for c in components}
            for item in read_json(d/'results.json'):
                cid=item['component_id']; built=item['geometry']; step=Path(built['step'])
                if not step.is_absolute(): step=d/step
                if not step.resolve().is_relative_to(d.resolve()):
                    errors.append(f'{cid}: STEP path outside run'); continue
                acceptance=inspect_step(step,by_id[cid]); checked.append({'component_id':cid,'step_acceptance':acceptance})
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
    integrity_ok=not missing and not errors
    stale=current_snapshot(project)!=m.get('snapshot')
    if stale: errors.append('run is stale: current project inputs differ from the confirmed run snapshot')
    current_gates=read_json(project/'state'/'state.json',{}).get('confirmations',{})
    gates=['scope']+(['survey'] if m.get('mode')=='remeasured' else [])
    if any(current_gates.get(gate,{}).get('snapshot')!=m.get('snapshot') for gate in gates):
        errors.append('current confirmations do not cover this run snapshot')
    ok=integrity_ok and not errors
    return {'run_id':run_id,'ok':ok,'artifact_integrity_ok':integrity_ok,'stale':stale,'missing':missing,'errors':errors,
            'geometries_checked':checked,'status':m.get('status'),
            'production_blocked':bool(m.get('production_blocked')) or not ok,
            'manufacturing_release':False}
