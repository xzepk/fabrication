"""Real OCCT/STEP/DXF adapter regressions; no fake adapter or live Rhino claims.

Run: PYTHONDONTWRITEBYTECODE=1 <venv>/bin/python -m unittest discover \
  -s adapters/cladding -p 'test_*.py' -v
"""
from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[2] / "cladding-delivery"
spec = importlib.util.spec_from_file_location("cladding_review_adapter", HERE / "run.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def envelope(components=None):
    document, session = str(uuid.uuid4()), str(uuid.uuid4())
    snapshot_hash = "A"*64
    request = {
        "protocolVersion": 1, "jobId": str(uuid.uuid4()),
        "expected": {"documentId": document, "sessionId": session, "revision": 4, "snapshotHash": snapshot_hash},
        "snapshot": {"documentId": document, "sessionId": session, "revision": 4, "units": "Millimeters", "tolerance": 0.01, "entities": [], "issues": [], "snapshotHash": snapshot_hash},
        "sourceMode": "explicit_design", "selectedEntityIds": [], "sources": [],
        "components": components or [plate()], "targets": ["step", "drawings", "bom", "nesting"], "stock": None,
        "evidence": {"sourceDrawingSha256": None, "designBasis": "Explicit test dimensions, not a production drawing", "assumptions": ["No holes or bends"]},
    }
    return {"requestHash": "B"*64, "inputSnapshotHash": snapshot_hash, "jobHash": "C"*64,
            "ruleVersion": a.rule_version(), "skillVersion": "3.1.0",
            "skillSourceHash": a.sha256(SKILL/"MANIFEST.sha256"), "request": request}


def plate(cid="P-001", plane="XY"):
    return {"entityId": cid, "displayLabel": "入口雨棚铝板 一", "originMM": {"x": 1234.5, "y": -876.25, "z": 9123},
            "widthMM": 120.5, "heightMM": 240.25, "thicknessMM": 3, "material": "铝", "grade": "3003", "densityKgM3": 2730,
            "quantity": 1, "sourceEntityIds": [], "features": [], "geometryType": "planar_plate", "plane": plane,
            "measurements": [{"field": "widthMM", "designValueMM": 120, "measuredValueMM": 120.5, "usedValueMM": 120.5, "adoptionBasis": "Test survey evidence"}]}


class ValidationTests(unittest.TestCase):
    def test_strict_json_rejects_nan_infinity_and_duplicate_keys(self):
        for raw in ('{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":1,"x":2}', '{"x":{"y":1,"y":2}}'):
            with self.subTest(raw=raw), self.assertRaises(a.AdapterError):
                a.strict_json(raw)

    def test_unsupported_features_types_and_fields_rejected(self):
        changes = [("features", ["holes"]), ("features", ["folds"]), ("features", {}), ("geometryType", "rect_tube"),
                   ("holes", []), ("folds", [{"angle": 90}]), ("unknown", 1), ("plane", "oblique")]
        for k,v in changes:
            e = envelope(); e["request"]["components"][0][k] = v
            with self.subTest(k=k,v=v), self.assertRaises(a.AdapterError):
                a.validate_envelope(e)

    def test_numeric_bools_and_nonfinite_rejected(self):
        for k in ("widthMM", "heightMM", "thicknessMM", "densityKgM3", "quantity"):
            for v in (True, False, float("nan"), float("inf"), -1, 0):
                e = envelope(); e["request"]["components"][0][k] = v
                with self.subTest(k=k,v=v), self.assertRaises(a.AdapterError):
                    a.validate_envelope(e)

    def test_bounds_units_and_quantity(self):
        for key,val in (("widthMM",100001),("quantity",2),("thicknessMM",130),("densityKgM3",30001)):
            e = envelope(); e["request"]["components"][0][key] = val
            with self.subTest(key=key), self.assertRaises(a.AdapterError): a.validate_envelope(e)
        e = envelope(); e["request"]["snapshot"]["units"] = "Meters"
        with self.assertRaises(a.AdapterError): a.validate_envelope(e)

    def test_source_mode_unknown_root_and_target_rejected(self):
        for mode in ("automatic", "", "dwg"):
            e = envelope(); e["request"]["sourceMode"] = mode
            with self.assertRaises(a.AdapterError): a.validate_envelope(e)
        e = envelope(); e["arbitraryExecutable"] = "/bin/sh"
        with self.assertRaises(a.AdapterError): a.validate_envelope(e)
        e = envelope(); e["request"]["targets"].pop()
        with self.assertRaises(a.AdapterError): a.validate_envelope(e)

    def test_measurement_preservation_and_adoption_validation(self):
        e = envelope(); a.validate_envelope(e)
        e["request"]["components"][0]["measurements"][0]["usedValueMM"] = 120
        with self.assertRaises(a.AdapterError): a.validate_envelope(e)
        e = envelope(); e["request"]["components"][0]["measurements"][0]["adoptionBasis"] = ""
        with self.assertRaises(a.AdapterError): a.validate_envelope(e)

    def test_duplicate_and_case_collision_ids(self):
        for cid in ("P-001", "p-001"):
            e = envelope([plate(),plate(cid)])
            with self.assertRaises(a.AdapterError): a.validate_envelope(e)

    def test_snapshot_and_rule_revision_binding(self):
        for k in ("inputSnapshotHash", "ruleVersion", "skillVersion"):
            e = envelope(); e[k] = "D"*64
            with self.subTest(key=k), self.assertRaises(a.AdapterError): a.validate_envelope(e)
        e = envelope(); e["request"]["expected"]["revision"] = 3
        with self.assertRaises(a.AdapterError): a.validate_envelope(e)

    def test_null_stock_and_unconfirmed_stock_no_fabricated_placement(self):
        e = envelope(); a.load_skill(SKILL,e)
        canonical = [a.canonical_component(c,e) for c in e["request"]["components"]]
        n = a.nesting(e,canonical)
        self.assertEqual(n["nestingStatus"],"NOT_CONFIGURED"); self.assertIsNone(n["stock"]); self.assertEqual(n["sheets"],[])
        e["request"]["stock"] = {"widthMM":1000,"heightMM":2000,"gapMM":3,"edgeMarginMM":10,"processConfirmed":False}
        n = a.nesting(e,canonical); self.assertEqual(n["nestingStatus"],"REVIEW"); self.assertEqual(n["statusReason"],"PROCESS_UNCONFIRMED"); self.assertEqual(n["sheets"],[])

    def test_material_thickness_nesting_groups_and_unplaced(self):
        e = envelope([plate(),plate("P-2")]); e["request"]["components"][1]["thicknessMM"] = 4
        e["request"]["stock"] = {"widthMM":1000,"heightMM":2000,"gapMM":3,"edgeMarginMM":10,"processConfirmed":True}
        a.load_skill(SKILL,e)
        canonical = [a.canonical_component(c,e) for c in e["request"]["components"]]
        n = a.nesting(e,canonical); self.assertEqual(n["nestingStatus"],"REVIEW"); self.assertEqual(len(n["batches"]),2)
        e["request"]["stock"]["widthMM"] = 25
        self.assertEqual(a.nesting(e,canonical)["nestingStatus"],"BLOCKED")

    def test_selected_managed_source_correspondence(self):
        e = envelope(); r=e["request"]; r["sourceMode"]="selected_managed"; r["selectedEntityIds"]=["SRC-1"]
        r["sources"]=[{"entityId":"SRC-1","fingerprint":"F"*64,"boxMM":{"origin":{"x":1234.5,"y":-876.25,"z":9123},"width":120,"depth":240.25,"height":3}}]
        r["snapshot"]["entities"]=[{"rhinoId":str(uuid.uuid4()),"entityId":"SRC-1","fingerprint":"F"*64,"geometryJson":"{}","attributesJson":"{}","kind":"box","isValid":True}]
        r["components"][0]["sourceEntityIds"]=["SRC-1"]
        a.validate_envelope(e)
        r["sources"][0]["fingerprint"]="G"*64
        with self.assertRaises(a.AdapterError): a.validate_envelope(e)

    def test_drawings_never_mislabel_snapshot_hash_as_original_source(self):
        e = envelope(); c = a.canonical_component(e["request"]["components"][0],e)
        self.assertIsNone(c["source"]["drawing_sha256"])
        self.assertEqual(c["metadata"]["rhino_snapshot_hash"],e["inputSnapshotHash"])
        e["request"]["evidence"]["sourceDrawingSha256"] = "D"*64
        self.assertEqual(a.canonical_component(e["request"]["components"][0],e)["source"]["drawing_sha256"],"D"*64)

    def test_selected_remeasurement_uses_design_box_not_adopted_box(self):
        for plane in ("XY","XZ","YZ"):
            e=envelope([plate(plane=plane)]);r=e["request"];c=r["components"][0]
            r["sourceMode"]="selected_managed";r["selectedEntityIds"]=["SRC-1"];c["sourceEntityIds"]=["SRC-1"]
            design=copy.deepcopy(c);design["widthMM"]=120;dims=a.world_dimensions(design)
            box={"origin":copy.deepcopy(c["originMM"]),"width":dims[0],"depth":dims[1],"height":dims[2]}
            r["sources"]=[{"entityId":"SRC-1","fingerprint":"F"*64,"boxMM":box}]
            r["snapshot"]["entities"]=[{"rhinoId":str(uuid.uuid4()),"entityId":"SRC-1","fingerprint":"F"*64,"geometryJson":"{}","attributesJson":"{}","kind":"box","isValid":True}]
            with self.subTest(plane=plane): a.validate_envelope(e)
            r["sources"][0]["boxMM"]["origin"]["x"]+=1
            with self.subTest(plane=plane),self.assertRaises(a.AdapterError):a.validate_envelope(e)

    def test_independent_skill_source_hash_and_unlisted_code_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"skill";shutil.copytree(SKILL,root)
            e=envelope();(root/"src/cladding_delivery/__init__.py").write_text("# changed")
            with self.assertRaises(a.AdapterError):a.load_skill(root,e)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"skill";shutil.copytree(SKILL,root)
            e=envelope();(root/"src/cladding_delivery/untrusted.py").write_text("# added")
            with self.assertRaises(a.AdapterError):a.load_skill(root,e)

    @unittest.skipIf(os.name=="nt","symlink creation requires Windows privilege")
    def test_linked_independent_skill_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"skill";shutil.copytree(SKILL,root)
            (root/"MANIFEST.sha256").unlink();(root/"MANIFEST.sha256").symlink_to(SKILL/"MANIFEST.sha256")
            with self.assertRaises(a.AdapterError):a.load_skill(root,envelope())

    def test_nested_unknown_properties_rejected(self):
        for container in ("expected","snapshot","evidence","stock"):
            e=envelope()
            if container=="stock":e["request"]["stock"]={"widthMM":1000,"heightMM":2000,"gapMM":3,"edgeMarginMM":10,"processConfirmed":True}
            e["request"][container]["unknown"]="not permitted"
            with self.subTest(container=container),self.assertRaises(a.AdapterError):a.validate_envelope(e)


    def test_rule_binding_covers_capabilities_schema_and_script(self):
        baseline=a.rule_version()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ("run.py","capabilities.json","request.schema.json"):
                shutil.copy2(HERE/name,root/name)
            with mock.patch.object(a,"__file__",str(root/"run.py")):
                self.assertEqual(a.rule_version(),baseline)
                with (root/"request.schema.json").open("a") as f:f.write("\n")
                self.assertNotEqual(a.rule_version(),baseline)
                caps=json.loads((root/"capabilities.json").read_text());caps["manufacturingRelease"]=True
                (root/"capabilities.json").write_text(json.dumps(caps))
                with self.assertRaises(a.AdapterError):a.rule_version()

    def test_dimensions_preserve_canopy_millimetre_precision_in_drawing_text(self):
        import ezdxf
        c=plate();c.update(widthMM=2084.634,heightMM=1182.001,thicknessMM=3.125)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"review.dxf"
            a.write_review_dxf(path,c,"TP-01-01")
            texts=" | ".join(e.dxf.text for e in ezdxf.readfile(path).modelspace().query("TEXT"))
            for dimension in ("2084.634","1182.001","3.125"):
                self.assertIn(dimension,texts)
                self.assertIn(dimension,a.review_svg(c,"TP-01-01"))

    def test_svg_thick_and_extreme_aspects_stay_in_canvas(self):
        for w,h,t in ((100,100,100),(100000,100000,100000),(0.02,100000,0.02),(100000,0.02,0.02),(120,240,3)):
            c=plate();c.update(widthMM=w,heightMM=h,thicknessMM=t)
            doc=ET.fromstring(a.review_svg(c,"P-001"))
            views={x.attrib["id"]:x for x in doc.iter() if x.tag.endswith("rect") and "id" in x.attrib}
            self.assertEqual(set(views),{"top","front","right"})
            for view in views.values():
                x,y,width,height=(float(view.attrib[k]) for k in ("x","y","width","height"))
                with self.subTest(dimensions=(w,h,t),view=view.attrib["id"]):
                    self.assertGreater(width,0);self.assertGreater(height,0)
                    self.assertLessEqual(x+width,975);self.assertLessEqual(y+height,632)
            self.assertTrue(a.review_svg(c,"P-001").isascii())


    def test_assembly_projection_all_world_corners_fit(self):
        components=[plate("P-XY","XY"),plate("P-XZ","XZ"),plate("P-YZ","YZ")]
        components[0]["originMM"]={"x":-10000000,"y":10000000,"z":-10000000}
        components[1]["originMM"]={"x":10000000,"y":-10000000,"z":10000000}
        for box in a.assembly_layout(components):
            self.assertEqual(len(box["points"]),8)
            for x,y in box["points"]:
                self.assertGreaterEqual(x,59.99999);self.assertLessEqual(x,1340.00001)
                self.assertGreaterEqual(y,99.99999);self.assertLessEqual(y,730.00001)



class RealOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="rhino-cladding-python-")
        cls.root = Path(cls.temp.name)
        cls.output = cls.root / "baseline"
        cls.e = envelope([plate("P:XY","XY"),plate("P-XZ","XZ"),plate("P-YZ","YZ")])
        with a.silence_native_stdout():
            cls.manifest = a.run(SKILL,cls.e,cls.output)
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def clone(self):
        root = self.root / str(uuid.uuid4()); shutil.copytree(self.output,root); return root
    def refresh_hash(self,root,path):
        manifest = a.read_json(root/"manifest.json")
        for entry in manifest["artifacts"]:
            if entry["path"]==path:
                entry["sha256"]=a.sha256(root/path);entry["bytes"]=(root/path).stat().st_size
        (root/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")

    def test_all_orientations_have_exact_translated_world_bounds(self):
        reports = a.read_json(self.output/"readback.json")["components"]
        for component,report in zip(self.e["request"]["components"],reports):
            self.assertEqual(report["measured"]["solidCount"],1)
            for actual,wanted in zip(report["measured"]["bboxMM"],a.world_dimensions(component)):
                self.assertAlmostEqual(actual,wanted,places=5)
            for actual,wanted in zip(report["measured"]["bboxMinMM"],component["originMM"].values()):
                self.assertAlmostEqual(actual,wanted,places=5)

    def test_chinese_mapping_ascii_drawings_and_source_surveys(self):
        labels = a.read_json(self.output/"label_map.json")["labels"]
        self.assertEqual(labels[0]["display_label"],"入口雨棚铝板 一")
        self.assertTrue(labels[0]["machine_id"].startswith("C-"))
        for entry in labels:
            svg=(self.output/"drawings"/(entry["machine_id"]+".svg")).read_text("ascii")
            self.assertIn(entry["machine_id"],svg)
        snapshot = a.read_json(self.output/"input_snapshot.json")
        self.assertEqual(snapshot,self.e)
        bom = a.read_json(self.output/"bom.json")
        self.assertEqual(bom["rows"][0]["measurements"],self.e["request"]["components"][0]["measurements"])
        self.assertAlmostEqual(bom["rows"][0]["theoretical_weight_kg_total"],120.5*240.25*3*1e-9*2730)

    def test_manifest_verifies_complete_real_outputs(self):
        with a.silence_native_stdout(): result=a.verify_output(self.output,self.e)
        self.assertEqual(result["status"],"REVIEW"); self.assertFalse(result["manufacturingRelease"])
        self.assertEqual(result["releaseDecision"],"NOT_RELEASED"); self.assertEqual(result["nestingStatus"],"NOT_CONFIGURED")
        self.assertEqual(len(result["artifacts"]),23)

    def test_step_tamper_with_updated_hash_fails_geometric_readback(self):
        import cadquery as cq
        root=self.clone(); rel=next(x["path"] for x in self.manifest["artifacts"] if x["kind"]=="model-step")
        with a.silence_native_stdout(): cq.exporters.export(cq.Workplane("XY").box(1,2,3),str(root/rel))
        self.refresh_hash(root,rel)
        with self.assertRaises(a.AdapterError), a.silence_native_stdout(): a.verify_output(root,self.e)

    def test_flat_tamper_with_updated_hash_fails_readback(self):
        import ezdxf
        root=self.clone();rel=next(x["path"] for x in self.manifest["artifacts"] if x["kind"]=="blank-dxf")
        d=ezdxf.readfile(root/rel);d.units=6;d.saveas(root/rel);self.refresh_hash(root,rel)
        with self.assertRaises(a.AdapterError), a.silence_native_stdout():a.verify_output(root,self.e)

    def test_forged_readback_bom_labels_and_svg_rejected(self):
        for rel in ("readback.json","bom.json","label_map.json"):
            root=self.clone();data=a.read_json(root/rel);data["requestHash"]="E"*64
            (root/rel).write_text(json.dumps(data),encoding="utf-8");self.refresh_hash(root,rel)
            with self.subTest(rel=rel), self.assertRaises(a.AdapterError), a.silence_native_stdout():a.verify_output(root,self.e)
        root=self.clone();rel=next(x["path"] for x in self.manifest["artifacts"] if x["kind"]=="drawing-svg")
        (root/rel).write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>bad()</script></svg>');self.refresh_hash(root,rel)
        with self.assertRaises(a.AdapterError), a.silence_native_stdout():a.verify_output(root,self.e)

    def test_missing_additional_and_traversal_artifacts_rejected(self):
        root=self.clone();(root/"bom.csv").unlink()
        with self.assertRaises(a.AdapterError):a.verify_output(root,self.e)
        root=self.clone();(root/"extra.txt").write_text("unmanifested")
        with self.assertRaises(a.AdapterError):a.verify_output(root,self.e)
        root=self.clone();m=a.read_json(root/"manifest.json");m["artifacts"][0]["path"]="../secret"
        (root/"manifest.json").write_text(json.dumps(m))
        with self.assertRaises(a.AdapterError):a.verify_output(root,self.e)

    @unittest.skipIf(os.name=="nt","symlink creation requires Windows privilege")
    def test_symlink_and_hardlink_rejected(self):
        root=self.clone();(root/"bom.csv").unlink();(root/"bom.csv").symlink_to(self.output/"bom.csv")
        with self.assertRaises(a.AdapterError):a.verify_output(root,self.e)
        root=self.clone();(root/"bom.csv").unlink();os.link(self.output/"bom.csv",root/"bom.csv")
        try:
            with self.assertRaises(a.AdapterError):a.verify_output(root,self.e)
        finally:(root/"bom.csv").unlink()

    def test_mixed_revision_and_production_release_rejected(self):
        for field,value in (("jobHash","F"*64),("manufacturingRelease",True),("releaseDecision","APPROVED_FOR_PRODUCTION")):
            root=self.clone();m=a.read_json(root/"manifest.json");m[field]=value
            (root/"manifest.json").write_text(json.dumps(m))
            with self.subTest(field=field),self.assertRaises(a.AdapterError):a.verify_output(root,self.e)

    def test_partial_failure_leaves_no_completion_manifest(self):
        root=self.root/str(uuid.uuid4())
        with mock.patch.object(a,"world_step_readback",side_effect=a.AdapterError("injected readback failure")):
            with self.assertRaises(a.AdapterError),a.silence_native_stdout():a.run(SKILL,envelope(),root)
        self.assertFalse((root/"manifest.json").exists())
        with self.assertRaises(a.AdapterError),a.silence_native_stdout():a.run(SKILL,envelope(),root)

    def test_existing_output_is_not_overwritten(self):
        before=a.sha256(self.output/"manifest.json")
        with self.assertRaises(a.AdapterError),a.silence_native_stdout():a.run(SKILL,self.e,self.output)
        self.assertEqual(a.sha256(self.output/"manifest.json"),before)

    def test_cli_stdout_one_status_json_and_generic_stderr(self):
        req=self.root/(str(uuid.uuid4())+".json");req.write_text(json.dumps(envelope()),encoding="utf-8")
        output=self.root/str(uuid.uuid4())
        p=subprocess.run([sys.executable,str(HERE/"run.py"),"--skill-root",str(SKILL),"--request",str(req),"--output",str(output)],capture_output=True,text=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(len(p.stdout.strip().splitlines()),1)
        self.assertEqual(json.loads(p.stdout)["status"],"REVIEW")
        broken=envelope();broken["request"]["components"][0]["features"]=["folds"];req.write_text(json.dumps(broken))
        p=subprocess.run([sys.executable,str(HERE/"run.py"),"--skill-root",str(SKILL),"--request",str(req),"--output",str(self.root/str(uuid.uuid4()))],capture_output=True,text=True,timeout=60)
        self.assertEqual(p.returncode,2);self.assertEqual(json.loads(p.stdout)["status"],"BLOCKED")
        self.assertNotIn(str(self.root),p.stderr)

    def test_rehashed_numeric_boolean_alias_is_rejected(self):
        root=self.clone();data=a.read_json(root/"bom.json");data["rows"][0]["quantity"]=True
        (root/"bom.json").write_text(json.dumps(data));self.refresh_hash(root,"bom.json")
        with self.assertRaises(a.AdapterError),a.silence_native_stdout():a.verify_output(root,self.e)

    def test_output_file_and_total_limits_are_enforced(self):
        for name,limit in (("MAX_FILES",2),("MAX_TOTAL_BYTES",200),("MAX_FILE_BYTES",100)):
            with self.subTest(name=name),mock.patch.object(a,name,limit),self.assertRaises(a.AdapterError):a.verify_output(self.output,self.e)
        root=self.clone();(root/"unexpected-empty-directory").mkdir()
        with self.assertRaises(a.AdapterError):a.verify_output(root,self.e)

    def test_real_canopy_56_nominal_skin_regression(self):
        fixture_path=HERE.parents[1]/"examples/canopy-reference-plates.json"
        fixture=json.loads(fixture_path.read_text(encoding="utf-8"))
        e=envelope(fixture["components"]);e["request"]["evidence"]=fixture["evidence"]
        self.assertEqual(len(e["request"]["components"]),56)
        self.assertEqual(sum(c["plane"]=="XY" for c in e["request"]["components"]),42)
        self.assertEqual(sum(c["plane"]=="XZ" for c in e["request"]["components"]),14)
        root=self.root/str(uuid.uuid4())
        with a.silence_native_stdout():m=a.run(SKILL,e,root)
        self.assertEqual(len(m["previewPlates"]),56);self.assertEqual(len(m["artifacts"]),288)
        self.assertEqual(m["nestingStatus"],"NOT_CONFIGURED");self.assertFalse(m["manufacturingRelease"])
        actual=a.read_json(root/"bom.json")["rows"]
        expected=sum(c["widthMM"]*c["heightMM"]*c["thicknessMM"]*c["densityKgM3"]*1e-9 for c in e["request"]["components"])
        self.assertAlmostEqual(sum(row["theoretical_weight_kg_total"] for row in actual),expected,places=5)
        self.assertEqual(a.read_json(root/"input_snapshot.json")["request"]["evidence"],fixture["evidence"])
        assembly=(root/"assembly-review.svg").read_text("ascii")
        self.assertIn(e["inputSnapshotHash"],assembly);self.assertIn("NOT RELEASED",assembly)
        doc=ET.fromstring(assembly);polygons=[x for x in doc.iter() if x.tag.endswith("polygon")]
        self.assertEqual(len(polygons),56*3)
        self.assertEqual(len({x.attrib["data-part"] for x in polygons}),56)
        for polygon in polygons:
            for xy in polygon.attrib["points"].split():
                x,y=map(float,xy.split(","));self.assertTrue(59.99999<=x<=1340.00001 and 99.99999<=y<=730.00001)
        report=a.read_json(root/"readback.json")
        self.assertEqual(report["assemblySha256"],a.sha256(root/"assembly-review.svg"))

    def test_rehashed_assembly_tamper_rejected(self):
        root=self.clone();path=root/"assembly-review.svg"
        path.write_text(path.read_text().replace("NOT RELEASED","RELEASED"))
        self.refresh_hash(root,"assembly-review.svg")
        with self.assertRaises(a.AdapterError):a.verify_output(root,self.e)



if __name__=="__main__":unittest.main()
