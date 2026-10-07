"""Real local runtime integration plus fail-closed policy regression tests."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cadfab_v3.backends.provider import BackendError, build_step, select_backend, validate_capabilities
from cadfab_v3.model import build_geometry_ir


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config/canopy-reference-validation.yaml").read_text())
        cls.ir = build_geometry_ir(cls.cfg)

    def exercise_real_backend(self, backend, python=None):
        before = copy.deepcopy(self.ir)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "geometry_ir.json").write_text(json.dumps(self.ir))
            step = root / "STEP" / "canopy.step"
            result = build_step(self.ir, step, backend=backend, runtime_python=python)
            self.assertEqual(result["provider"]["selected"], backend)
            self.assertEqual(result["solid_count"], 56)
            self.assertTrue(result["valid"])
            self.assertTrue(result["per_solid_geometry_verified"])
            self.assertEqual(result["bbox_mm"], [29288.876, 3529.0, 603.0])
            self.assertAlmostEqual(result["volume_mm3"], 358798865.544, places=3)
            self.assertEqual(result["saved_step_sha256"], hashlib.sha256(step.read_bytes()).hexdigest())
            self.assertFalse(result["provider"]["production_qualified"])
            if backend != "cadquery":
                self.assertTrue((root / "SOURCE" / "canopy.py").is_file())
            original = step.read_bytes()
            with self.assertRaisesRegex(BackendError, "Refusing to overwrite"):
                build_step(self.ir, step, backend=backend, runtime_python=python)
            self.assertEqual(step.read_bytes(), original)
        self.assertEqual(self.ir, before)

    def test_real_cadquery(self):
        self.exercise_real_backend("cadquery")

    def test_real_build123d(self):
        self.exercise_real_backend("build123d")

    @unittest.skipUnless(os.environ.get("CADFAB_TEST_CADGEN_PYTHON"), "Set CADFAB_TEST_CADGEN_PYTHON to an external cadgen 0.7.15 venv")
    def test_real_cadgen_export(self):
        try:
            self.exercise_real_backend("cadgen", os.environ["CADFAB_TEST_CADGEN_PYTHON"])
        except BackendError as exc:
            if "PermissionError: [Errno 1] Operation not permitted" in str(exc) and "socket" in str(exc):
                self.skipTest("BLOCKED: cadgen @step requires local IPC sockets denied by this execution environment; no export pass claimed")
            raise

    @unittest.skipUnless(os.environ.get("CADFAB_TEST_CADGEN_PYTHON"), "External current build123d runtime not specified")
    def test_real_build123d_current_external(self):
        self.exercise_real_backend("build123d", os.environ["CADFAB_TEST_CADGEN_PYTHON"])

    def test_unknown_provider_and_python_fail_closed(self):
        with self.assertRaises(BackendError):
            select_backend("imaginary")
        with self.assertRaises(BackendError):
            select_backend("cadgen", "/missing/cadfab/python")

    def test_complex_features_fail_closed(self):
        for change in ({"geometry_level": "FABRICATION_SOLID"}, {"status": "PRODUCTION_CANDIDATE"}, {"units": "inch"}):
            ir = copy.deepcopy(self.ir)
            ir.update(change)
            with self.assertRaises(BackendError):
                validate_capabilities(ir)
        for requirements in (["sections"], ["true_flat_patterns"], ["curved_panels"]):
            with self.assertRaises(BackendError):
                validate_capabilities(self.ir, requirements)
        ir = copy.deepcopy(self.ir)
        ir["parts"][0]["holes"] = [{"diameter": 10}]
        with self.assertRaisesRegex(BackendError, "Unsupported part fields"):
            validate_capabilities(ir)

    def test_nonfinite_dimensions_fail_closed(self):
        for value in (float("nan"), float("inf"), -1, 0, True):
            ir = copy.deepcopy(self.ir)
            ir["parts"][0]["width"] = value
            with self.assertRaises(BackendError):
                validate_capabilities(ir)

    def test_config_values_are_not_silently_normalized(self):
        for value in (14.9, True, "14"):
            cfg = copy.deepcopy(self.cfg)
            cfg["geometry"]["bay_count"] = value
            with self.assertRaisesRegex(ValueError, "bay_count"):
                build_geometry_ir(cfg)
        cfg = copy.deepcopy(self.cfg)
        cfg["geometry"]["joint_strategy"] = "LEFT"
        with self.assertRaisesRegex(ValueError, "joint_strategy"):
            build_geometry_ir(cfg)
        cfg = copy.deepcopy(self.cfg)
        cfg["geometry"]["overall_length"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            build_geometry_ir(cfg)

    def test_boolean_and_text_dimensions_are_rejected_before_conversion(self):
        for key, value in (("bay_pitch", True), ("bay_pitch", "2092.634"), ("panel_thickness", True), ("top_depth_bands", [1190, True, 1170])):
            cfg = copy.deepcopy(self.cfg)
            cfg["geometry"][key] = value
            with self.assertRaisesRegex(ValueError, "real number"):
                build_geometry_ir(cfg)
        for key in ("density_kg_m3", "thickness"):
            cfg = copy.deepcopy(self.cfg)
            cfg["material"][key] = True
            with self.assertRaisesRegex(ValueError, "real number"):
                build_geometry_ir(cfg)

    def test_auto_availability_policy_only(self):
        # Policy tests supplement, never substitute for the real kernel/export tests above.
        responses = [subprocess.CompletedProcess([], 1, "", "cadgen missing"),
                     subprocess.CompletedProcess([], 0, json.dumps({"provider": "build123d", "ok": True}), "")]
        with mock.patch("cadfab_v3.backends.provider._run", side_effect=responses):
            selection = select_backend("auto")
        self.assertEqual(selection.selected, "build123d")
        self.assertEqual(selection.unavailable[0]["provider"], "cadgen")
        with mock.patch("cadfab_v3.backends.provider._run", return_value=responses[0]) as run:
            with self.assertRaisesRegex(BackendError, "no fallback"):
                select_backend("cadgen")
            self.assertEqual(run.call_count, 1)

    def test_runtime_build_error_never_falls_back(self):
        selection = select_backend("build123d")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "STEP" / "failed.step"
            with mock.patch("cadfab_v3.backends.provider._run", return_value=subprocess.CompletedProcess([], 4, "", "deliberate runtime failure")) as run:
                with self.assertRaisesRegex(BackendError, "no fallback attempted"):
                    build_step(self.ir, target, selection=selection)
            self.assertEqual(run.call_count, 1)
            self.assertFalse(target.exists())

    def test_successful_exporter_with_wrong_geometry_is_not_delivered(self):
        import cadquery as cq
        selection = select_backend("build123d")
        def wrong_export(command, **kwargs):
            source = Path(command[2])
            target = source.parent.parent / "STEP" / "wrong.step"
            cq.exporters.export(cq.Workplane("XY").box(1, 2, 3), str(target), exportType="STEP")
            return subprocess.CompletedProcess(command, 0, "success", "")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "STEP" / "wrong.step"
            with mock.patch("cadfab_v3.backends.provider._run", side_effect=wrong_export):
                with self.assertRaisesRegex(BackendError, "STEP readback failed"):
                    build_step(self.ir, target, selection=selection)
            self.assertFalse(target.exists())
            self.assertFalse((root / "SOURCE" / "wrong.py").exists())

    def test_runner_refuses_existing_output_without_changes(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            marker = out / "input.txt"
            marker.write_text("keep me")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/run_project.py"), str(ROOT / "config/canopy-reference-validation.yaml"), str(out)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Output already exists", result.stderr)
            self.assertEqual(marker.read_text(), "keep me")
            self.assertEqual(list(out.iterdir()), [marker])

    def test_runner_rejects_unknown_geometry_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "output"
            config = Path(td) / "input.yaml"
            cfg = copy.deepcopy(self.cfg)
            cfg["geometry"]["curve_radius"] = 100
            config.write_text(yaml.safe_dump(cfg))
            original = config.read_bytes()
            result = subprocess.run([sys.executable, str(ROOT / "scripts/run_project.py"), str(config), str(out)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unimplemented geometry", result.stderr)
            self.assertEqual(config.read_bytes(), original)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
