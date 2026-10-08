#!/usr/bin/env python3
"""Bounded, REVIEW-only bridge to the independent cladding-delivery OCCT library.

The trusted Host supplies all three CLI paths and validates Rhino context. No path,
code, executable, provider, import name, or network endpoint comes from request JSON.
The independent skill's CLI/human-confirmation pipeline is deliberately not invoked:
this adapter calls its deterministic library primitives and makes no gate approvals.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import uuid

sys.dont_write_bytecode = True
PROTOCOL = 1
RULE_PREFIX = "rhino-cladding-planar-v1:"
SKILL_VERSION = "3.1.0"
MAX_FILES = 1000
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_REQUEST_BYTES = 8 * 1024 * 1024
BINDING = ("requestHash", "inputSnapshotHash", "jobHash", "ruleVersion", "skillVersion", "skillSourceHash")
WARNINGS = [
    "REVIEW ONLY. No manufacturing release or human scope/survey approval is implied.",
    "Only axis-aligned plain rectangular planar plates are supported. Holes, folds, returns, tubes, notches, joints and other features are rejected.",
    "Flat DXF CUT is a geometric review contour; INFO is identification only. No CNC/toolpath, kerf, bend allowance or process qualification is supplied.",
    "ASCII machine IDs are used in drawings. Original labels are preserved reversibly in label_map.json; Chinese glyph rendering is not claimed.",
]
ENTITY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
HASH_RE = re.compile(r"[A-Fa-f0-9]{64}\Z")


class AdapterError(ValueError):
    """Fail-closed validation or artifact acceptance failure."""


def require(condition, message):
    if not condition:
        raise AdapterError(message)


def same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x,y) for x,y in zip(a,b))
    return a == b


def exact(obj, required, optional=()):
    require(type(obj) is dict, "expected JSON object")
    keys = set(obj)
    require(set(required) <= keys and keys <= set(required) | set(optional), "missing or unsupported JSON fields")


def string(value, maximum=128):
    require(type(value) is str and 0 < len(value) <= maximum and value.strip() == value,
            "invalid string")
    require(not any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value), "control character in string")
    return value


def entity_id(value):
    require(type(value) is str and ENTITY_RE.fullmatch(value), "invalid engineering entity ID")
    return value


def number(value, maximum, *, minimum=0, inclusive=False):
    require(type(value) in (int, float) and math.isfinite(value), "non-finite or nonnumeric input")
    require((value >= minimum if inclusive else value > minimum) and value <= maximum, "number outside bounds")
    return value


def point(value):
    exact(value, ("x", "y", "z"))
    for v in value.values():
        number(v, 10000000, minimum=-10000000, inclusive=True)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON property")
            result[key] = value
        return result
    def constant(_):
        raise AdapterError("non-finite JSON constant")
    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError) as exc:
        raise AdapterError("invalid JSON") from exc
    def check(v, depth=0):
        require(depth <= 32, "JSON depth exceeded")
        if isinstance(v, dict):
            for x in v.values():
                check(x, depth+1)
        elif isinstance(v, list):
            for x in v:
                check(x, depth+1)
        elif type(v) is float:
            require(math.isfinite(v), "non-finite JSON number")
    check(value)
    return value


def read_json(path):
    require(path.stat().st_size <= MAX_FILE_BYTES, "JSON file too large")
    return strict_json(path.read_text(encoding="utf-8-sig"))


def write_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    require(len(data) <= MAX_FILE_BYTES, "JSON output too large")
    with path.open("xb") as f:
        f.write(data)


def list_of(value, maximum=128):
    require(type(value) is list and len(value) <= maximum, "invalid or excessive array")
    return value


def unique_ids(value):
    values = list_of(value)
    for v in values:
        entity_id(v)
    require(len({v.casefold() for v in values}) == len(values), "duplicate or case-colliding identity")
    return values


def guid(value):
    string(value, 36)
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise AdapterError("invalid GUID") from exc
    require(str(parsed) == value.lower() and parsed.int != 0, "invalid GUID")


def rule_version():
    root = clean_path(Path(__file__).absolute().parent)
    names = ["capabilities.json", "request.schema.json", "run.py"]
    caps = read_json(clean_path(root / "capabilities.json"))
    require(caps.get("skillId") == "cladding-delivery" and caps.get("skillVersion") == SKILL_VERSION,
            "capability skill identity mismatch")
    require(caps.get("ruleBindingFiles") == names and caps.get("manufacturingRelease") is False
            and caps.get("arbitraryCode") is False and caps.get("originalInputOverwrite") is False
            and caps.get("reviewStatus") == "REVIEW" and caps.get("releaseDecision") == "NOT_RELEASED"
            and caps.get("rulePolicy") == RULE_PREFIX[:-1], "unsafe capability declaration")
    require(caps.get("geometry") == ["planar_plate"] and caps.get("planes") == ["XY", "XZ", "YZ"]
            and caps.get("requiredTargets") == ["step", "drawings", "bom", "nesting"], "unsupported capability declaration")
    schema = read_json(clean_path(root / "request.schema.json"))
    require(schema.get("$id") == "urn:rhino-ai:cladding-review-request:v1" and schema.get("additionalProperties") is False,
            "invalid request schema identity")
    payload = ""
    for name in names:
        path = clean_path(root / name)
        require(path.is_file() and path.stat().st_size <= MAX_FILE_BYTES, "missing rule binding file")
        payload += name + " " + sha256(path) + "\n"
    return RULE_PREFIX + hashlib.sha256(payload.encode("ascii")).hexdigest().upper()


def validate_envelope(envelope):
    exact(envelope, (*BINDING, "request"))
    for k in ("requestHash", "inputSnapshotHash", "jobHash", "skillSourceHash"):
        require(type(envelope[k]) is str and HASH_RE.fullmatch(envelope[k]), "invalid binding hash")
    require(envelope["ruleVersion"] == rule_version(), "adapter rule version mismatch")
    require(envelope["skillVersion"] == SKILL_VERSION, "unsupported skill version")
    r = envelope["request"]
    exact(r, ("protocolVersion", "jobId", "expected", "snapshot", "sourceMode", "selectedEntityIds", "sources", "components", "targets"), ("stock", "evidence"))
    require(type(r["protocolVersion"]) is int and r["protocolVersion"] == PROTOCOL, "unsupported protocol")
    guid(r["jobId"])
    expected, snap = r["expected"], r["snapshot"]
    exact(expected, ("documentId", "sessionId", "revision", "snapshotHash"))
    exact(snap, ("documentId", "sessionId", "revision", "units", "tolerance", "entities", "issues", "snapshotHash"))
    for k in ("documentId", "sessionId"):
        guid(snap[k]); require(snap[k] == expected[k], "context mismatch")
    require(type(snap["revision"]) is int and 0 <= snap["revision"] <= 9223372036854775807 and type(expected["revision"]) is int and snap["revision"] == expected["revision"], "revision mismatch")
    require(expected["snapshotHash"] == snap["snapshotHash"] == envelope["inputSnapshotHash"], "snapshot binding mismatch")
    require(snap["units"] == "Millimeters", "only millimetres are supported")
    tolerance = number(snap["tolerance"], 1)
    require(list_of(snap["issues"], 10000) == [], "snapshot issues block review")
    seen = set()
    for e in list_of(snap["entities"], 10000):
        exact(e, ("rhinoId", "entityId", "fingerprint", "geometryJson", "attributesJson", "kind", "isValid"))
        guid(e["rhinoId"]); entity_id(e["entityId"])
        require(e["entityId"].casefold() not in seen, "snapshot identity collision")
        seen.add(e["entityId"].casefold())
        string(e["fingerprint"], 256); string(e["geometryJson"], 1024*1024); string(e["attributesJson"], 1024*1024); string(e["kind"], 128)
        require(type(e["isValid"]) is bool and e["isValid"], "invalid snapshot entity")
    require(r["sourceMode"] in ("explicit_design", "selected_managed"), "unsupported source mode")
    selection = unique_ids(r["selectedEntityIds"])
    sources = list_of(r["sources"])
    source_ids = []
    for s in sources:
        exact(s, ("entityId", "fingerprint", "boxMM")); entity_id(s["entityId"]); string(s["fingerprint"], 256)
        source_ids.append(s["entityId"])
        b = s["boxMM"]; exact(b, ("origin", "width", "depth", "height")); point(b["origin"])
        for k in ("width", "depth", "height"):
            number(b[k], 100000, minimum=tolerance)
    unique_ids(source_ids)
    require(set(source_ids) == set(selection), "selection/source mismatch")
    if r["sourceMode"] == "explicit_design":
        require(not selection and not sources, "explicit design has selected sources")
    else:
        require(bool(selection) and set(selection) <= {e["entityId"] for e in snap["entities"]}, "selected source missing")
        for s in sources:
            e = next(e for e in snap["entities"] if e["entityId"] == s["entityId"])
            require(s["fingerprint"] == e["fingerprint"], "selected source fingerprint mismatch")
    require(type(r["targets"]) is list and len(r["targets"]) == 4 and set(r["targets"]) == {"step", "drawings", "bom", "nesting"}, "all review targets required")
    components = list_of(r["components"])
    require(bool(components), "no components")
    for c in components:
        exact(c, ("entityId", "displayLabel", "originMM", "widthMM", "heightMM", "thicknessMM", "material", "grade", "densityKgM3", "quantity", "sourceEntityIds"), ("measurements", "features", "geometryType", "plane"))
        entity_id(c["entityId"]); string(c["displayLabel"]); string(c["material"]); string(c["grade"]); point(c["originMM"])
        require(c.get("geometryType", "planar_plate") == "planar_plate", "only planar_plate supported")
        require(c.get("plane", "XY") in ("XY", "XZ", "YZ"), "unsupported plate plane")
        require(c.get("features") is None or type(c["features"]) is list and len(c["features"]) == 0, "unsupported features")
        for k in ("widthMM", "heightMM", "thicknessMM"):
            number(c[k], 100000, minimum=tolerance)
        require(c["thicknessMM"] <= min(c["widthMM"], c["heightMM"]), "invalid plate thickness")
        number(c["densityKgM3"], 30000)
        require(type(c["quantity"]) is int and c["quantity"] == 1, "only explicit single instances supported")
        refs = unique_ids(c["sourceEntityIds"])
        require((not refs) if r["sourceMode"] == "explicit_design" else (len(refs) == 1 and refs[0] in selection), "component source mismatch")
        measured_fields = set()
        measurements = c.get("measurements")
        if measurements is not None:
            for m in list_of(measurements, 3):
                exact(m, ("field", "designValueMM", "measuredValueMM", "usedValueMM", "adoptionBasis"))
                require(m["field"] in ("widthMM", "heightMM", "thicknessMM") and m["field"] not in measured_fields, "invalid measurement field")
                measured_fields.add(m["field"])
                for k in ("designValueMM", "measuredValueMM", "usedValueMM"):
                    number(m[k], 100000, minimum=tolerance)
                require(m["usedValueMM"] == c[m["field"]], "adopted measurement mismatch")
                string(m["adoptionBasis"], 128)
        if r["sourceMode"] == "selected_managed":
            source = next(s for s in sources if s["entityId"] == refs[0])
            design = dict(c)
            for measurement in measurements or []:
                design[measurement["field"]] = measurement["designValueMM"]
            dims = world_dimensions(design)
            expected_box = {"origin": c["originMM"], "width": dims[0], "depth": dims[1], "height": dims[2]}
            require(same(source["boxMM"], expected_box), "selected design geometry differs from captured source")
    unique_ids([c["entityId"] for c in components])
    if r["sourceMode"] == "selected_managed":
        require(sorted(c["sourceEntityIds"][0] for c in components) == sorted(selection), "selection must map one-to-one to components")
    evidence = r.get("evidence")
    if evidence is not None:
        exact(evidence, ("sourceDrawingSha256", "designBasis", "assumptions"))
        require(evidence["sourceDrawingSha256"] is None or type(evidence["sourceDrawingSha256"]) is str and HASH_RE.fullmatch(evidence["sourceDrawingSha256"]), "invalid drawing source hash")
        string(evidence["designBasis"], 128)
        for assumption in list_of(evidence["assumptions"], 64):
            string(assumption, 512)
    stock = r.get("stock")
    if stock is not None:
        exact(stock, ("widthMM", "heightMM", "gapMM", "edgeMarginMM", "processConfirmed"))
        number(stock["widthMM"], 100000); number(stock["heightMM"], 100000)
        number(stock["gapMM"], 100000, inclusive=True); number(stock["edgeMarginMM"], 100000, inclusive=True)
        require(stock["edgeMarginMM"]*2 < min(stock["widthMM"], stock["heightMM"]), "stock margin consumes sheet")
        require(type(stock["processConfirmed"]) is bool, "invalid process confirmation")
    return r


def clean_path(path):
    """Reject symlinks/reparse points along the complete supplied path."""
    path = Path(path)
    require(path.is_absolute(), "absolute trusted path required")
    for ancestor in (path, *path.parents):
        if ancestor.exists() or ancestor.is_symlink():
            st = ancestor.lstat()
            require(not stat.S_ISLNK(st.st_mode) and not (getattr(st, "st_file_attributes", 0) & 0x400), "symlink/reparse path rejected")
    return path


def safe_relative(path):
    require(type(path) is str and 0 < len(path) <= 240 and path.isascii(), "invalid artifact path")
    require(not path.startswith("/") and "\\" not in path and ":" not in path and all(x not in ("", ".", "..") for x in path.split("/")), "unsafe relative path")
    return path


def load_skill(skill_root, envelope):
    root = clean_path(skill_root)
    manifest = clean_path(root / "MANIFEST.sha256")
    require(manifest.is_file() and sha256(manifest) == envelope["skillSourceHash"].upper(), "skill manifest binding mismatch")
    lines = manifest.read_text(encoding="utf-8").splitlines()
    require(0 < len(lines) <= 1000, "invalid skill manifest")
    listed = set()
    for line in lines:
        require(re.fullmatch(r"[0-9a-fA-F]{64}  .+", line), "invalid skill manifest entry")
        digest, rel = line.split("  ", 1); safe_relative(rel)
        require(rel not in listed, "duplicate skill manifest entry"); listed.add(rel)
        p = clean_path(root / rel)
        require(p.is_file() and sha256(p) == digest.upper(), "independent skill source changed")
    actual_source = {p.relative_to(root).as_posix() for p in (root / "src").rglob("*") if p.is_file()}
    require(actual_source == {p for p in listed if p.startswith("src/")}, "unmanifested skill source")
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import cladding_delivery
    require(Path(cladding_delivery.__file__).resolve() == (root / "src/cladding_delivery/__init__.py").resolve(), "wrong skill import")
    require(cladding_delivery.__version__ == envelope["skillVersion"], "skill runtime version mismatch")
    from cladding_delivery.geometry.factory import get_provider
    return get_provider("occt")


def canonical_component(c, envelope):
    return {"id": c["entityId"], "display_label": c["displayLabel"], "kind": "panel", "quantity": 1,
            "geometry": {"type": "planar_plate", "width_mm": c["widthMM"], "height_mm": c["heightMM"], "thickness_mm": c["thicknessMM"]},
            "material": {"name": c["material"], "grade": c["grade"], "density_kg_m3": c["densityKgM3"]},
            "source": {"drawing_sha256": (envelope["request"].get("evidence") or {}).get("sourceDrawingSha256"), "entity_handles": c["sourceEntityIds"]},
            "metadata": {"rhino_snapshot_hash": envelope["inputSnapshotHash"], "source_mode": envelope["request"]["sourceMode"], "origin_mm": c["originMM"], "plane": c.get("plane", "XY"), "measurements": c.get("measurements")}}


def binding(envelope):
    return {"protocolVersion": PROTOCOL, "jobId": envelope["request"]["jobId"], **{k: envelope[k] for k in BINDING}}


def metadata(envelope, **data):
    return {**binding(envelope), "status": "REVIEW", "manufacturingRelease": False, "releaseDecision": "NOT_RELEASED", **data}


def world_dimensions(c):
    w, h, t = (c[k] for k in ("widthMM", "heightMM", "thicknessMM"))
    return {"XY": [w, h, t], "XZ": [w, t, h], "YZ": [t, w, h]}[c.get("plane", "XY")]


def world_shape(local, c):
    if c.get("plane", "XY") == "XZ":
        local = local.rotate((0,0,0), (1,0,0), 90).translate((0,c["thicknessMM"],0))
    elif c.get("plane", "XY") == "YZ":
        local = local.rotate((0,0,0), (1,1,1), 120)
    return local.translate(tuple(c["originMM"][k] for k in ("x", "y", "z")))


def preview_plate(c):
    dims = world_dimensions(c)
    return {"entityId": c["entityId"], "box": {"origin": c["originMM"], "width": dims[0], "depth": dims[1], "height": dims[2]}, "material": c["material"]}


def world_step_readback(path, c):
    import cadquery as cq
    from OCP.BRepCheck import BRepCheck_Analyzer
    shape = cq.importers.importStep(str(path)).val()
    solids = shape.Solids()
    require(BRepCheck_Analyzer(shape.wrapped).IsValid(), "invalid STEP BRep")
    require(len(solids) == 1 and all(s.Shells() and all(sh.Closed() for sh in s.Shells()) for s in solids), "STEP must contain one closed solid")
    box = shape.BoundingBox()
    measured = {"bboxMM": [box.xlen, box.ylen, box.zlen], "bboxMinMM": [box.xmin, box.ymin, box.zmin],
                "volumeMM3": shape.Volume(), "surfaceAreaMM2": shape.Area(), "solidCount": len(solids),
                "closed": True, "brepValid": True}
    w, h, t = (c[k] for k in ("widthMM", "heightMM", "thicknessMM"))
    origin = [c["originMM"][k] for k in ("x", "y", "z")]
    for values, target in ((measured["bboxMM"], world_dimensions(c)), (measured["bboxMinMM"], origin)):
        require(all(math.isfinite(a) and math.isclose(a, b, rel_tol=0, abs_tol=1e-5) for a, b in zip(values, target)), "STEP placement/dimensions differ")
    for key, target in (("volumeMM3", w*h*t), ("surfaceAreaMM2", 2*(w*h+w*t+h*t))):
        require(math.isfinite(measured[key]) and math.isclose(measured[key], target, rel_tol=1e-7, abs_tol=1e-5), "STEP mass properties differ")
    require(len(shape.Faces()) == 6 and all(f.geomType() == "PLANE" for f in shape.Faces()), "STEP is not the supported planar rectangular solid")
    require(solids[0].isInside(tuple(origin[i]+world_dimensions(c)[i]/2 for i in range(3)), 1e-7), "STEP interior probe failed")
    return measured


def rectangle(x, y, w, h):
    return [(x, y), (x+w, y), (x+w, y+h), (x, y+h)]


def review_layout(c, machine):
    w, h, t = (c[k] for k in ("widthMM", "heightMM", "thicknessMM"))
    gap = max(25.0, min(w, h)*0.15)
    rectangles = [("TOP", rectangle(0, 0, w, h)), ("FRONT", rectangle(0, -gap-t, w, t)), ("RIGHT", rectangle(w+gap, 0, t, h))]
    texts = [(machine + " REVIEW - NOT RELEASED; PLATE-LOCAL VIEWS; PLANE " + c.get("plane", "XY"), (0, h+gap)),
             (f"TOP {w:.12g} x {h:.12g} mm", (0, h+gap*0.35)),
             (f"FRONT thickness {t:.12g} mm", (0, -gap*0.7)),
             (f"RIGHT {h:.12g} x {t:.12g} mm", (w+gap, h+gap*0.35))]
    return rectangles, texts, max(2.0, min(w, h)*0.025)


def write_review_dxf(path, c, machine):
    import ezdxf
    doc = ezdxf.new("R2018"); doc.units = 4
    for layer in ("TOP", "FRONT", "RIGHT", "INFO"):
        doc.layers.new(layer)
    rectangles, texts, size = review_layout(c, machine)
    msp = doc.modelspace()
    for layer, points in rectangles:
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
    for text, at in texts:
        msp.add_text(text, height=size, dxfattribs={"layer": "INFO"}).set_placement(at)
    doc.saveas(path)


def review_svg(c, machine):
    """Standalone ASCII, non-scripted orthographic review rendering; not a toolpath."""
    w, h, t = (c[k] for k in ("widthMM", "heightMM", "thicknessMM"))
    scale = min(620/w, 440/h, 850/(w+t), 500/(h+t))
    dw, dh, dt = w*scale, h*scale, max(t*scale, 1)
    fmt = lambda n: format(n, ".12g")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="768" viewBox="0 0 1024 768">\n'
            f'<rect width="1024" height="768" fill="white"/>\n'
            f'<g font-family="sans-serif" fill="#17212b" font-size="18"><text x="35" y="32">{machine} | REVIEW - NOT RELEASED</text>'
            f'<text x="35" y="58">PLATE-LOCAL TOP: {w:.12g} x {h:.12g} mm | thickness: {t:.12g} mm | world plane: {c.get("plane", "XY")}</text>'
            f'<text x="35" y="715">Axis-aligned planar plate. Edge views share top scale; subpixel thickness shown as 1 px.</text>'
            f'<text x="35" y="740">Verify dimensions in STEP / DXF. No fabrication approval or machining allowance.</text></g>\n'
            f'<g fill="#e6eef6" stroke="#203b55" stroke-width="1">'
            f'<rect id="top" x="35" y="85" width="{fmt(dw)}" height="{fmt(dh)}"/>'
            f'<rect id="front" x="35" y="{fmt(130+dh)}" width="{fmt(dw)}" height="{fmt(dt)}"/>'
            f'<rect id="right" x="{fmt(90+dw)}" y="85" width="{fmt(dt)}" height="{fmt(dh)}"/></g>\n'
            f'<g font-family="sans-serif" font-size="14"><text x="35" y="{fmt(115+dh)}">FRONT: {w:.12g} x {t:.12g} mm</text>'
            f'<text x="{fmt(75+dw)}" y="75">RIGHT: {h:.12g} x {t:.12g} mm</text></g>\n</svg>\n')


def assembly_layout(components):
    """Project every actual world-box corner into one bounded isometric viewport."""
    boxes = []
    for index, c in enumerate(components, 1):
        x, y, z = (c["originMM"][k] for k in ("x", "y", "z"))
        w, d, h = world_dimensions(c)
        corners = [(x+dx*w, y+dy*d, z+dz*h) for dz in (0,1) for dy in (0,1) for dx in (0,1)]
        uv = [((px-py)*math.sqrt(3)/2, (px+py)/2-pz) for px,py,pz in corners]
        boxes.append({"index": index, "uv": uv, "depth": x+y+z+(w+d+h)/2, "plane": c.get("plane", "XY")})
    all_points = [point for box in boxes for point in box["uv"]]
    min_u, max_u = min(p[0] for p in all_points), max(p[0] for p in all_points)
    min_v, max_v = min(p[1] for p in all_points), max(p[1] for p in all_points)
    scale = min(1280/(max_u-min_u), 630/(max_v-min_v))
    for box in boxes:
        box["points"] = [(60+(1280-(max_u-min_u)*scale)/2+(u-min_u)*scale,
                           100+(630-(max_v-min_v)*scale)/2+(v-min_v)*scale) for u,v in box.pop("uv")]
    return sorted(boxes, key=lambda box: (box["depth"], box["index"]))


def assembly_svg(components, identities, snapshot_hash):
    height = max(960, 890+math.ceil(len(components)/2)*21)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="{height}" viewBox="0 0 1400 {height}">',
             f'<rect width="1400" height="{height}" fill="white"/>',
             '<g font-family="sans-serif" fill="#17212b"><text x="35" y="35" font-size="25">ASSEMBLY REVIEW - NOT RELEASED</text>',
             f'<text x="35" y="60" font-size="14">Snapshot: {snapshot_hash}</text>',
             f'<text x="35" y="82" font-size="14">{len(components)} individual plates | world millimetres | isometric display | no fabrication approval</text></g>',
             '<g stroke="#203b55" stroke-width="0.7" stroke-linejoin="round">']
    colors = {"XY": "#9dc3e6", "XZ": "#f3bf7a", "YZ": "#a9d0ad"}
    labels = []
    for box in assembly_layout(components):
        points = box["points"]
        # Three axis-aligned faces; all coordinates come from the verified world box.
        for face in ((1,3,7,5), (2,3,7,6), (4,5,7,6)):
            coords = " ".join(f"{points[i][0]:.12g},{points[i][1]:.12g}" for i in face)
            lines.append(f'<polygon data-part="{box["index"]}" points="{coords}" fill="{colors[box["plane"]]}" fill-opacity="0.82"/>')
        cx = sum(points[i][0] for i in (4,5,7,6))/4
        cy = sum(points[i][1] for i in (4,5,7,6))/4
        labels.append(f'<text x="{cx:.12g}" y="{cy:.12g}" text-anchor="middle">{box["index"]}</text>')
    lines += ['</g>', '<g font-family="sans-serif" font-size="10" fill="#102536">', *labels, '</g>',
              '<g font-family="monospace" font-size="13" fill="#17212b">',
              '<text x="35" y="792">Number to collision-safe machine ID. Original identities and Unicode labels: label_map.json</text>']
    for index, identity in enumerate(identities):
        x, y = 35+(index%2)*690, 820+(index//2)*21
        lines.append(f'<text x="{x}" y="{y}">{index+1:03d}: {identity["machine_id"]}</text>')
    lines += [f'<text x="35" y="{height-25}">Nominal plate solids only. STEP / per-part DXF carry dimensions. No holes, folds, returns, joints or CAM.</text>', '</g>', '</svg>', '']
    return "\n".join(lines)


def verify_dxf(path, c, machine, *, flat):
    import ezdxf
    doc = ezdxf.readfile(path)
    require(doc.units == 4 and not doc.audit().has_errors, "invalid DXF or units")
    entities = list(doc.modelspace())
    require(all(e.dxftype() in ("LWPOLYLINE", "TEXT") for e in entities), "unexpected DXF entity")
    polys = [e for e in entities if e.dxftype() == "LWPOLYLINE"]
    text_entities = [e for e in entities if e.dxftype() == "TEXT"]
    if flat:
        expected_polys = [("CUT", rectangle(0, 0, c["widthMM"], c["heightMM"]))]
        expected_texts = [machine]
    else:
        expected_polys, texts, _ = review_layout(c, machine)
        expected_texts = [t[0] for t in texts]
    require(len(polys) == len(expected_polys) and len(text_entities) == len(expected_texts), "DXF entity count mismatch")
    for poly, (layer, pts) in zip(polys, expected_polys):
        require(poly.closed and poly.dxf.layer == layer and poly.dxf.elevation == 0 and poly.dxf.const_width == 0, "invalid DXF contour")
        actual = list(poly.get_points("xyseb"))
        require(len(actual) == 4 and all(math.isclose(a[0], b[0], rel_tol=0, abs_tol=1e-8) and math.isclose(a[1], b[1], rel_tol=0, abs_tol=1e-8) and a[2:] == (0,0,0) for a,b in zip(actual, pts)), "DXF coordinates differ")
    require([e.dxf.text for e in text_entities] == expected_texts and all(e.dxf.layer == "INFO" and e.dxf.text.isascii() for e in text_entities), "DXF ASCII label mismatch")
    return {"units": "mm", "closedContours": len(polys), "asciiLabels": True}


def nesting(envelope, canonical):
    from cladding_delivery.nesting import shelf_nest
    stock = envelope["request"].get("stock")
    if stock is None:
        return metadata(envelope, nestingStatus="NOT_CONFIGURED", stock=None, sheets=[], unplaced=[], reason="No stock supplied; no stock dimensions or process values were assumed.")
    if not stock["processConfirmed"]:
        return metadata(envelope, nestingStatus="REVIEW", statusReason="PROCESS_UNCONFIRMED", stock=stock, sheets=[], unplaced=[], reason="Stock provided but process parameters are unconfirmed; no placement computed.")
    groups = {}
    for c in canonical:
        key = (c["material"]["name"], c["material"]["grade"], c["geometry"]["thickness_mm"])
        groups.setdefault(key, []).append({"id": c["id"], "w": c["geometry"]["width_mm"], "h": c["geometry"]["height_mm"], "qty": 1})
    batches = []
    for (material, grade, thickness), rectangles in groups.items():
        result = shelf_nest(rectangles, stock["widthMM"], stock["heightMM"], stock["gapMM"], stock["edgeMarginMM"])
        batches.append({"material": material, "grade": grade, "thicknessMM": thickness, **result})
    return metadata(envelope, nestingStatus="BLOCKED" if any(b["unplaced"] for b in batches) else "REVIEW", statusReason="UNPLACED" if any(b["unplaced"] for b in batches) else "PLACED_FOR_REVIEW", stock=stock, batches=batches, reason="Unrotated shelf review grouped by material, grade and thickness; not CAM or process approval.")


def csv_text(rows):
    buf = io.StringIO(newline="")
    fields = ["component_id", "machine_id", "display_label", "kind", "geometry_type", "material", "grade", "quantity", "volume_mm3_each", "theoretical_weight_kg_total", "widthMM", "heightMM", "thicknessMM", "originMM", "sourceEntityIds", "measurements"]
    writer = csv.DictWriter(buf, fieldnames=fields); writer.writeheader()
    for row in rows:
        serialized = {}
        for k in fields:
            v = row[k]
            if isinstance(v, (list, dict)) or v is None:
                v = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
            if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")):
                v = "'"+v  # prevent spreadsheet formula execution; exact text is in JSON
            serialized[k] = v
        writer.writerow(serialized)
    return buf.getvalue()


def inventory(root):
    root = clean_path(root)
    require(root.is_dir(), "missing output directory")
    files, total = {}, 0
    for p in root.rglob("*"):
        clean_path(p)
        st = p.lstat()
        if stat.S_ISDIR(st.st_mode):
            continue
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, "nonregular or hardlinked output")
        require(0 < st.st_size <= MAX_FILE_BYTES, "empty or oversized output")
        rel = p.relative_to(root).as_posix(); safe_relative(rel)
        require(rel.casefold() not in {q.casefold() for q in files}, "case-colliding output paths")
        files[rel] = p; total += st.st_size
        require(len(files) <= MAX_FILES and total <= MAX_TOTAL_BYTES, "output limits exceeded")
    return files


def artifact_specs(canonical):
    from cladding_delivery.identity import identity_map
    specs = {name: (kind, None) for name, kind in (("input_snapshot.json", "input"), ("provenance.json", "provenance"), ("label_map.json", "labels"), ("bom.json", "bom"), ("bom.csv", "bom-csv"), ("nesting.json", "nesting"), ("readback.json", "readback"), ("assembly-review.svg", "assembly-svg"))}
    identities = identity_map(canonical)
    for identity in identities:
        m, cid = identity["machine_id"], identity["component_id"]
        for rel, kind in ((f"model/{m}.step", "model-step"), (f"blank/{m}_flat.dxf", "blank-dxf"), (f"blank/{m}.identity.json", "identity"), (f"drawings/{m}.dxf", "drawing-dxf"), (f"drawings/{m}.svg", "drawing-svg")):
            specs[rel] = (kind, cid)
    return specs, identities


def verify_output(root, envelope):
    """Revalidate actual bytes and geometry, even if a tamperer recomputed file hashes.

    Host additionally pins the immutable manifest's hash before preview/apply; this
    function cannot authenticate a caller who replaces both envelope and all files.
    """
    r = validate_envelope(envelope)
    root = clean_path(root)
    canonical = [canonical_component(c, envelope) for c in r["components"]]
    specs, identities = artifact_specs(canonical)
    files = inventory(root)
    require({p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir()} == {"model", "blank", "drawings"}, "unexpected output directories")
    require(set(files) == {*specs, "manifest.json"}, "missing or unexpected output artifact")
    m = read_json(files["manifest.json"])
    exact(m, (*binding(envelope), "status", "manufacturingRelease", "releaseDecision", "nestingStatus", "previewPlates", "artifacts", "warnings"))
    require(all(same(m[k], v) for k, v in binding(envelope).items()), "manifest revision binding mismatch")
    require(m["status"] == "REVIEW" and m["manufacturingRelease"] is False and m["releaseDecision"] == "NOT_RELEASED", "invalid release decision")
    require(m["warnings"] == WARNINGS, "missing limitations")
    require(files["assembly-review.svg"].read_text(encoding="ascii") == assembly_svg(r["components"], identities, envelope["inputSnapshotHash"]), "assembly SVG differs from preview world boxes")
    require(type(m["artifacts"]) is list and len(m["artifacts"]) == len(specs), "artifact count mismatch")
    listed = set()
    for a in m["artifacts"]:
        exact(a, ("path", "sha256", "bytes", "kind", "entityId"))
        rel = safe_relative(a["path"])
        require(rel in specs and rel not in listed, "invalid or duplicate artifact")
        listed.add(rel)
        require((a["kind"], a["entityId"]) == specs[rel], "artifact identity mismatch")
        require(type(a["bytes"]) is int and a["bytes"] == files[rel].stat().st_size and type(a["sha256"]) is str and a["sha256"].upper() == sha256(files[rel]), "artifact checksum mismatch")
    require(same(read_json(files["input_snapshot.json"]), envelope), "input snapshot differs")
    require(same(read_json(files["label_map.json"]), metadata(envelope, labels=identities)), "identity map differs")
    provenance = read_json(files["provenance.json"])
    require(all(same(provenance.get(k), v) for k,v in metadata(envelope).items()), "provenance binding mismatch")
    require(provenance.get("provider") == "occt" and provenance.get("scopeApproval") == "NOT_RECORDED" and provenance.get("surveyApproval") == "NOT_RECORDED" and provenance.get("runtime", {}).get("claddingDelivery") == SKILL_VERSION, "invalid provenance")
    preview, readback, rows = [], [], []
    from cladding_delivery.bom import bom_row
    for c, canon, identity in zip(r["components"], canonical, identities):
        machine = identity["machine_id"]
        step_rel, flat_rel = f"model/{machine}.step", f"blank/{machine}_flat.dxf"
        dxf_rel, svg_rel = f"drawings/{machine}.dxf", f"drawings/{machine}.svg"
        measured = world_step_readback(files[step_rel], c)
        flat_check = verify_dxf(files[flat_rel], c, machine, flat=True)
        draw_check = verify_dxf(files[dxf_rel], c, machine, flat=False)
        require(files[svg_rel].read_text(encoding="ascii") == review_svg(c, machine), "SVG review differs")
        require(read_json(files[f"blank/{machine}.identity.json"]) == identity, "component identity differs")
        row = bom_row(canon, {"volume_mm3": measured["volumeMM3"]})
        row.update({k: c.get(k) for k in ("widthMM", "heightMM", "thicknessMM", "originMM", "sourceEntityIds", "measurements")}); rows.append(row)
        preview.append(preview_plate(c))
        readback.append({"entityId": c["entityId"], "stepSha256": sha256(files[step_rel]), "measured": measured, "flat": flat_check, "drawing": draw_check})
    require(same(m["previewPlates"], preview), "preview geometry differs")
    require(same(read_json(files["readback.json"]), metadata(envelope, method="Independent STEP import, closed-solid/BRep/mass/bounds/faces/interior checks; DXF reread; deterministic SVG", components=readback, assemblySha256=sha256(files["assembly-review.svg"]))), "readback report differs")
    require(same(read_json(files["bom.json"]), metadata(envelope, rows=rows)), "BOM geometry/provenance differs")
    require(files["bom.csv"].read_bytes() == csv_text(rows).encode("utf-8-sig"), "BOM CSV differs")
    expected_nesting = nesting(envelope, canonical)
    require(same(read_json(files["nesting.json"]), expected_nesting) and m["nestingStatus"] == expected_nesting["nestingStatus"], "nesting differs")
    return m


def run(skill_root, envelope, output):
    r = validate_envelope(envelope)
    root = clean_path(output)
    require(not root.exists(), "output must be a new directory")
    require(not root.is_relative_to(Path(skill_root).resolve()), "output cannot be within independent skill")
    root.mkdir(parents=False)
    for d in ("model", "blank", "drawings", "_provider"):
        (root/d).mkdir()
    old_environment = {key: os.environ.get(key) for key in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME", "EZDXF_CONFIG_FILE")}
    try:
        os.environ["XDG_CACHE_HOME"] = str(root / "_provider" / "cache")
        os.environ["XDG_CONFIG_HOME"] = str(root / "_provider" / "config")
        os.environ.pop("EZDXF_CONFIG_FILE", None)
        provider = load_skill(skill_root, envelope)
    finally:
        for key, value in old_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    canonical = [canonical_component(c, envelope) for c in r["components"]]
    specs, identities = artifact_specs(canonical)
    import cadquery as cq
    import ezdxf
    import OCP
    from cladding_delivery.bom import bom_row
    readbacks, rows, preview = [], [], []
    # No manifest is written until every required output is complete and checked.
    for c, canon, identity in zip(r["components"], canonical, identities):
        machine = identity["machine_id"]
        built = provider.build_component(canon, root / "_provider" / machine)
        local = cq.importers.importStep(built["step"]).val()
        moved = world_shape(local, c)
        step = root / "model" / f"{machine}.step"
        cq.exporters.export(moved, str(step))
        measured = world_step_readback(step, c)
        flat = provider.unfold_component(canon, root / "blank")
        flat_check = verify_dxf(Path(flat["dxf"]), c, machine, flat=True)
        drawing = root / "drawings" / f"{machine}.dxf"
        write_review_dxf(drawing, c, machine)
        draw_check = verify_dxf(drawing, c, machine, flat=False)
        (root / "drawings" / f"{machine}.svg").write_text(review_svg(c, machine), encoding="ascii")
        row = bom_row(canon, {"volume_mm3": measured["volumeMM3"]})
        row.update({k: c.get(k) for k in ("widthMM", "heightMM", "thicknessMM", "originMM", "sourceEntityIds", "measurements")}); rows.append(row)
        preview.append(preview_plate(c))
        readbacks.append({"entityId": c["entityId"], "stepSha256": sha256(step), "measured": measured, "flat": flat_check, "drawing": draw_check})
        shutil.rmtree(root / "_provider" / machine)  # only this run's disposable provider files
        inventory(root)
    shutil.rmtree(root / "_provider")
    write_json(root / "input_snapshot.json", envelope)
    write_json(root / "provenance.json", metadata(envelope, provider="occt", sourceMode=r["sourceMode"], scopeApproval="NOT_RECORDED", surveyApproval="NOT_RECORDED", runtime={"python": sys.version.split()[0], "cadquery": cq.__version__, "ocp": getattr(OCP, "__version__", "unknown"), "ezdxf": ezdxf.__version__, "claddingDelivery": SKILL_VERSION}, limitations=WARNINGS))
    write_json(root / "label_map.json", metadata(envelope, labels=identities))
    write_json(root / "bom.json", metadata(envelope, rows=rows))
    (root / "bom.csv").write_bytes(csv_text(rows).encode("utf-8-sig"))
    nest = nesting(envelope, canonical); write_json(root / "nesting.json", nest)
    (root / "assembly-review.svg").write_text(assembly_svg(r["components"], identities, envelope["inputSnapshotHash"]), encoding="ascii")
    write_json(root / "readback.json", metadata(envelope, method="Independent STEP import, closed-solid/BRep/mass/bounds/faces/interior checks; DXF reread; deterministic SVG", components=readbacks, assemblySha256=sha256(root / "assembly-review.svg")))
    files = inventory(root)
    require(set(files) == set(specs), "partial or additional artifacts")
    artifacts = [{"path": p, "sha256": sha256(files[p]), "bytes": files[p].stat().st_size, "kind": specs[p][0], "entityId": specs[p][1]} for p in sorted(specs)]
    write_json(root / "manifest.json", metadata(envelope, nestingStatus=nest["nestingStatus"], previewPlates=preview, artifacts=artifacts, warnings=WARNINGS))
    try:
        return verify_output(root, envelope)
    except Exception:
        # Leave partial evidence, but never a completion manifest after failed acceptance.
        (root / "manifest.json").unlink(missing_ok=True)
        raise


@contextlib.contextmanager
def silence_native_stdout():
    """OCP exporters can write C stdio; reserve CLI stdout for one status JSON."""
    sys.stdout.flush()
    saved = os.dup(1)
    try:
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), 1)
            with contextlib.redirect_stdout(sink):
                yield
    finally:
        os.dup2(saved, 1); os.close(saved)


def main():
    parser = argparse.ArgumentParser(description="Bounded cladding REVIEW adapter")
    parser.add_argument("--skill-root", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        request_path = clean_path(args.request)
        require(request_path.is_file() and request_path.stat().st_size <= MAX_REQUEST_BYTES, "invalid request file")
        envelope = read_json(request_path)
        require(not request_path.is_relative_to(args.output), "request cannot be in output")
        with silence_native_stdout():
            manifest = run(args.skill_root, envelope, args.output)
        print(json.dumps({"status": "REVIEW", "jobId": manifest["jobId"], "manufacturingRelease": False, "releaseDecision": "NOT_RELEASED"}, separators=(",", ":")))
        return 0
    except Exception:
        print("Cladding review rejected: invalid input, unavailable runtime, or artifact verification failure.", file=sys.stderr)
        print('{"status":"BLOCKED","manufacturingRelease":false,"releaseDecision":"NOT_RELEASED"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
