#!/usr/bin/env python3
"""Combined Stage 1/2 qualification gate. Development continuation is not qualification."""
import argparse
import hashlib
import json
from pathlib import Path
from release_gate import evaluate as stage1_evaluate, VALID

REQUIRED_STAGE2 = ('S-01', 'S-02', 'S-03', 'S-04', 'S-05')
EXECUTIONS = {'S-01': 'actual-independent-skill-process',
              'S-02': 'live-windows-rhino',
              'S-03': 'rendered-artifact-readback',
              'S-04': 'actual-canopy-golden-readback',
              'S-05': 'actual-local-model'}


def verify_bundle(source_root, reference):
    if not isinstance(reference, dict) or not isinstance(reference.get('path'), str):
        raise ValueError('Canopy review bundle reference is required')
    root = Path(source_root).resolve()
    relative = reference['path']
    if '\\' in relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Unsafe canopy bundle path')
    folder = root / relative
    if not folder.resolve().is_relative_to(root) or any(p.is_symlink() for p in [folder, *folder.parents]):
        raise ValueError('Unsafe canopy bundle location')
    manifest_path = folder / 'manifest.json'
    if manifest_path.stat().st_size > 1048576 or manifest_path.is_symlink():
        raise ValueError('Invalid canopy manifest')
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference.get('manifestSha256'):
        raise ValueError('Canopy manifest bytes changed')
    manifest = json.loads(raw)
    if manifest.get('status') != 'REVIEW' or manifest.get('manufacturingRelease') is not False:
        raise ValueError('Canopy bundle improperly claims release')
    files = {'manifest.json'}
    total = 0
    entries = manifest.get('artifacts', [])
    if not 1 <= len(entries) <= 1000:
        raise ValueError('Canopy bundle file count invalid')
    for entry in entries:
        name = entry['path']
        if not isinstance(name, str) or '\\' in name or Path(name).is_absolute() or '..' in Path(name).parts or name in files:
            raise ValueError('Unsafe or duplicate canopy artifact')
        path = folder / name
        if not path.resolve().is_relative_to(folder.resolve()) or any(p.is_symlink() for p in [path, *path.parents]):
            raise ValueError('Unsafe canopy artifact location')
        size = path.stat().st_size
        total += size
        if not 0 < size <= 33554432 or size != entry['bytes'] or total > 134217728:
            raise ValueError('Canopy artifact size changed or exceeds limit')
        if hashlib.sha256(path.read_bytes()).hexdigest().lower() != entry['sha256'].lower():
            raise ValueError('Canopy artifact bytes changed')
        files.add(name)
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual != files:
        raise ValueError('Canopy bundle has missing or additional files')


def evaluate(report, source_root=None):
    blockers = stage1_evaluate(report, source_root)
    rows = report.get('checks', {})
    for name in REQUIRED_STAGE2:
        row = rows.get(name, {})
        status = row.get('status')
        if status not in VALID:
            blockers.append(f'{name}: missing or invalid status')
        elif status != 'PASS':
            blockers.append(f"{name}: {status} — {row.get('reason', 'No qualification evidence')}")
        else:
            if row.get('execution') != EXECUTIONS[name]:
                blockers.append(f'{name}: required execution is {EXECUTIONS[name]}')
            if not row.get('evidence'):
                blockers.append(f'{name}: PASS lacks evidence')
    if report.get('manufacturing_release') is not False:
        blockers.append('This local review candidate cannot release manufacturing')
    if report.get('scope') != 'orthogonal-planar-plate-review':
        blockers.append('Review bridge scope must be explicit')
    if source_root is not None and rows.get('S-04', {}).get('status') == 'PASS':
        try:
            verify_bundle(source_root, report.get('review_bundle'))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            blockers.append(f'S-04: {exc}')
    return blockers


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding='utf-8-sig'))
        blockers = evaluate(report, args.source_root.resolve())
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}))
        return 2
    print(json.dumps({'stage2_qualification': 'BLOCKED' if blockers else 'PASS',
                      'production_status': 'REVIEW', 'manufacturing_release': False,
                      'blockers': blockers}, ensure_ascii=False, indent=2))
    return 2 if blockers else 0


if __name__ == '__main__':
    raise SystemExit(main())
