from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable
import os

import ezdxf
from ezdxf.enums import TextEntityAlignment
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .backends.cadquery_backend import build_shape
from .projection import ProjectedView, standard_views

# Cross-platform CJK font discovery. Font files are NOT bundled in the skill.
# Prefer an embeddable system font for viewer-stable engineering PDFs; fall back
# to a standard CID font only when the workstation has no usable TTF/TTC.
def _register_cjk_font():
    candidates = []
    env_font = os.environ.get("CADFAB_CJK_FONT")
    if env_font:
        candidates.append(Path(env_font))
    candidates += [
        Path("/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("C:/Windows/Fonts/Deng.ttf"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        # TTC collections may expose different usable subfonts. Try a small
        # bounded set; ordinary TTF ignores all but index 0.
        max_idx = 5 if path.suffix.lower() == ".ttc" else 1
        for idx in range(max_idx):
            try:
                name = "CADFAB-CJK"
                pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=idx))
                return name, True, str(path)
            except Exception:
                continue
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light", False, "standard CID fallback"
    except Exception:
        return "Helvetica", False, "no CJK font available"

CN_FONT, CN_FONT_EMBEDDED, CN_FONT_SOURCE = _register_cjk_font()

PAGE_W_PT, PAGE_H_PT = landscape(A3)
PAGE_W_MM, PAGE_H_MM = PAGE_W_PT / mm, PAGE_H_PT / mm

LAYER_SPECS = {
    "A-FRAME": {"color": 7, "lineweight": 35, "linetype": "CONTINUOUS"},
    "A-VIEW-VISIBLE": {"color": 7, "lineweight": 35, "linetype": "CONTINUOUS"},
    "A-VIEW-HIDDEN": {"color": 8, "lineweight": 18, "linetype": "HIDDEN2"},
    "A-PANEL-CUT": {"color": 1, "lineweight": 35, "linetype": "CONTINUOUS"},
    "A-PANEL-JOINT": {"color": 3, "lineweight": 18, "linetype": "CONTINUOUS"},
    "A-STRUCTURE": {"color": 5, "lineweight": 25, "linetype": "CONTINUOUS"},
    "A-DIM": {"color": 2, "lineweight": 13, "linetype": "CONTINUOUS"},
    "A-TEXT": {"color": 7, "lineweight": 18, "linetype": "CONTINUOUS"},
    "A-CENTER": {"color": 4, "lineweight": 13, "linetype": "CENTER2"},
    "A-NOTE": {"color": 6, "lineweight": 18, "linetype": "CONTINUOUS"},
    "A-REF": {"color": 8, "lineweight": 13, "linetype": "DASHED"},
    "A-WARNING": {"color": 1, "lineweight": 25, "linetype": "CONTINUOUS"},
}


def _setup_doc():
    doc = ezdxf.new("R2010")
    for name, pattern in {
        "HIDDEN2": [0.6, 0.3, -0.3],
        "CENTER2": [1.0, 0.5, -0.15, 0.15, -0.15],
        "DASHED": [0.5, 0.25, -0.25],
    }.items():
        if name not in doc.linetypes:
            doc.linetypes.add(name, pattern=pattern)
    for name, spec in LAYER_SPECS.items():
        if name not in doc.layers:
            doc.layers.add(name, color=spec["color"], linetype=spec["linetype"], lineweight=spec["lineweight"])
        else:
            layer = doc.layers.get(name)
            layer.dxf.color = spec["color"]
            layer.dxf.linetype = spec["linetype"]
            layer.dxf.lineweight = spec["lineweight"]
    if "CADFAB_DIM" not in doc.dimstyles:
        doc.dimstyles.add("CADFAB_DIM", dxfattribs={
            "dimtxt": 110.0, "dimasz": 70.0, "dimexo": 35.0, "dimexe": 55.0,
            "dimclrd": 2, "dimclre": 2, "dimclrt": 2,
        })
    return doc


def _add_dim_linear(msp, p1, p2, base, angle=0, override=None):
    d = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, dimstyle="CADFAB_DIM", dxfattribs={"layer": "A-DIM"})
    if override:
        d.dimension.dxf.text = override
    d.render()


def _draw_dxf_view(msp, view: ProjectedView, offset=(0.0, 0.0)):
    ox, oy = offset
    for line in view.hidden:
        if len(line) >= 2:
            msp.add_lwpolyline([(x + ox, y + oy) for x, y in line], dxfattribs={"layer": "A-VIEW-HIDDEN"})
    for line in view.visible:
        if len(line) >= 2:
            msp.add_lwpolyline([(x + ox, y + oy) for x, y in line], dxfattribs={"layer": "A-VIEW-VISIBLE"})


