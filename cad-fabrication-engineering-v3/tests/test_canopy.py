import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cadfab_v3.model import build_geometry_ir
from cadfab_v3.backends.cadquery_backend import build_step
from cadfab_v3.drawing import engineering_pdf, engineering_dxf, reference_blank_dxf
from cadfab_v3.qa import run_qa


class CanopyReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config" / "canopy-reference-validation.yaml").read_text(encoding="utf-8"))

    def test_geometry_semantics(self):
        ir = build_geometry_ir(self.cfg)
        self.assertEqual(ir["ir_version"], "1.1")
        self.assertEqual(ir["geometry_level"], "NOMINAL_SKIN")
        self.assertEqual(ir["metrics"]["panel_count"], 56)
        self.assertAlmostEqual(ir["geometry"]["overall_length"], 29696.875, 3)
        self.assertAlmostEqual(ir["geometry"]["top_projection_depth"], 3530.0, 3)
        self.assertAlmostEqual(ir["geometry"]["profile_path_length_ref"], 4130.0, 3)
        self.assertNotIn("overall_depth", ir["geometry"])
        self.assertEqual(len({p["id"] for p in ir["parts"]}), 56)
        self.assertFalse(ir["metrics"]["flat_pattern_released"])
        self.assertIsNone(ir["metrics"]["blank_area_m2"])

    def test_dimensional_closure(self):
        ir = build_geometry_ir(self.cfg)
        g = ir["geometry"]
        setout = g["end_margin_left"] + g["bay_count"] * g["bay_pitch"] + g["end_margin_right"]
        self.assertLess(abs(setout - g["overall_length"]), 0.01)
        self.assertAlmostEqual(sum(g["top_depth_bands"]) + g["front_fascia_drop"], g["profile_path_length_ref"], 6)

    def test_end_to_end_artifact_qa(self):
        ir = build_geometry_ir(self.cfg)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            step = out / "model.step"
            pdf = out / "drawing.pdf"
            eng = out / "engineering.dxf"
            blank = out / "reference_blank.dxf"
            sm = build_step(ir, step)
            dm = engineering_pdf(ir, pdf)
            dxm = engineering_dxf(ir, eng)
            bm = reference_blank_dxf(ir, blank)
            qa = run_qa(ir, sm, dm, dxm, bm, pdf_path=pdf, eng_dxf_path=eng, blank_dxf_path=blank, step_path=step)
            self.assertTrue(qa["passed"], json.dumps(qa, ensure_ascii=False, indent=2))
            self.assertEqual(qa["checks"]["pdf_preflight"]["panel_ids_found"], 56)
            self.assertEqual(qa["checks"]["pdf_preflight"]["page_count"], 3)
            self.assertEqual(qa["drawing"]["view_source"], "OCCT_HLR_FROM_BREP")


if __name__ == "__main__":
    unittest.main()
