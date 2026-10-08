#!/usr/bin/env python3
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from stage2_gate import evaluate, verify_bundle, REQUIRED_STAGE2, EXECUTIONS
from release_gate import REQUIRED, LIVE


class Stage2GateTests(unittest.TestCase):
    def candidate(self):
        rows = {name: {'status': 'PASS', 'evidence': ['test-only-evidence.txt'],
                       'execution': 'live-windows-rhino' if name in LIVE else 'automated'}
                for name in REQUIRED}
        rows.update({name: {'status': 'PASS', 'evidence': ['test-only-evidence.txt'],
                           'execution': EXECUTIONS[name]} for name in REQUIRED_STAGE2})
        return {'checks': rows, 'production_status': 'REVIEW', 'manufacturing_release': False,
                'scope': 'orthogonal-planar-plate-review',
                'live_environment': {name: 'test-only' for name in
                    ('windows_version', 'rhino_version', 'runtime_version', 'source_digest', 'reviewer')}}

    def test_complete_synthetic_metadata_for_gate_unit_test(self):
        self.assertEqual([], evaluate(self.candidate()))

    def test_every_missing_row_blocks(self):
        for name in REQUIRED_STAGE2:
            candidate = self.candidate()
            del candidate['checks'][name]
            self.assertTrue(any(name in issue for issue in evaluate(candidate)))

    def test_fixture_is_not_real_model_or_live_rhino(self):
        for name in ('S-02', 'S-05'):
            candidate = self.candidate()
            candidate['checks'][name]['execution'] = 'fake-http-fixture'
            self.assertTrue(any(name in issue for issue in evaluate(candidate)))

    def test_hold_does_not_release(self):
        candidate = self.candidate()
        candidate['checks']['F-02']['status'] = 'NOT_RUN'
        candidate['checks']['F-02']['reason'] = 'ON HOLD by user; development continues'
        self.assertTrue(any('F-02' in issue for issue in evaluate(candidate)))

    def test_no_manufacturing_override(self):
        for value in (True, None, 'false'):
            candidate = self.candidate()
            candidate['manufacturing_release'] = value
            self.assertTrue(any('manufacturing' in issue for issue in evaluate(candidate)))

    def test_scope_and_evidence_required(self):
        candidate = self.candidate()
        candidate['scope'] = 'general-cladding'
        candidate['checks']['S-04']['evidence'] = []
        issues = evaluate(candidate)
        self.assertTrue(any('scope' in issue for issue in issues))
        self.assertTrue(any('S-04' in issue for issue in issues))

    def test_bundle_readback_detects_changed_and_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'output'
            folder.mkdir()
            artifact = folder / 'bom.json'
            artifact.write_bytes(b'[]')
            manifest = {'status': 'REVIEW', 'manufacturingRelease': False,
                        'artifacts': [{'path': 'bom.json', 'bytes': 2,
                                       'sha256': hashlib.sha256(b'[]').hexdigest()}]}
            raw = json.dumps(manifest).encode()
            (folder / 'manifest.json').write_bytes(raw)
            reference = {'path': 'output', 'manifestSha256': hashlib.sha256(raw).hexdigest()}
            verify_bundle(root, reference)
            artifact.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'changed'):
                verify_bundle(root, reference)
            artifact.unlink()
            with self.assertRaises(OSError):
                verify_bundle(root, reference)

    def test_bundle_path_and_missing_reference_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for reference in (None, {'path': '../escape'}, {'path': '/absolute'}, {'path': 'unsafe\\name'}):
                with self.assertRaises(ValueError):
                    verify_bundle(Path(tmp), reference)


if __name__ == '__main__':
    unittest.main(verbosity=2)
