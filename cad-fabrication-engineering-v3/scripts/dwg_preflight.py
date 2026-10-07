#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shlex, shutil, subprocess
from pathlib import Path

DWG_VERSIONS={"AC1015":"AutoCAD 2000/2002","AC1018":"AutoCAD 2004/2005/2006","AC1021":"AutoCAD 2007/2008/2009","AC1024":"AutoCAD 2010/2011/2012","AC1027":"AutoCAD 2013-2017","AC1032":"AutoCAD 2018+"}

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()

def command_spec(kind:str):
    env_name='CADFAB_ACADSHARP_CMD' if kind=='acadsharp' else 'CADFAB_ODA_CMD'
    default='cadfab-acadsharp-dump' if kind=='acadsharp' else 'cadfab-oda-dump'
    raw=os.environ.get(env_name,default).strip()
    parts=shlex.split(raw)
    exe=shutil.which(parts[0]) if parts else None
    return {'kind':kind,'env':env_name,'configured':raw,'executable':exe,'available':bool(exe),'argv_prefix':parts}

def inspect(path:Path):
    header=path.read_bytes()[:6].decode('ascii',errors='replace')
    return {'path':str(path),'sha256':sha256(path),'bytes':path.stat().st_size,'dwg_header':header,'dwg_generation':DWG_VERSIONS.get(header,'unknown'),
            'adapters':{k:command_spec(k) for k in ('acadsharp','oda')}}

def run_adapter(kind:str,path:Path,out_dir:Path):
    spec=command_spec(kind)
    if not spec['available']:
        return {'parser':kind,'attempted':False,'success':False,'reason':f"adapter unavailable: {spec['configured']}"}
    target=out_dir/kind; target.mkdir(parents=True,exist_ok=True)
    cmd=spec['argv_prefix']+['parse','--input',str(path),'--output',str(target)]
    cp=subprocess.run(cmd,capture_output=True,text=True)
    evidence=target/'parser-evidence.json'
    ok=cp.returncode==0 and evidence.exists()
    return {'parser':kind,'attempted':True,'success':ok,'returncode':cp.returncode,'command':cmd,
            'evidence':str(evidence) if evidence.exists() else None,'stdout_tail':cp.stdout[-4000:],'stderr_tail':cp.stderr[-4000:]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('drawing')
    ap.add_argument('--parser',choices=['acadsharp','oda','auto'],default='acadsharp')
    ap.add_argument('--out-dir',default='work/parser_raw')
    ap.add_argument('--check-only',action='store_true')
    ap.add_argument('--allow-reference',action='store_true')
    a=ap.parse_args(); path=Path(a.drawing).resolve()
    if not path.exists(): raise SystemExit(f'not found: {path}')
    result=inspect(path); result['policy']=a.parser; result['attempts']=[]; result['selected_parser']=None
    if not a.check_only:
        order=['acadsharp'] if a.parser=='acadsharp' else ['oda'] if a.parser=='oda' else ['acadsharp','oda']
        for kind in order:
            r=run_adapter(kind,path,Path(a.out_dir).resolve()); result['attempts'].append(r)
            if r['success']:
                result['selected_parser']=kind; break
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if a.check_only:
        available = result['adapters']['acadsharp']['available'] or result['adapters']['oda']['available']
        if not available and not a.allow_reference: raise SystemExit(2)
    elif result['selected_parser'] is None and not a.allow_reference:
        raise SystemExit(2)
if __name__=='__main__': main()
