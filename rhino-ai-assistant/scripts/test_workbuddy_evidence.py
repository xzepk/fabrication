#!/usr/bin/env python3
"""Local fixtures only; these assertions never constitute live Rhino acceptance."""
import copy
import json
import pathlib
import tempfile
import unittest

import workbuddy_evidence as evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rhinoai-evidence-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name) / 'source with spaces'
        self.root.mkdir()
        (self.root / 'RhinoAi.sln').write_text('fixture\n', encoding='utf-8')
        self.run = self.root / 'artifacts/workbuddy-runs/test'
        (self.run / 'logs').mkdir(parents=True)
        (self.root / evidence.MANIFEST).parent.mkdir(parents=True)
        evidence.write_json(self.root / evidence.MANIFEST, evidence.source_manifest(self.root))
        commands = []
        for name in evidence.REQUIRED_COMMANDS:
            text = 'RESULT 37/37 passed.\n' if name == 'core-tests' else 'test fixture\n'
            file = self.run / 'logs' / (name + '.log')
            file.write_text(text + 'EXIT_CODE: 0\n', encoding='utf-8')
            commands.append({'name': name, 'exit_code': 0, 'log': 'logs/' + file.name})
        evidence.write_json(self.run / 'commands.json', commands)
        (self.run / 'host-integration').mkdir()
        evidence.write_json(self.run / 'host-integration/results.json', {'passed': 52, 'failed': 0})
        for folder, files in (('host', evidence.HOST_FILES), ('plugin', evidence.PLUGIN_FILES)):
            (self.run / 'candidate' / folder).mkdir(parents=True)
            for name in files:
                (self.run / 'candidate' / folder / name).write_bytes(b'fixture; not a real binary')

    def init(self):
        return evidence.init_run(self.root, self.run, 'a' * 40)

    def test_init_and_reverify_remain_blocked(self):
        report = self.init()
        self.assertEqual(report['production_status'], 'REVIEW')
        self.assertEqual(report['stage1_release'], 'BLOCKED')
        self.assertEqual(report['checks']['F-01']['status'], 'PASS')
        self.assertTrue(all(report['checks'][key]['status'] == 'NOT_RUN' for key in evidence.LIVE))
        self.assertEqual(len(evidence.read_json(self.run / 'live-cases.json')['cases']), 20)
        evidence.verify_run(self.root, self.run)
        self.assertFalse((self.run / 'acceptance.local.json').read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_source_tampering_detected(self):
        self.init()
        (self.root / 'RhinoAi.sln').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Source bytes'):
            evidence.verify_run(self.root, self.run)

    def test_candidate_tampering_detected(self):
        self.init()
        (self.run / 'candidate/plugin/RhinoAi.Plugin.rhp').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Candidate bytes'):
            evidence.verify_run(self.root, self.run)

    def test_candidate_added_file_detected(self):
        self.init()
        (self.run / 'candidate/plugin/unexpected.dll').write_bytes(b'new')
        with self.assertRaisesRegex(ValueError, 'Candidate bytes'):
            evidence.verify_run(self.root, self.run)

    def test_missing_candidate_blocked(self):
        (self.run / 'candidate/host/RhinoAi.Host.exe').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing candidate'):
            self.init()

    def test_failed_command_blocked(self):
        path = self.run / 'commands.json'
        data = evidence.read_json(path); data[0]['exit_code'] = 1
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Successful command'):
            self.init()

    def test_reinitialization_blocked(self):
        self.init()
        with self.assertRaisesRegex(ValueError, 'already has evidence'):
            self.init()

    def test_path_escape_blocked(self):
        path = self.run / 'commands.json'
        data = evidence.read_json(path); data[0]['log'] = '../../../../RhinoAi.sln'
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.init()

    def test_utf8_bom_and_chinese_evidence(self):
        path = self.run / 'commands.json'
        path.write_text(path.read_text(encoding='utf-8'), encoding='utf-8-sig')
        self.init()
        path = self.run / 'live-cases.json'
        data = evidence.read_json(path)
        data['cases']['L-01']['reason'] = '尚未进行 Windows 验收'
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8-sig')
        evidence.verify_run(self.root, self.run)

    def test_live_pass_without_evidence_blocked(self):
        self.init()
        path = self.run / 'live-cases.json'; data = evidence.read_json(path)
        data['cases']['L-01']['status'] = 'PASS'
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'PASS requires evidence'):
            evidence.verify_run(self.root, self.run)

    def test_full_pass_with_incomplete_live_cases_blocked(self):
        self.init()
        path = self.run / 'acceptance.local.json'; data = evidence.read_json(path)
        for key in evidence.LIVE:
            data['checks'][key]['status'] = 'PASS'
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'all L-01'):
            evidence.verify_run(self.root, self.run)

    def test_full_pass_with_unknown_commit_blocked(self):
        evidence.init_run(self.root, self.run)
        path = self.run / 'acceptance.local.json'; data = evidence.read_json(path)
        for key in evidence.LIVE:
            data['checks'][key]['status'] = 'PASS'
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'commit provenance'):
            evidence.verify_run(self.root, self.run)

    def test_invalid_commit_rejected(self):
        with self.assertRaisesRegex(ValueError, 'full 40-character'):
            evidence.init_run(self.root, self.run, 'main')

    def test_source_output_paths_excluded(self):
        original = evidence.verify_source(self.root)
        (self.root / 'artifacts/another-output.txt').write_bytes(b'generated')
        self.assertEqual(original, evidence.verify_source(self.root))

    def test_outside_run_rejected(self):
        with self.assertRaisesRegex(ValueError, 'under module'):
            evidence.run_directory(self.root, self.root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
