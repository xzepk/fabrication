#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''): h.update(chunk)
    return h.hexdigest()


def _block_name(value):
    if isinstance(value, dict): return value.get('name')
    return str(value) if value is not None else None


def normalize(raw: dict, raw_path: Path, out_dir: Path):
    if not raw.get('success'):
        raise ValueError(f"ACadSharp dump did not succeed: {raw.get('error','unknown error')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    entities=[]
    for block in raw.get('blocks', []):
        owner=block.get('name')
        for e in block.get('entities', []):
            handle=e.get('handle')
            kind=e.get('type') or e.get('class')
            rec={
              'source_ref':{
                'handle':handle,
                'layer':e.get('layer'),
                'owner_block':owner,
                'block_path':[owner] if owner else [],
                'transform_chain':[],
              },
              'entity_type':kind,
              'class':e.get('class'),
              'invisible':bool(e.get('invisible',False)),
              'properties':{k:v for k,v in e.items() if k not in {'handle','type','class','owner','layer','invisible'}},
              'normalization_status':'RAW_CANONICAL_EVIDENCE',
            }
            if (e.get('class') or '').lower()=='insert' or str(kind).upper() in {'INSERT','ACDBBLOCKREFERENCE'}:
                rec['insert']={
                  'block':_block_name(e.get('Block')),
                  'insert_point':e.get('InsertPoint'),
                  'rotation':e.get('Rotation'),
                  'scale':[e.get('XScale'),e.get('YScale'),e.get('ZScale')],
                }
                rec['normalization_status']='INSERT_REQUIRES_TRANSFORM_EXPANSION'
            entities.append(rec)
    notifications=raw.get('notifications',[])
    issues=[{'severity':'WARNING','source':'ACadSharp','message':n.get('message') if isinstance(n,dict) else str(n),'raw':n} for n in notifications]
    manifest={
      'raw_dump':str(raw_path),
      'raw_dump_sha256':_sha(raw_path),
      'source_file':raw.get('file'),
      'parser':'ACadSharp',
      'parser_version':raw.get('library'),
      'entity_count':len(entities),
      'block_count':len(raw.get('blocks',[])),
      'layer_count':len(raw.get('layers',[])),
      'notification_count':len(notifications),
      'canonical_level':'RAW_CANONICAL_EVIDENCE',
      'production_geometry_ready':False,
      'reason':'Nested insert/XRef transform expansion and semantic resolution must complete before Geometry IR production use.'
    }
    (out_dir/'drawing_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out_dir/'canonical_entities.jsonl').open('w',encoding='utf-8') as f:
        for e in entities: f.write(json.dumps(e,ensure_ascii=False,separators=(',',':'))+'\n')
    (out_dir/'issues.json').write_text(json.dumps(issues,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('raw_json')
    ap.add_argument('out_dir')
    args=ap.parse_args()
    raw_path=Path(args.raw_json).resolve(); out=Path(args.out_dir).resolve()
    raw=json.loads(raw_path.read_text(encoding='utf-8'))
    print(json.dumps(normalize(raw,raw_path,out),ensure_ascii=False,indent=2))

if __name__=='__main__': main()