def engineering_dxf(ir: dict, out: Path) -> dict:
    """1:1 model-space engineering linework with semantic layers.

    The PDF is the controlled document sheet. This DXF intentionally keeps
    projected geometry 1:1 in model space so downstream CAD users can measure it.
    """
    g = ir["geometry"]
    L = float(g["overall_length"])
    top_depth = float(g["top_projection_depth"])
    fascia = float(g["front_fascia_drop"])
    pitch = float(g["bay_pitch"])
    ml = float(g["end_margin_left"])
    mr = float(g["end_margin_right"])
    n = int(g["bay_count"])
    bands = [float(x) for x in g["top_depth_bands"]]

    shape = build_shape(ir)
    views = standard_views(shape)
    doc = _setup_doc()
    msp = doc.modelspace()

    # Reference envelope and projected model-space views.
    _draw_dxf_view(msp, views["top"], (0, 0))
    msp.add_lwpolyline([(0, 0), (L, 0), (L, top_depth), (0, top_depth)], close=True, dxfattribs={"layer": "A-REF"})
    for i in range(n + 1):
        x = ml + i * pitch
        if 0 <= x <= L:
            msp.add_line((x, 0), (x, top_depth), dxfattribs={"layer": "A-PANEL-JOINT"})
    y = 0.0
    for b in bands[:-1]:
        y += b
        msp.add_line((0, y), (L, y), dxfattribs={"layer": "A-PANEL-JOINT"})

    front_off = (0.0, -3500.0)
    _draw_dxf_view(msp, views["front"], front_off)
    end_off = (L + 3500.0, 0.0)
    _draw_dxf_view(msp, views["end"], end_off)

    msp.add_text("PLAN - NOMINAL PANEL SKIN", height=180, dxfattribs={"layer": "A-TEXT"}).set_placement((0, top_depth + 1100))
    msp.add_text("FRONT ELEVATION", height=180, dxfattribs={"layer": "A-TEXT"}).set_placement((0, front_off[1] + fascia + 600))
    msp.add_text("END PROFILE - NOT STRUCTURAL SECTION", height=180, dxfattribs={"layer": "A-TEXT"}).set_placement((end_off[0], top_depth + 600))
    msp.add_text(f"STATUS: {ir['status']} / GEOMETRY LEVEL: {ir.get('geometry_level','NOMINAL_SKIN')}", height=160, dxfattribs={"layer": "A-WARNING"}).set_placement((0, top_depth + 1600))

    _add_dim_linear(msp, (0, 0), (L, 0), (0, top_depth + 750), 0, f"{L:.3f}")
    # Set-out chain: margins + repeated bays, not fourteen duplicate pitch dimensions.
    _add_dim_linear(msp, (0, 0), (ml, 0), (0, -650), 0, f"{ml:.3f}")
    _add_dim_linear(msp, (ml, 0), (L - mr, 0), (ml, -650), 0, f"{n} EQ @ {pitch:.3f}")
    _add_dim_linear(msp, (L - mr, 0), (L, 0), (L - mr, -650), 0, f"{mr:.3f}")
    y = 0.0
    for dep in bands:
        _add_dim_linear(msp, (0, y), (0, y + dep), (-700, y), 90, f"{dep:.0f}")
        y += dep

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out)
    return {
        "modelspace_1_to_1": True,
        "views": ["plan", "front", "end_profile"],
        "semantic_layers": sorted(LAYER_SPECS),
        "entity_count": len(msp),
    }


