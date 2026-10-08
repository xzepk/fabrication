#!/usr/bin/env python3
import copy
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('gate',Path(__file__).with_name('release_gate.py'))
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
base={'production_status':'REVIEW','checks':{k:{'status':'PASS','evidence':['verified.log'],'execution':'live-windows-rhino' if k in gate.LIVE else 'automated'} for k in gate.REQUIRED},'live_environment':{k:'recorded' for k in ('windows_version','rhino_version','runtime_version','source_digest','reviewer')}}
assert not gate.evaluate(base)
for k in gate.REQUIRED:
    r=copy.deepcopy(base);r['checks'][k]['status']='NOT_RUN';assert gate.evaluate(r)
    r=copy.deepcopy(base);r['checks'][k]['evidence']=[];assert gate.evaluate(r)
for k in gate.LIVE:
    r=copy.deepcopy(base);r['checks'][k]['execution']='fake-adapter';assert gate.evaluate(r)
r=copy.deepcopy(base);r['production_status']='APPROVED_FOR_PRODUCTION';assert gate.evaluate(r)
assert gate.evaluate({})
import tempfile
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'verified.log').write_text('evidence')
    valid=copy.deepcopy(base);valid['source_digest']=gate.source_digest(root);valid['live_environment']['source_digest']=valid['source_digest']
    assert not gate.evaluate(valid,root)
    (root/'verified.log').write_text('tampered evidence')
    assert gate.evaluate(valid,root)
    valid['source_digest']=gate.source_digest(root);valid['live_environment']['source_digest']=valid['source_digest']
    for row in valid['checks'].values(): row['evidence']=['missing.log']
    assert gate.evaluate(valid,root)
print('PASS release gate rejects missing/not-run/fake/stale evidence and production promotion (40 assertions)')
