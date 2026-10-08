#!/usr/bin/env python3
"""Create per-run evidence without rewriting committed historical acceptance."""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sys

from release_gate import REQUIRED, LIVE, source_digest, source_entries

MANIFEST = pathlib.Path('evidence/repository-workflow/source-manifest.json')
REQUIRED_COMMANDS = ('source-verify', 'restore', 'build', 'core-tests', 'host-tests',
                     'release-gate-tests', 'workbuddy-evidence-tests', 'publish-restore', 'publish')
PLUGIN_FILES = ('RhinoAi.Plugin.rhp', 'RhinoAi.Plugin.deps.json', 'RhinoAi.Core.dll', 'RhinoAi.Contracts.dll')
HOST_FILES = ('RhinoAi.Host.exe', 'RhinoAi.Host.dll', 'RhinoAi.Host.deps.json',
              'RhinoAi.Host.runtimeconfig.json', 'RhinoAi.Core.dll', 'RhinoAi.Contracts.dll')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write('\n')


def source_manifest(root):
    entries = source_entries(root)
    return {'algorithm': 'sha256-utf8-json-posix-ordinal-v1',
            'source_digest': source_digest(root), 'files': dict(entries)}


def verify_source(root):
    expected = read_json(root / MANIFEST)
    actual = source_manifest(root)
    if expected.get('source_digest') != actual['source_digest'] or expected.get('files') != actual['files']:
        raise ValueError('Source bytes do not match the committed repository-workflow manifest. Preserve differences; reacquire the intended commit without line-ending conversion. Do not refresh the manifest to hide this mismatch.')
    return actual