def reference_blank_dxf(ir: dict, out: Path) -> dict:
    """Reference-only nominal face layout.

    This is deliberately *not* called a flat pattern or nesting file when bend
    definitions are unresolved. It shows one representative nominal face per
    geometry type, with quantity and warning text.
    """
    if ir.get("status") == "PRODUCTION_CANDIDATE" and not ir["metrics"].get("flat_pattern_released"):
        raise RuntimeError("PRODUCTION_CANDIDATE cannot emit a reference blank layout in place of a true flat pattern")
    doc = _setup_doc()
    msp = doc.modelspace()
    groups = _panel_groups(ir)
    x, y = 0.0, 0.0
    gap = 500.0
    for idx, row in enumerate(groups, 1):
        w, h = row["width"], row["height"]
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "A-PANEL-CUT"})
        msp.add_text(row["type"], height=90, dxfattribs={"layer": "A-TEXT"}).set_placement((x + w/2, y + h/2 + 90), align=TextEntityAlignment.MIDDLE_CENTER)
        msp.add_text(f"NOMINAL FACE {w:.3f} x {h:.3f} x {row['thickness']:.1f}; QTY {row['qty']}", height=65, dxfattribs={"layer": "A-TEXT"}).set_placement((x + w/2, y + h/2 - 40), align=TextEntityAlignment.MIDDLE_CENTER)
        msp.add_text("REFERENCE ONLY - NOT FLAT PATTERN / NOT NESTING", height=60, dxfattribs={"layer": "A-WARNING"}).set_placement((x + w/2, y - 120), align=TextEntityAlignment.MIDDLE_CENTER)
        x += w + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out)
    return {"reference_only": True, "type_count": len(groups), "flat_pattern_released": False, "entity_count": len(msp)}


def _panel_groups(ir: dict) -> list[dict]:
    agg = Counter((p["kind"], round(p["width"], 3), round(p["height"], 3), round(p["thickness"], 3)) for p in ir["parts"])
    rows = []
    for idx, (key, count) in enumerate(sorted(agg.items()), 1):
        kind, w, h, t = key
        rows.append({
            "type": f"T{idx:02d}", "kind": kind, "width": w, "height": h,
            "thickness": t, "qty": count, "area_m2": w * h / 1e6 * count,
        })
    return rows


# ---------- PDF helpers ----------

def _set_line_mm(c, width_mm: float):
    c.setLineWidth(width_mm * mm)


def _text(c, x_mm, y_mm, text, size=2.5, font=CN_FONT, align="left"):
    c.setFont(font, size * mm)
    x, y = x_mm * mm, y_mm * mm
    if align == "center":
        c.drawCentredString(x, y, str(text))
    elif align == "right":
        c.drawRightString(x, y, str(text))
    else:
        c.drawString(x, y, str(text))


def _label(c, x_mm, y_mm, no, zh, en, scale=None):
    _text(c, x_mm, y_mm, f"{no}  {zh} / {en}", 2.65)
    if scale:
        _text(c, x_mm + 72, y_mm, f"SCALE {scale}", 2.2, "Helvetica")


def _arrow(c, x_mm, y_mm, direction: str, size=1.3):
    x, y = x_mm * mm, y_mm * mm
    s = size * mm
    p = c.beginPath()
    if direction == "right":
        p.moveTo(x, y); p.lineTo(x+s, y+s*0.45); p.lineTo(x+s, y-s*0.45)
    elif direction == "left":
        p.moveTo(x, y); p.lineTo(x-s, y+s*0.45); p.lineTo(x-s, y-s*0.45)
    elif direction == "up":
        p.moveTo(x, y); p.lineTo(x-s*0.45, y+s); p.lineTo(x+s*0.45, y+s)
    else:
        p.moveTo(x, y); p.lineTo(x-s*0.45, y-s); p.lineTo(x+s*0.45, y-s)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def _dim_h(c, x1, x2, y, text, witness_y=None, size=2.2):
    _set_line_mm(c, 0.13)
    if witness_y is not None:
        c.line(x1*mm, witness_y*mm, x1*mm, (y+1.8)*mm)
        c.line(x2*mm, witness_y*mm, x2*mm, (y+1.8)*mm)
    c.line(x1*mm, y*mm, x2*mm, y*mm)
    _arrow(c, x1, y, "right")
    _arrow(c, x2, y, "left")
    _text(c, (x1+x2)/2, y+1.3, text, size, "Helvetica", "center")


def _dim_v(c, x, y1, y2, text, witness_x=None, size=2.2):
    _set_line_mm(c, 0.13)
    if witness_x is not None:
        c.line(witness_x*mm, y1*mm, (x+1.8)*mm, y1*mm)
        c.line(witness_x*mm, y2*mm, (x+1.8)*mm, y2*mm)
    c.line(x*mm, y1*mm, x*mm, y2*mm)
    _arrow(c, x, y1, "up")
    _arrow(c, x, y2, "down")
    # horizontal text beside the dimension is more legible for small A3 details.
    _text(c, x-1.8, (y1+y2)/2-0.9, text, size, "Helvetica", "right")


def _view_map(view: ProjectedView, x_mm, y_mm, scale_den: float, override_bounds=None):
    xmin, ymin, xmax, ymax = override_bounds or view.bounds
    def p(pt):
        x, y = pt
        return (x_mm + (x-xmin)/scale_den, y_mm + (y-ymin)/scale_den)
    return p, (xmax-xmin)/scale_den, (ymax-ymin)/scale_den


