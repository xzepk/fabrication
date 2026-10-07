from __future__ import annotations
import argparse, hashlib, json, os, shutil, sys, zipfile
from pathlib import Path
import yaml
import jsonschema
from .project import init_project, create_snapshot, load_config
from .gates import record_gate, GateBlocked
from .pipeline import run_pipeline, verify_run, PipelineBlocked
from .cad.inspect import inspect_drawing
from .cad.acadsharp import command_path
from .geometry.factory import get_provider
from .util import write_json, read_json, sha256_file
from .identity import identity_map
from .geometry.contract import capabilities
from .proposals import stage_proposal


def skill_root():
    source=Path(__file__).resolve().parents[2]
    if (source/'config'/'project.example.yaml').is_file(): return source
    installed=Path(sys.prefix)/'share'/'cladding-delivery'
    if (installed/'config'/'project.example.yaml').is_file(): return installed
    raise RuntimeError('cladding resource files missing; reinstall the package or use the source scripts/run.py')
def emit(x): print(json.dumps(x,ensure_ascii=False,indent=2))

def cmd_doctor(project):
    cfg=load_config(project); checks=[]
    try:
        p=get_provider(cfg.get('geometry',{}).get('provider','occt')); detail=p.health(); checks.append({'name':'geometry','ok':bool(detail.get('ok')),'detail':detail})
    except Exception as e: checks.append({'name':'geometry','ok':False,'detail':f'{type(e).__name__}: {e}'})
    try:
        import ezdxf; checks.append({'name':'ezdxf','ok':True,'detail':ezdxf.__version__})
    except Exception as e: checks.append({'name':'ezdxf','ok':False,'detail':str(e)})
    checks.append({'name':'acadsharp-helper','ok':bool(command_path()),'detail':command_path() or 'not configured; required only for DWG'})
    result={'ok':all(c['ok'] for c in checks if c['name']!='acadsharp-helper'),'checks':checks}
    return result

def copy_input(project,path):
    dst=project/'inputs'/path.name
    if path.resolve()!=dst.resolve(): shutil.copy2(path,dst)
    return dst

def main(argv=None):
    ap=argparse.ArgumentParser(prog='cladding-delivery'); ap.add_argument('--project',required=True); sp=ap.add_subparsers(dest='cmd',required=True)
    sp.add_parser('init'); sp.add_parser('doctor');
    p=sp.add_parser('inspect'); p.add_argument('drawing')
    sp.add_parser('snapshot')
    p=sp.add_parser('record'); p.add_argument('gate',choices=['scope','survey','order']); p.add_argument('--actor',required=True); p.add_argument('--statement',required=True); p.add_argument('--evidence')
    p=sp.add_parser('survey-import'); p.add_argument('file')
    p=sp.add_parser('components-import'); p.add_argument('file')
    p=sp.add_parser('proposal-import'); p.add_argument('file'); p.add_argument('--engine',choices=['text-to-cad','cadgen','manual'],required=True)
    p=sp.add_parser('run'); p.add_argument('--mode',choices=['preview','remeasured'],required=True)
    p=sp.add_parser('verify'); p.add_argument('--run-id',required=True)
    p=sp.add_parser('package'); p.add_argument('--run-id',required=True)
    sp.add_parser('providers')
    args=ap.parse_args(argv); project=Path(args.project).resolve()
    try:
        if args.cmd=='init': emit(init_project(project,skill_root())); return 0
        if not project.exists(): raise FileNotFoundError(f'project does not exist: {project}; run init')
        if args.cmd=='doctor':
            result=cmd_doctor(project); emit(result); return 0 if result['ok'] else 1
        if args.cmd=='inspect':
            src=Path(args.drawing).resolve(); dst=copy_input(project,src); report=inspect_drawing(dst); write_json(project/'work'/(dst.stem+'.inspect.json'),report); emit(report); return 0
        if args.cmd=='snapshot': emit(create_snapshot(project)); return 0
        if args.cmd=='record': emit(record_gate(project,args.gate,args.actor,args.statement,Path(args.evidence).resolve() if args.evidence else None)); return 0
        if args.cmd=='survey-import':
            src=Path(args.file).resolve(); data=yaml.safe_load(src.read_text(encoding='utf-8')) or {}; write_json(project/'work'/'survey.json',data); emit({'imported':str(src),'measurements':len(data.get('measurements',[]))}); return 0
        if args.cmd=='components-import':
            src=Path(args.file).resolve(); data=json.loads(src.read_text(encoding='utf-8'))
            if not isinstance(data,list): raise ValueError('components file must be a JSON array')
            schema=json.loads((skill_root()/'schemas'/'component.schema.json').read_text(encoding='utf-8'))
            for i,item in enumerate(data):
                try: jsonschema.validate(item,schema)
                except jsonschema.ValidationError as e: raise ValueError(f'component[{i}] schema error: {e.message}') from e
            identity_map(data)
            write_json(project/'work'/'components.json',data); emit({'imported':len(data)}); return 0
        if args.cmd=='proposal-import':
            schema=json.loads((skill_root()/'schemas'/'component.schema.json').read_text(encoding='utf-8'))
            result=stage_proposal(project,Path(args.file).resolve(),schema,args.engine)
            emit(result); return 2 if result['issues'] else 0
        if args.cmd=='run':
            result=run_pipeline(project,args.mode); emit(result); return 2 if result['production_blocked'] else 0
        if args.cmd=='verify':
            result=verify_run(project,args.run_id); emit(result); return 0 if result['ok'] else 2
        if args.cmd=='package':
            verification=verify_run(project,args.run_id)
            if not verification['ok']: raise PipelineBlocked('package blocked: run artifacts failed verification')
            run=project/'runs'/args.run_id
            if not run.exists(): raise FileNotFoundError(run)
            manifest=read_json(run/'run_manifest.json')
            archive_files=[]
            for rel,digest in manifest['artifact_sha256'].items():
                path=(run/rel).resolve()
                if not path.is_relative_to(run.resolve()): raise PipelineBlocked('unsafe package artifact path')
                data=path.read_bytes()
                if hashlib.sha256(data).hexdigest()!=digest: raise PipelineBlocked('artifact changed while preparing package')
                archive_files.append((rel,data))
            archive_files.append(('run_manifest.json',(run/'run_manifest.json').read_bytes()))
            delivery=project/'deliveries'/f'{args.run_id}-REVIEW.zip'
            with zipfile.ZipFile(delivery,'w',zipfile.ZIP_DEFLATED) as z:
                for rel,data in archive_files: z.writestr(f'{args.run_id}/{rel}',data)
            emit({'package':str(delivery),'sha256':sha256_file(delivery),'status':'REVIEW'}); return 0
        if args.cmd=='providers':
            emit({'default':'occt','available_contracts':['occt','build123d','rhino'],
                  'builtin_capabilities':capabilities(), 'cadgen':'external proposal/review only; not a geometry provider',
                  'rhino_required_env':['CADFAB_RHINO_ADAPTER_URL']}); return 0
    except (GateBlocked,PipelineBlocked) as e:
        print(f'BLOCKED: {e}',file=sys.stderr); return 2
    except Exception as e:
        print(f'ERROR {type(e).__name__}: {e}',file=sys.stderr); return 1

if __name__=='__main__': raise SystemExit(main())
