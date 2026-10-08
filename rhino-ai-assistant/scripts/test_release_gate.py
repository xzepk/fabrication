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

# Windows Path's case-folded ordering must not change the source digest.
import hashlib
import json
import random
from pathlib import PurePosixPath, PureWindowsPath
names = ['SOURCE_BASELINE.json', 'SPEC.md', 'src/a.cs', 'src/Z.cs', 'src/a-b.cs', 'scripts/test.py', 'docs/中文.md']
entries = [(name, hashlib.sha256(name.encode('utf-8')).hexdigest()) for name in names]
expected = hashlib.sha256(json.dumps(sorted(entries), ensure_ascii=True, separators=(',', ':')).encode('utf-8')).hexdigest()
for path_class in (PurePosixPath, PureWindowsPath):
    for seed in range(10):
        candidates = [(path_class(name), value) for name, value in entries]
        random.Random(seed).shuffle(candidates)
        assert gate.digest_entries(candidates) == expected
        assert gate.digest_entries(sorted(candidates)) == expected
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for name, _ in entries:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(name.encode('utf-8'))
    assert gate.source_digest(root) == expected
    (root/'artifacts').mkdir(); (root/'artifacts'/'ignored.json').write_bytes(b'output')
    assert gate.source_digest(root) == expected
print('PASS canonical digest: POSIX/Windows/shuffled paths, case, Unicode, UTF-8 and exclusions (42 assertions)')
# The old frozen 46-file Linux manifest remains reproducible with canonical ordering.
historical = Path(__file__).resolve().parent.parent / 'evidence/source-manifest.json'
if historical.is_file():
    frozen = json.loads(historical.read_text(encoding='utf-8'))
    assert gate.digest_entries(frozen['files'].items()) == frozen['source_digest'] == 'f03be27fef5aecc3281c9b17f3108bea6a786b97470747fc25643ad6d07795ae'
    print('PASS canonical digest preserves original 46-file Linux frozen baseline (1 assertion)')