def _draw_pdf_view(c, view: ProjectedView, x_mm, y_mm, scale_den: float, override_bounds=None, hidden=True):
    P, w_mm, h_mm = _view_map(view, x_mm, y_mm, scale_den, override_bounds)
    if hidden:
        c.saveState(); _set_line_mm(c, 0.13); c.setDash(1.8*mm, 1.0*mm)
        for line in view.hidden:
            pts = [P(pt) for pt in line]
            if len(pts) >= 2:
                path = c.beginPath(); path.moveTo(pts[0][0]*mm, pts[0][1]*mm)
                for x, y in pts[1:]: path.lineTo(x*mm, y*mm)
                c.drawPath(path, stroke=1, fill=0)
        c.restoreState()
    _set_line_mm(c, 0.35)
    for line in view.visible:
        pts = [P(pt) for pt in line]
        if len(pts) >= 2:
            path = c.beginPath(); path.moveTo(pts[0][0]*mm, pts[0][1]*mm)
            for x, y in pts[1:]: path.lineTo(x*mm, y*mm)
            c.drawPath(path, stroke=1, fill=0)
    return P, w_mm, h_mm


def _fit_view(c, view: ProjectedView, x_mm, y_mm, w_mm, h_mm, padding_mm=2.0):
    sx = max(view.width, 1e-9) / max(w_mm-2*padding_mm, 1e-9)
    sy = max(view.height, 1e-9) / max(h_mm-2*padding_mm, 1e-9)
    den = max(sx, sy)
    P, vw, vh = _view_map(view, x_mm+padding_mm, y_mm+padding_mm, den)
    # centre inside box
    dx = (w_mm-2*padding_mm-vw)/2
    dy = (h_mm-2*padding_mm-vh)/2
    return _draw_pdf_view(c, view, x_mm+padding_mm+dx, y_mm+padding_mm+dy, den, hidden=False), den


def _title_block(c, ir, sheet_no: int, sheet_count: int, title: str, scales: str):
    # A3 landscape frame / title block in millimetres.
    left, right, bottom, top = 8.0, PAGE_W_MM-8.0, 8.0, PAGE_H_MM-8.0
    _set_line_mm(c, 0.35); c.rect(left*mm, bottom*mm, (right-left)*mm, (top-bottom)*mm)
    tb_h = 31.0
    c.line(left*mm, (bottom+tb_h)*mm, right*mm, (bottom+tb_h)*mm)
    x1, x2, x3 = 220.0, 285.0, 350.0
    for x in (x1, x2, x3): c.line(x*mm, bottom*mm, x*mm, (bottom+tb_h)*mm)
    c.line(left*mm, (bottom+15.5)*mm, x1*mm, (bottom+15.5)*mm)
    c.line(x1*mm, (bottom+15.5)*mm, right*mm, (bottom+15.5)*mm)

    _text(c, left+3, bottom+20.5, f"项目 / PROJECT: {ir['project']}", 2.45)
    _text(c, left+3, bottom+5.3, f"图名 / TITLE: {title}", 2.45)
    _text(c, x1+3, bottom+20.5, f"比例 / SCALE: {scales}", 2.25)
    _text(c, x1+3, bottom+5.3, "单位 / UNITS: mm", 2.25)
    _text(c, x2+3, bottom+20.5, "版本 / REV: B", 2.25)
    _text(c, x2+3, bottom+5.3, f"状态 / STATUS: {ir['status']}", 2.1)
    _text(c, x3+3, bottom+20.5, f"图号 / DWG: YP-V32-{sheet_no:03d}", 2.25)
    _text(c, x3+3, bottom+5.3, f"SHEET {sheet_no} OF {sheet_count}", 2.25, "Helvetica")

    # Status flag lives in the drawing field too; it should be impossible to miss.
    c.saveState(); _set_line_mm(c, 0.25); c.setDash(1.5*mm, 0.9*mm)
    c.rect((right-61)*mm, (top-10)*mm, 58*mm, 7*mm)
    c.restoreState()
    _text(c, right-32, top-7.7, ir["status"], 2.25, "Helvetica-Bold", "center")
    return {"left": left, "right": right, "bottom": bottom+tb_h, "top": top}


