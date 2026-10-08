#!/usr/bin/env python3
"""Record Stage 2 candidate evidence without promoting unexecuted model or Rhino gates."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from workbuddy_evidence import read_json, write_json, run_directory, verify_run
from stage2_gate import verify_bundle


def create_report(source, run):
    source = Path(source).resolve()
    run = run_directory(source, Path(run))
    verify_run(source, run)
    report = copy.deepcopy(read_json(run / 'acceptance.local.json'))
    report.update(candidate='rhino-ai-harness-stage2-local-candidate',
                  scope='orthogonal-planar-plate-review', manufacturing_release=False,
                  stage2_qualification='BLOCKED', windows_verification='ON_HOLD',
                  actual_local_model='NOT_RUN')
    rows = report['checks']
    process_result = run / 'cladding-process/cladding-results.json'
    process = read_json(process_result) if process_result.is_file() else None
    actual = bool(process and process.get('failed') == 0 and process.get('realSkill') == 'PASS'
                  and type(process.get('passed')) is int and process['passed'] > 0)
    relative = lambda path: path.resolve().relative_to(source).as_posix()
    rows['S-01'] = {'status': 'PASS' if actual else 'NOT_RUN',
                    'execution': 'actual-independent-skill-process',
                    'reason': 'Actual bounded independent Skill process and negative integration tests.' if actual else 'No successful configured Skill process run in this build.',
                    'evidence': [relative(process_result)] if actual else []}
    rows['S-02'] = {'status': 'NOT_RUN', 'execution': 'live-windows-rhino',
                    'reason': 'Windows/Rhino selected-source, review, preview and adoption qualification is ON HOLD.', 'evidence': []}
    rows['S-03'] = {'status': 'NOT_RUN', 'execution': 'rendered-artifact-readback',
                    'reason': 'This build does not claim human inspection of final rendered pages. ASCII labels and maps have automated checks only.', 'evidence': []}
    canopy = actual and bool(process.get('canopyJob')) and bool(process.get('canopyOutputDirectory'))
    if canopy:
        folder = Path(process['canopyOutputDirectory']).resolve()
        if not folder.is_relative_to((run / 'cladding-process').resolve()):
            raise ValueError('Canopy result is outside this build evidence')
        report['review_bundle'] = {'path': relative(folder),
                                   'manifestSha256': hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()}
        verify_bundle(source, report['review_bundle'])
    rows['S-04'] = {'status': 'PASS' if canopy else 'NOT_RUN',
                    'execution': 'actual-canopy-golden-readback',
                    'reason': 'Actual 56-part NOMINAL_SKIN canopy fixture, STEP/drawing/BOM bindings and no manufacturing release.' if canopy else 'No successful complete canopy fixture run in this build.',
                    'evidence': [relative(process_result)] if canopy else []}
    rows['S-05'] = {'status': 'NOT_RUN', 'execution': 'actual-local-model',
                    'reason': 'Synthetic protocol fixtures do not establish actual local-model or natural-language quality.', 'evidence': []}
    write_json(run / 'acceptance.stage2.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--run-root', required=True, type=Path)
    args = parser.parse_args()
    create_report(args.source_root, args.run_root)
    print('Stage 2 evidence recorded. Windows/Rhino and actual-model gates remain NOT_RUN; release BLOCKED.')


if __name__ == '__main__':
    main()
