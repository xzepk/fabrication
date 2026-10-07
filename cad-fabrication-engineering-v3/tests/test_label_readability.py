"""Artifact-level font, Unicode identity, fallback and renderer regressions."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import ezdxf
import fitz
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cadfab_v3.labels import LabelPolicy, discover_font, is_ascii_text, stable_display_id, portable_file_stem, verify_font_raster
from cadfab_v3.model import build_geometry_ir
from cadfab_v3.drawing import engineering_pdf, engineering_dxf
from cadfab_v3.qa import _pdf_preflight, _dxf_preflight


class LabelReadabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = yaml.safe_load((ROOT / "config/canopy-reference-validation.yaml").read_text())
        cfg["geometry"]["bay_count"] = 2
        cfg["geometry"]["overall_length"] = cfg["geometry"]["bay_pitch"]*2 + 400
        cls.ir = build_geometry_ir(cfg)
        cls.ir["project"] = "雨棚铝板深化"
        cls.ir["parts"][0]["id"] = "顶板-甲-01"
        cls.ir["parts"][1]["id"] = "顶板-乙-01"

    def test_ids_preserve_identity_across_order_and_unicode(self):
        raws = ["顶板-甲", "顶板_甲", "顶板 甲", "TP-01-01", "a/b", "a?b", "e\u0301", "é"]
        mapped = [stable_display_id(value) for value in raws]
        self.assertEqual(len(set(mapped)), len(raws))
        self.assertEqual(mapped[3], "TP-01-01")
        self.assertTrue(all(is_ascii_text(value) for value in mapped))
        self.assertEqual(dict(zip(raws, mapped)), {raw: stable_display_id(raw) for raw in reversed(raws)})
        self.assertNotEqual(stable_display_id("e\u0301"), stable_display_id("é"))

    def test_portable_names_do_not_collapse_reserved_or_case_only_ids(self):
        raw = ["CON", "con", "A", "a", "ABC.", "..", "A:B", "顶板", "LPT1", "nul.txt"]
        marks = [stable_display_id(value) for value in raw]
        files = [portable_file_stem(value) for value in raw]
        self.assertEqual(len(raw), len({value.casefold() for value in marks}))
        self.assertEqual(len(raw), len({value.casefold() for value in files}))
        self.assertTrue(all(is_ascii_text(value) and not value.endswith(".") and ":" not in value for value in marks + files))
        self.assertEqual(portable_file_stem("canopy_reference_validation"), "canopy_reference_validation")

    def test_missing_and_latin_fonts_are_rejected(self):
        font, diagnostics = discover_font(["/missing/cadfab-font.ttf"])
        self.assertIsNone(font)
        self.assertTrue(diagnostics[0].startswith("missing:"))
        latin = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        if latin.exists():
            font, diagnostics = discover_font([latin])
            self.assertIsNone(font)
            self.assertTrue(any("probe glyphs missing" in value for value in diagnostics))

    def test_unknown_text_is_not_silently_lost(self):
        policy = LabelPolicy(font_candidates=[])
        text, embedded = policy.pdf("未审核的特殊工艺")
        self.assertFalse(embedded)
        self.assertTrue(is_ascii_text(text))
        self.assertIn("UNTRANSLATED", text)
        self.assertEqual(policy.metadata()["untranslated_labels"][0]["raw_label"], "未审核的特殊工艺")
        translated = LabelPolicy({"display_labels": {"未审核的特殊工艺": "Special process NOT REVIEWED"}}, font_candidates=[])
        self.assertEqual(translated.pdf("未审核的特殊工艺")[0], "Special process NOT REVIEWED")
        self.assertFalse(translated.metadata()["untranslated_labels"])

    def test_explicit_invalid_override_does_not_silently_find_system_font(self):
        with patch.dict(os.environ, {"CADFAB_CJK_FONT": "/missing/explicit-font.ttf"}):
            policy = LabelPolicy()
            self.assertIsNone(policy.font)
            self.assertEqual(policy.pdf("现场复尺尚未回填。")[0], "Site survey NOT APPLIED.")

    def test_missing_font_pdf_is_readable_and_preserves_raw_mapping(self):
        before = copy.deepcopy(self.ir)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"CADFAB_CJK_FONT": "/missing/explicit-font.ttf"}):
            pdf = Path(tmp) / "ascii.pdf"
            meta = engineering_pdf(self.ir, pdf)
            expected = {stable_display_id(p["id"]) for p in self.ir["parts"]}
            qa = _pdf_preflight(pdf, expected, 3, meta["label_mapping"])
            self.assertEqual(qa["panel_id_coverage"], 1)
            self.assertTrue(qa["raster_render_passed"])
            self.assertTrue(qa["label_readback_complete"], qa.get("labels_missing_from_readback"))
            self.assertEqual(qa["missing_glyph_count"], 0)
            self.assertFalse(meta["label_mapping"]["untranslated_labels"])
            self.assertFalse(meta["label_mapping"]["layout_issues"])
            self.assertFalse(meta["font"]["embedded_expected"])
            mapping = json.loads(pdf.with_suffix(".pdf.labels.json").read_text())
            self.assertIn({"raw_id": "顶板-甲-01", "display_id": stable_display_id("顶板-甲-01")}, mapping["part_id_mapping"])
            with fitz.open(pdf) as document:
                text = "".join(page.get_text() for page in document)
                self.assertIn("NOT CONFIRMED", text)
                self.assertNotIn("\ufffd", text)
                self.assertTrue(all(ord(ch) < 128 for ch in text))
        self.assertEqual(before, self.ir)

    def test_available_cjk_font_is_embedded_and_renders_all_glyphs(self):
        font, _ = discover_font()
        if not font:
            self.skipTest("No embeddable CJK font available; missing-font acceptance still runs")
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "unicode.pdf"
            with patch.dict(os.environ, {"CADFAB_CJK_FONT": font.source}):
                meta = engineering_pdf(self.ir, pdf)
            qa = _pdf_preflight(pdf, {stable_display_id(p["id"]) for p in self.ir["parts"]}, 3, meta["label_mapping"])
            self.assertTrue(meta["font"]["embedded_expected"])
            self.assertTrue(meta["font"]["glyph_raster_matches_source"])
            self.assertTrue(meta["font"]["whole_page_raster_matches_source"])
            self.assertTrue(qa["unicode_fonts_embedded"])
            self.assertEqual(qa["missing_glyph_count"], 0)
            self.assertTrue(qa["label_readback_complete"], qa.get("labels_missing_from_readback"))
            self.assertTrue(qa["raster_render_passed"])
            with fitz.open(pdf) as document:
                self.assertIn("雨棚", "".join(page.get_text() for page in document))
                self.assertTrue(any(document.extract_font(row[0])[3] for row in document[0].get_fonts() if row[2] == "Type0"))

    def test_cff_wrong_glyph_raster_is_rejected_despite_valid_cmap(self):
        from io import BytesIO
        from fontTools.ttLib import TTFont
        from fontTools import subset
        font, _ = discover_font()
        if not font:
            self.skipTest("No embeddable CJK font")
        f = TTFont(BytesIO(font.buffer), recalcTimestamp=False)
        if "CFF " not in f:
            self.skipTest("CID-keyed CFF-specific regression")
        text = "项目 / PROJECT: 雨棚铝板深化"
        sub = subset.Subsetter()  # deliberately unsafe GID renumbering
        sub.populate(text=text)
        sub.subset(f)
        buffer = BytesIO()
        f.save(buffer)
        f.close()
        # cmap coverage/ToUnicode alone cannot distinguish this corrupted rendering.
        self.assertFalse(verify_font_raster(font.buffer, buffer.getvalue(), text))

    def test_unembedded_cid_font_is_not_accepted_as_portable_pdf(self):
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unembedded.pdf"
            c = canvas.Canvas(str(path))
            c.setFont("STSong-Light", 12)
            c.drawString(30, 700, "雨棚铝板")
            c.save()
            check = _pdf_preflight(path, set(), 1)
            self.assertFalse(check["unicode_fonts_embedded"])

    def test_dxf_has_ascii_marks_source_mapping_and_actual_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "engineering.dxf"
            meta = engineering_dxf(self.ir, path)
            check = _dxf_preflight(path, {"A-TEXT", "A-DIM"})
            self.assertTrue(check["ascii_display_text_only"])
            self.assertTrue(check["raster_preview"]["passed"])
            texts = [entity.dxf.text for entity in ezdxf.readfile(path).modelspace().query("TEXT")]
            self.assertIn(stable_display_id("顶板-甲-01"), texts)
            self.assertIn(stable_display_id("顶板-乙-01"), texts)
            self.assertFalse(meta["label_mapping"]["untranslated_labels"])
            # The same renderer cannot turn arbitrary CJK STYLE text into a
            # portability claim merely because this machine happens to have it.
            doc = ezdxf.new()
            doc.modelspace().add_text("原始中文标签", height=2)
            bad = Path(tmp) / "raw-cjk.dxf"
            doc.saveas(bad)
            self.assertFalse(_dxf_preflight(bad, set())["ascii_display_text_only"])


if __name__ == "__main__":
    unittest.main()