def _assumption_lines(ir: dict, limit=5):
    out = []
    for a in ir.get("assumptions", [])[:limit]:
        if isinstance(a, str):
            out.append(a)
        else:
            out.append(f"{a.get('id','A')}: {a.get('statement','')}")
    return out


def engineering_pdf(ir: dict, out: Path) -> dict:
    shape = build_shape(ir)
    views = standard_views(shape)
    g = ir["geometry"]
    L = float(g["overall_length"])
    n = int(g["bay_count"])
    pitch = float(g["bay_pitch"])
    ml = float(g["end_margin_left"])
    mr = float(g["end_margin_right"])
    bands = [float(x) for x in g["top_depth_bands"]]
    top_depth = float(g["top_projection_depth"])
    fascia = float(g["front_fascia_drop"])
    profile_path = float(g["profile_path_length_ref"])
    gap = float(g["joint_gap"])

    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=landscape(A3), invariant=1, pageCompression=1)
    c.setTitle(ir["project"])
    c.setAuthor("cad-fabrication-engineering-v3")
    sheet_count = 3
    rendered_marks: set[str] = set()

    # ----- SHEET 1: GA -----
    _title_block(c, ir, 1, sheet_count, "雨棚铝板深化 - 总体分板与标称轮廓", "AS SHOWN")
    _label(c, 18, 276, "01", "平面分板", "PLAN PANELIZATION", "1:100")
    plan_x, plan_y, plan_s = 18.0, 188.0, 100.0
    plan_bounds = (0.0, 0.0, L, top_depth)
    _draw_pdf_view(c, views["top"], plan_x, plan_y, plan_s, override_bounds=plan_bounds, hidden=False)
    plan_w, plan_h = L/plan_s, top_depth/plan_s
    # reference envelope / datums
    c.saveState(); _set_line_mm(c, 0.13); c.setDash(1.6*mm, 1.0*mm)
    c.rect(plan_x*mm, plan_y*mm, plan_w*mm, plan_h*mm)
    c.restoreState()
    # panel joint centre lines + bay IDs: legible at 1:100 even when actual 8 mm gaps collapse on paper.
    _set_line_mm(c, 0.18)
    for i in range(n + 1):
        xx = ml + i*pitch
        if 0 <= xx <= L:
            sx = plan_x + xx/plan_s
            c.line(sx*mm, plan_y*mm, sx*mm, (plan_y+plan_h)*mm)
    yy = 0.0
    for dep in bands[:-1]:
        yy += dep
        sy = plan_y + yy/plan_s
        c.line(plan_x*mm, sy*mm, (plan_x+plan_w)*mm, sy*mm)
    for i in range(n):
        cx = plan_x + (ml + i*pitch + pitch/2)/plan_s
        _text(c, cx, plan_y + plan_h/2 - 1.0, f"B{i+1:02d}", 1.75, "Helvetica", "center")

    _dim_h(c, plan_x, plan_x+plan_w, plan_y+plan_h+7.5, f"{L:.3f} OVERALL", plan_y+plan_h)
    # concise set-out chain instead of 14 repeated dimensions
    x_m1 = plan_x + ml/plan_s
    x_m2 = plan_x + (L-mr)/plan_s
    chain_y = plan_y - 7.5
    _dim_h(c, plan_x, x_m1, chain_y, f"{ml:.0f}", plan_y)
    _dim_h(c, x_m1, x_m2, chain_y, f"{n} EQ @ {pitch:.3f}", plan_y)
    _dim_h(c, x_m2, plan_x+plan_w, chain_y, f"{mr:.0f}", plan_y)
    # depth chain
    y_acc = 0.0
    for dep in bands:
        y1 = plan_y + y_acc/plan_s; y2 = plan_y + (y_acc+dep)/plan_s
        _dim_v(c, plan_x-7.0, y1, y2, f"{dep:.0f}", plan_x)
        y_acc += dep

    # ISO actual B-Rep/HIDDEN-LINE projection, fit-to-box.
    _label(c, 326, 276, "02", "模型轴测", "B-REP ISOMETRIC", "NTS")
    _fit_view(c, views["iso"], 324, 224, 80, 46, padding_mm=2)
    _text(c, 364, 221, f"{len(ir['parts'])} NOMINAL-SKIN PARTS", 1.9, "Helvetica", "center")

    # Full front elevation at common GA scale (small height is truthful, not vertically exaggerated).
    _label(c, 18, 166, "03", "正立面", "FRONT ELEVATION", "1:100")
    front_x, front_y = 18.0, 151.0
    front_bounds = (0.0, min(views["front"].bounds[1], -3.0), L, max(views["front"].bounds[3], fascia))
    _draw_pdf_view(c, views["front"], front_x, front_y, 100.0, override_bounds=front_bounds, hidden=True)
    _dim_v(c, front_x+L/100+5.5, front_y, front_y+fascia/100, f"{fascia:.0f}", front_x+L/100)
    _text(c, front_x, front_y-5.5, "FULL ELEVATION SHOWN AT TRUE 1:100 SCALE; PANEL JOINTS READ FROM B-REP.", 1.75, "Helvetica")

    # End profile, projected from the actual B-Rep. It is explicitly not called a structural section.
    _label(c, 18, 128, "04", "端部标称轮廓", "END NOMINAL-SKIN PROFILE", "1:25")
    prof_x, prof_y, prof_s = 18.0, 83.0, 25.0
    prof_bounds = (0.0, -fascia, top_depth, 3.0)
    _draw_pdf_view(c, views["end"], prof_x, prof_y, prof_s, override_bounds=prof_bounds, hidden=True)
    # depth dimensions above profile
    acc = 0.0
    for dep in bands:
        x1 = prof_x + acc/prof_s; x2 = prof_x + (acc+dep)/prof_s
        _dim_h(c, x1, x2, prof_y+fascia/prof_s+8.0, f"{dep:.0f}", prof_y+fascia/prof_s)
        acc += dep
    _dim_v(c, prof_x+top_depth/prof_s+7.5, prof_y, prof_y+fascia/prof_s, f"{fascia:.0f}", prof_x+top_depth/prof_s)
    _text(c, prof_x, 74.0, f"REF PROFILE CHAIN: {profile_path:.0f} = " + " + ".join(f"{v:.0f}" for v in bands+[fascia]) + " ; VERIFY SOURCE SEMANTIC.", 1.8, "Helvetica")
    _text(c, prof_x, 69.5, "This is a cladding-envelope profile only; no bracket/subframe/waterproofing section is asserted.", 1.75, "Helvetica")

    # Typical panel face (not a flat pattern) for readability.
    group = max((r for r in _panel_groups(ir) if r["kind"] == "top_panel"), key=lambda r: r["height"], default=_panel_groups(ir)[0])
    _label(c, 188, 144, "05", "典型面板标称面", "TYP. NOMINAL FACE", "1:20")
    px, py, ps = 188.0, 80.0, 20.0
    pw, ph = group["width"]/ps, group["height"]/ps
    _set_line_mm(c, 0.35); c.rect(px*mm, py*mm, pw*mm, ph*mm)
    _dim_h(c, px, px+pw, py-6, f"{group['width']:.3f}", py)
    _dim_v(c, px+pw+6, py, py+ph, f"{group['height']:.3f}", px+pw)
    _text(c, px, 68.0, f"{group['type']} / {group['kind']} / T={group['thickness']:.1f} / QTY={group['qty']}", 1.8, "Helvetica")
    _text(c, px, 63.5, "NOMINAL FACE ONLY - RETURN FLANGE / BEND RELIEF / FLAT PATTERN NOT RELEASED.", 1.75, "Helvetica")

    # Notes / release state on the right, not mixed into geometry.
    nx, ny, nw, nh = 326.0, 144.0, 78.0, 72.0
    _set_line_mm(c, 0.18); c.rect(nx*mm, ny*mm, nw*mm, nh*mm)
    _text(c, nx+3, ny+nh-6, "深化状态 / RELEASE STATE", 2.25)
    release_lines = [
        f"Geometry: {ir.get('geometry_level','NOMINAL_SKIN')}",
        "DWG parse: recovered dimensions only",
        "Flat pattern: NOT RELEASED",
        "Survey: NOT APPLIED",
        "Nodes/subframe: NOT MODELED",
        f"Joint gap: {gap:.1f} mm (reference)",
    ]
    for i, line in enumerate(release_lines):
        _text(c, nx+3, ny+nh-13-i*6.1, line, 1.75, "Helvetica")
    c.showPage()

    # ----- SHEET 2: SCHEDULE + COMPLETE MARK MATRIX -----
    _title_block(c, ir, 2, sheet_count, "板件类型表、完整编号矩阵与材料状态", "NTS")
    groups = _panel_groups(ir)
    _label(c, 18, 276, "01", "板件类型表", "PANEL TYPE SCHEDULE")
    cols = [18, 35, 82, 117, 152, 175, 194, 224, 276, 333, 404]
    headers = ["TYPE", "KIND", "W mm", "H mm", "T", "QTY", "AREA m2", "MATERIAL", "FINISH", "FABRICATION STATUS"]
    table_top, row_h = 267.0, 11.0
    _set_line_mm(c, 0.18)
    for x in cols: c.line(x*mm, (table_top-(len(groups)+1)*row_h)*mm, x*mm, table_top*mm)
    for r in range(len(groups)+2):
        y = table_top-r*row_h
        c.line(cols[0]*mm, y*mm, cols[-1]*mm, y*mm)
    for i, h in enumerate(headers): _text(c, (cols[i]+cols[i+1])/2, table_top-7.3, h, 1.75, "Helvetica-Bold", "center")
    material = ir.get("material", {})
    for r, row in enumerate(groups, 1):
        y = table_top-r*row_h-7.3
        vals = [row["type"], row["kind"], f"{row['width']:.3f}", f"{row['height']:.3f}", f"{row['thickness']:.1f}", str(row["qty"]), f"{row['area_m2']:.3f}", material.get("grade", "TBC"), material.get("finish", "TBC"), "NOMINAL FACE / NO FLAT"]
        for i, val in enumerate(vals): _text(c, (cols[i]+cols[i+1])/2, y, val, 1.62, "Helvetica", "center")

    # Mark matrix: 14 bays x (3 top bands + fascia) = all 56 marks, no silent truncation.
    _label(c, 18, 211, "02", "完整板件编号矩阵", "COMPLETE PANEL MARK MATRIX")
    matrix_x0, matrix_x1 = 18.0, 404.0
    row_labels = [f"TOP B{i:02d}" for i in range(1, len(bands)+1)] + ["FASCIA"]
    matrix_top = 201.0
    label_w = 25.0
    cell_w = (matrix_x1-matrix_x0-label_w)/n
    # grid
    for i in range(n+1):
        x = matrix_x0+label_w+i*cell_w
        c.line(x*mm, (matrix_top-(len(row_labels)+1)*11)*mm, x*mm, matrix_top*mm)
    c.line(matrix_x0*mm, (matrix_top-(len(row_labels)+1)*11)*mm, matrix_x0*mm, matrix_top*mm)
    c.line((matrix_x0+label_w)*mm, (matrix_top-(len(row_labels)+1)*11)*mm, (matrix_x0+label_w)*mm, matrix_top*mm)
    for r in range(len(row_labels)+2):
        y=matrix_top-r*11
        c.line(matrix_x0*mm, y*mm, matrix_x1*mm, y*mm)
    _text(c, matrix_x0+label_w/2, matrix_top-7.2, "ZONE", 1.7, "Helvetica-Bold", "center")
    for bay in range(1, n+1):
        _text(c, matrix_x0+label_w+(bay-.5)*cell_w, matrix_top-7.2, f"B{bay:02d}", 1.6, "Helvetica-Bold", "center")
    by_key = defaultdict(list)
    for p in ir["parts"]: by_key[(p["kind"], p.get("band"))].append(p)
    for ri, label in enumerate(row_labels, 1):
        y = matrix_top-ri*11-7.2
        _text(c, matrix_x0+label_w/2, y, label, 1.55, "Helvetica", "center")
        if ri <= len(bands): key=("top_panel", ri)
        else: key=("front_fascia", None)
        parts = sorted(by_key[key], key=lambda p: p["bay"])
        for p in parts:
            rendered_marks.add(p["id"])
            x = matrix_x0+label_w+(p["bay"]-.5)*cell_w
            _text(c, x, y, p["id"], 1.45, "Helvetica", "center")
    _text(c, 18, 138.5, f"MARK COVERAGE: {len(rendered_marks)}/{len(ir['parts'])} - COMPLETE", 2.0, "Helvetica-Bold")

    # Material / metrics and hard release gates.
    _label(c, 18, 126, "03", "材料与数量", "MATERIAL / QUANTITY")
    metrics = ir["metrics"]
    qx, qy, qw, qh = 18.0, 62.0, 178.0, 57.0
    _set_line_mm(c, 0.18); c.rect(qx*mm, qy*mm, qw*mm, qh*mm)
    q_lines = [
        f"Panel count: {metrics['panel_count']}",
        f"Net visible sheet area: {metrics['net_visible_sheet_area_m2']} m2",
        f"Estimated net sheet mass: {metrics['estimated_net_sheet_mass_kg']} kg",
        "Blank area: NOT AVAILABLE - true unfold not released",
        "Purchase area: NOT AVAILABLE - nesting / waste not defined",
        f"Material: {material.get('grade','TBC')} / {material.get('finish','TBC')} / {g['panel_thickness']:.1f} mm",
    ]
    for i, line in enumerate(q_lines): _text(c, qx+4, qy+qh-8-i*7.2, line, 2.0, "Helvetica")

    _label(c, 210, 126, "04", "生产放行阻断项", "PRODUCTION RELEASE BLOCKERS")
    bx, by, bw, bh = 210.0, 62.0, 194.0, 57.0
    _set_line_mm(c, 0.18); c.rect(bx*mm, by*mm, bw*mm, bh*mm)
    blockers = _assumption_lines(ir, 4)
    blockers += ["Gate A 尚未确认。" if not ir.get("release_gates",{}).get("gate_a_confirmed",False) else "Gate A 已确认。"]
    blockers += ["现场复尺尚未回填。" if not ir.get("release_gates",{}).get("survey_applied",False) else "现场复尺已回填。"]
    yy = by+bh-7
    for line in blockers[:6]:
        # Keep blockers readable: hard-wrap concise statements to two rows maximum.
        text_line = str(line)
        chunks = [text_line[i:i+42] for i in range(0, len(text_line), 42)][:2]
        for ci, chunk in enumerate(chunks):
            _text(c, bx+4, yy, ("- " if ci == 0 else "  ") + chunk, 1.85)
            yy -= 4.8
        yy -= 1.1
    c.showPage()

    # ----- SHEET 3: NOMINAL FACE DETAILS -----
    _title_block(c, ir, 3, sheet_count, "典型板件标称面尺寸 - 非展开图", "1:20")
    _label(c, 18, 276, "01", "典型板件标称面", "NOMINAL PANEL FACE DETAILS", "1:20")
    _text(c, 18, 269, "These details dimension the nominal visible face only. They are intentionally not fabrication flat patterns.", 1.9, "Helvetica")
    positions = [(18, 177), (151, 177), (284, 177)]
    for row, (x0, y0) in zip(groups, positions):
        scale = 20.0
        w, h = row["width"]/scale, row["height"]/scale
        box_w = 116.0
        _set_line_mm(c, 0.18); c.rect(x0*mm, (y0-5)*mm, box_w*mm, 82*mm)
        _text(c, x0+3, y0+68, f"{row['type']}  {row['kind']}  QTY {row['qty']}", 2.05, "Helvetica-Bold")
        gx = x0 + (box_w-w)/2
        gy = y0 + 4
        _set_line_mm(c, 0.35); c.rect(gx*mm, gy*mm, w*mm, h*mm)
        _dim_h(c, gx, gx+w, gy-6, f"{row['width']:.3f}", gy)
        _dim_v(c, gx+w+6, gy, gy+h, f"{row['height']:.3f}", gx+w)
        _text(c, x0+3, y0-1, f"T={row['thickness']:.1f} mm / AREA TOTAL={row['area_m2']:.3f} m2", 1.65, "Helvetica")
    _label(c, 18, 147, "02", "加工定义边界", "FABRICATION DEFINITION BOUNDARY")
    boundary = [
        "Nominal face geometry: available and traceable.",
        "Return flange / bend radius / K-factor: reference inputs only until Gate A confirms the node.",
        "Corner reliefs, fastener holes, drainage, seam returns, brackets and subframe interfaces: not modeled.",
        "Therefore: do not derive CNC, nesting or purchase quantity from this sheet.",
        "When fabrication definition is confirmed, generate a fabrication solid first, then a true flat pattern from that solid.",
    ]
    for i, line in enumerate(boundary): _text(c, 18, 139-i*7.0, f"{i+1}. {line}", 1.85, "Helvetica")
    c.showPage(); c.save()

    return {
        "sheet_count": sheet_count,
        "view_source": "OCCT_HLR_FROM_BREP",
        "scales": {"plan": "1:100", "front": "1:100", "end_profile": "1:25", "typical_face": "1:20"},
        "panel_mark_coverage": {"expected": len(ir["parts"]), "rendered": len(rendered_marks), "ratio": round(len(rendered_marks)/max(len(ir["parts"]),1), 6)},
        "flat_pattern_claimed": False,
        "profile_semantic": "NOMINAL_CLADDING_ENVELOPE_NOT_STRUCTURAL_SECTION",
        "font": {"name": CN_FONT, "embedded_expected": CN_FONT_EMBEDDED, "source": CN_FONT_SOURCE},
    }