def safe_child(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Evidence path escapes its root: ' + str(relative))
    return path


def run_directory(root, run):
    root = root.resolve()
    run = run.resolve()
    allowed = (root / 'artifacts/workbuddy-runs').resolve()
    if run == allowed or not run.is_relative_to(allowed) or not run.is_dir():
        raise ValueError('Run root must be an existing unique directory under module/artifacts/workbuddy-runs.')
    return run


def candidate_manifest(run):
    candidate = run / 'candidate'
    for folder, names in (('plugin', PLUGIN_FILES), ('host', HOST_FILES)):
        for name in names:
            file = safe_child(candidate, folder + '/' + name)
            if not file.is_file() or file.stat().st_size == 0:
                raise ValueError('Missing candidate file: ' + str(file))
    return {file.relative_to(candidate).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(candidate.rglob('*'), key=lambda p: p.relative_to(candidate).as_posix())
            if file.is_file() and file != candidate / 'SHA256.json'}


def verify_commands(run):
    records = read_json(run / 'commands.json')
    if not isinstance(records, list):
        raise ValueError('commands.json must be an array')
    matched = {}
    for name in REQUIRED_COMMANDS:
        rows = [row for row in records if row.get('name') == name]
        if len(rows) != 1 or rows[0].get('exit_code') != 0:
            raise ValueError('Successful command evidence required: ' + name)
        log = safe_child(run, rows[0]['log'])
        if not log.is_file() or not log.stat().st_size:
            raise ValueError('Missing command log: ' + name)
        matched[name] = log
    core = matched['core-tests'].read_text(encoding='utf-8-sig')
    match = re.search(r'RESULT (\d+)/(\d+) passed\.', core)
    if not match or int(match[1]) == 0 or match[1] != match[2]:
        raise ValueError('Core test result is incomplete or failed')
    http = read_json(run / 'host-integration/results.json')
    if http.get('failed') != 0 or not isinstance(http.get('passed'), int) or http['passed'] < 1:
        raise ValueError('HTTP integration result is incomplete or failed')
    return matched, {'core_passed': int(match[1]), 'core_total': int(match[2]),
                     'http_passed': http['passed'], 'http_failed': http['failed']}


def init_run(root, run, source_commit=None):
    run = run_directory(root, run)
    if any((run / name).exists() for name in ('acceptance.local.json', 'source-manifest.json', 'live-cases.json')):
        raise ValueError('This run already has evidence; use a new run directory. Never reinitialize live results.')
    manifest = verify_source(root)
    logs, results = verify_commands(run)
    candidates = candidate_manifest(run)
    if source_commit and not re.fullmatch(r'[0-9a-fA-F]{40}', source_commit):
        raise ValueError('source-commit must be the full 40-character Git commit, not SOURCE_BASELINE or a branch label')
    def relative(path):
        return path.resolve().relative_to(root.resolve()).as_posix()
    checks = {key: {'status': 'NOT_RUN', 'execution': 'live-windows-rhino',
                    'reason': 'No live Windows/Rhino acceptance has been recorded for this run.', 'evidence': []}
              for key in REQUIRED}
    checks['F-01'] = {'status': 'PASS', 'execution': 'actual-sdk-compilation',
                      'evidence': [relative(logs[x]) for x in ('restore', 'build', 'publish-restore', 'publish')],
                      'reason': 'Actual locked restore/build and framework-dependent win-x64 publish succeeded in this run. This does not establish Windows/Rhino execution.'}
    checks['F-12'] = {'status': 'PASS', 'execution': 'automated',
                      'evidence': [relative(logs[x]) for x in ('core-tests', 'host-tests', 'release-gate-tests', 'workbuddy-evidence-tests')],
                      'reason': 'Actual automated Core, HTTP-process, release-gate and repository-evidence tests passed for this run. Live Rhino remains separate.'}
    report = {'schema_version': 1, 'verified_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'candidate': 'rhino-ai-harness-stage1-repository-workflow',
              'source_digest': manifest['source_digest'], 'source_commit': source_commit,
              'source_commit_provenance': 'recorded checkout or supplied archive commit' if source_commit else 'UNKNOWN; preserve download provenance before live qualification',
              'production_status': 'REVIEW', 'stage1_release': 'BLOCKED', 'live_environment': {},
              'checks': checks, 'automated_results': results,
              'live_cases_file': relative(run / 'live-cases.json')}
    write_json(run / 'source-manifest.json', manifest)
    write_json(run / 'candidate/SHA256.json', {'source_digest': manifest['source_digest'], 'files': candidates})
    write_json(run / 'live-cases.json', {'source_digest': manifest['source_digest'], 'cases': {
        f'L-{i:02}': {'status': 'NOT_RUN', 'reason': 'Not executed in this run.', 'evidence': []} for i in range(1, 21)}})
    write_json(run / 'acceptance.local.json', report)
    return report


def verify_run(root, run):
    run = run_directory(root, run)
    current = verify_source(root)
    original = read_json(run / 'source-manifest.json')
    if original != current:
        raise ValueError('Source no longer matches this run')
    recorded = read_json(run / 'candidate/SHA256.json')
    if recorded.get('source_digest') != current['source_digest'] or recorded.get('files') != candidate_manifest(run):
        raise ValueError('Candidate bytes no longer match this run')
    report = read_json(run / 'acceptance.local.json')
    if report.get('source_digest') != current['source_digest']:
        raise ValueError('Acceptance no longer matches this run')
    verify_commands(run)
    # Live case records are evidence, never automatically promoted by build/init.
    live = read_json(run / 'live-cases.json')
    if live.get('source_digest') != current['source_digest']:
        raise ValueError('Live case source digest mismatch')
    for i in range(1, 21):
        row = live.get('cases', {}).get(f'L-{i:02}', {})
        if row.get('status') not in {'PASS', 'FAIL', 'BLOCKED', 'NOT_RUN'}:
            raise ValueError(f'Missing/invalid live case L-{i:02}')
        if row['status'] == 'PASS':
            if not row.get('evidence'):
                raise ValueError(f'L-{i:02} PASS requires evidence')
            for reference in row['evidence']:
                file = safe_child(root, reference)
                if not file.is_file() or not file.stat().st_size:
                    raise ValueError(f'L-{i:02} missing evidence: {reference}')
    # Complete acceptance additionally requires all twenty cases; partial PASSs
    # may still be recorded while the technical gate correctly remains blocked.
    if all(report.get('checks', {}).get(key, {}).get('status') == 'PASS' for key in LIVE):
        if not isinstance(report.get('source_commit'), str) or not re.fullmatch(r'[0-9a-fA-F]{40}', report['source_commit']):
            raise ValueError('Full live acceptance requires verified full 40-character source commit provenance')
        if any(live['cases'][f'L-{i:02}']['status'] != 'PASS' for i in range(1, 21)):
            raise ValueError('Full live acceptance requires all L-01 through L-20 to PASS with evidence')
    return current


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify-source', 'init', 'verify-run'))
    parser.add_argument('--source-root', required=True, type=pathlib.Path)
    parser.add_argument('--run-root', type=pathlib.Path)
    parser.add_argument('--source-commit')
    args = parser.parse_args(argv)
    try:
        root = args.source_root.resolve()
        if not (root / 'RhinoAi.sln').is_file():
            raise ValueError('source-root must be the Rhino module')
        if args.command == 'verify-source':
            result = verify_source(root)
        else:
            if args.run_root is None:
                raise ValueError('--run-root is required')
            result = init_run(root, args.run_root, args.source_commit) if args.command == 'init' else verify_run(root, args.run_root)
        print(f"PASS {args.command}: source {result['source_digest']}; live Rhino is not implied.")
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f'BLOCKED {args.command}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
