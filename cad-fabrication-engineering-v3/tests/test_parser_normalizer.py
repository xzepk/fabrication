import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ParserNormalizerTests(unittest.TestCase):
    def test_synthetic_acadsharp_normalization_is_fail_closed(self):
        raw = {
            "file": "synthetic.dwg", "library": "3.8.0.0", "success": True,
            "layers": [{"name": "A-PANEL"}], "notifications": [{"message": "proxy object retained"}],
            "blocks": [
                {"name": "*Model_Space", "entities": [
                    {"handle": "10", "type": "LINE", "class": "Line", "owner": "*Model_Space", "layer": "A-PANEL", "invisible": False,
                     "StartPoint": {"X": 0, "Y": 0, "Z": 0}, "EndPoint": {"X": 100, "Y": 0, "Z": 0}},
                    {"handle": "20", "type": "INSERT", "class": "Insert", "owner": "*Model_Space", "layer": "A-PANEL", "invisible": False,
                     "InsertPoint": {"X": 10, "Y": 20, "Z": 0}, "Rotation": 0.0, "XScale": 1.0, "YScale": 1.0, "ZScale": 1.0,
                     "Block": {"handle": "B1", "type": "BlockRecord", "name": "PANEL_BLOCK"}}
                ]}
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "raw.json"; src.write_text(json.dumps(raw), encoding="utf-8")
            out = td / "out"
            cp = subprocess.run(["python", str(ROOT/"scripts"/"normalize_acadsharp_dump.py"), str(src), str(out)], capture_output=True, text=True)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            manifest = json.loads((out/"drawing_manifest.json").read_text())
            self.assertEqual(manifest["entity_count"], 2)
            self.assertFalse(manifest["production_geometry_ready"])
            lines = [json.loads(x) for x in (out/"canonical_entities.jsonl").read_text().splitlines()]
            self.assertEqual(lines[1]["normalization_status"], "INSERT_REQUIRES_TRANSFORM_EXPANSION")
            issues = json.loads((out/"issues.json").read_text())
            self.assertEqual(len(issues), 1)


if __name__ == "__main__":
    unittest.main()
