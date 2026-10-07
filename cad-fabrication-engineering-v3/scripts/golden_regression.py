#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''): h.update(chunk)
    return h.hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output', help='generated project output directory to validate')
    args=ap.parse_args()
    spec=yaml.safe_load((ROOT/'references/golden-samples.yaml').read_text(encoding='utf-8'))
    errors=[]; checks={}
    for item in spec['files']:
        p=ROOT/'assets/golden-samples'/item['name']
        actual=sha256(p) if p.exists() else None
        ok=actual==item['sha256']
        checks[f"fingerprint:{item['name']}"]=ok
        if not ok: errors.append(f"golden fingerprint changed: {item['name']}")
    if args.output:
        out=Path(args.output).resolve()
        ir=json.loads((out/'geometry_ir.json').read_text(encoding='utf-8'))
        qa_files=list((out/'QA').glob('*_qa.json'))
        qa=json.loads(qa_files[0].read_text(encoding='utf-8')) if qa_files else {}
        exp=spec['current_reference_expectations']
        actual={
          'project':ir['project'],
          'panel_count':ir['metrics']['panel_count'],
          'panel_type_count':len({(p['kind'],round(p['width'],3),round(p['height'],3),round(p['thickness'],3)) for p in ir['parts']}),
          'overall_length_mm':ir['geometry']['overall_length'],
          'top_projection_depth_mm':ir['geometry']['top_projection_depth'],
          'profile_path_length_ref_mm':ir['geometry']['profile_path_length_ref'],
          'drawing_sheet_count':qa.get('drawing',{}).get('sheet_count'),
          'panel_mark_coverage':qa.get('drawing',{}).get('panel_mark_coverage',{}).get('ratio'),
          'flat_pattern_released':ir['metrics']['flat_pattern_released'],
        }
        for k,v in exp.items():
            ok=actual.get(k)==v
            checks[f"reference:{k}"]=ok
            if not ok: errors.append(f"reference mismatch {k}: expected={v!r} actual={actual.get(k)!r}")
    print(json.dumps({'passed':not errors,'errors':errors,'checks':checks},ensure_ascii=False,indent=2))
    if errors: raise SystemExit(2)

if __name__=='__main__': main()
