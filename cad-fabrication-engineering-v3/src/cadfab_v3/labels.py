"""Portable display labels without rewriting source IDs or source drawings.

PDF Unicode is allowed only with a coverage-checked, embeddable local font.
DXF TEXT is deliberately ASCII: a font name in STYLE does not embed its font.
Every changed label is recoverable from the adjacent UTF-8 label-map sidecar.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import os
import re

from fontTools.ttLib import TTFont


TRANSLATIONS = {
    "雨棚铝板深化 - 总体分板与标称轮廓": "Canopy cladding - panel layout and nominal profiles",
    "板件类型表、完整编号矩阵与材料状态": "Panel schedule, complete mark matrix and material status",
    "典型板件标称面尺寸 - 非展开图": "Nominal panel face dimensions - NOT FLAT PATTERNS",
    "材料牌号、厚度、表面处理及25mm折边均为验证假设，Gate A 尚未确认。": "Material grade, thickness, finish and 25 mm return are assumptions. Gate A unconfirmed.",
    "1190/1170/1170 被解释为顶面分带尺寸，须用生产级 DWG 解析复核原始语义。": "1190/1170/1170 assumed top bands; production DWG parsing must verify source meaning.",
    "600mm 被解释为前檐下翻，仅用于还原 4130 参考轮廓链，非已确认生产尺寸。": "600 mm assumed fascia drop in 4130 reference chain; NOT a confirmed production dimension.",
    "节点、龙骨、角码、紧固件、防水排水、胶缝及结构接口均未建模。": "Nodes, subframe, brackets, fasteners, drainage, joints and structural interfaces are not modeled.",
    "Gate A 尚未确认。": "Gate A NOT CONFIRMED.",
    "Gate A 已确认。": "Gate A CONFIRMED.",
    "现场复尺尚未回填。": "Site survey NOT APPLIED.",
    "现场复尺已回填。": "Site survey APPLIED.",
    "深化状态": "Release state", "项目": "Project", "图名": "Title", "比例": "Scale",
    "单位": "Units", "版本": "Revision", "状态": "Status", "图号": "Drawing",
    "平面分板": "Plan panelization", "模型轴测": "Model isometric", "正立面": "Front elevation",
    "端部标称轮廓": "Nominal end profile", "端部轮廓": "End profile", "典型面板标称面": "Typical nominal face",
    "板件类型表": "Panel type schedule", "完整板件编号矩阵": "Complete panel mark matrix",
    "材料与数量": "Material and quantity", "生产放行阻断项": "Production release blockers",
    "典型板件标称面": "Nominal panel face details", "加工定义边界": "Fabrication definition boundary",
    "°": " deg", "±": "+/-", "×": "x", "–": "-", "—": "-", "Ø": "DIA", "ø": "DIA",
    "²": "2", "³": "3", "，": ", ", "。": ".", "：": ": ", "（": "(", "）": ")", "、": ", ",
}


def is_ascii_text(value: str) -> bool:
    return all(32 <= ord(ch) <= 126 for ch in value)


def _windows_reserved(value: str) -> bool:
    return value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def stable_display_id(raw_id: str, prefix: str = "P") -> str:
    """Stable ASCII marks; originals survive in the mapping, never normalized away.

    Uppercase engineering marks remain unchanged. Lowercase, unsafe or Unicode
    IDs receive a hash so case-insensitive consumers cannot merge A and a.
    """
    raw_id = str(raw_id)
    if re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]{0,39}", raw_id) and not raw_id.endswith(".") and not _windows_reserved(raw_id):
        return raw_id
    return f"{prefix}-{sha256(raw_id.encode('utf-8')).hexdigest()[:12].upper()}"


def portable_file_stem(raw: str) -> str:
    """Safe standalone output stem with stable raw-name disambiguation.

    Lowercase ASCII project slugs are conventional and preserved. Uppercase or
    otherwise unsafe names use a content-addressed alias, avoiding case-only
    filename collisions across platforms without altering the canonical project.
    """
    raw = str(raw)
    if re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,79}", raw) and not raw.endswith(".") and not _windows_reserved(raw):
        return raw
    return "project-" + sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class VerifiedFont:
    source: str
    index: int
    name: str
    buffer: bytes
    coverage: frozenset[int]
    sha256: str

    def supports(self, text: str) -> bool:
        return all(ord(c) in self.coverage for c in text if not c.isspace())


def discover_font(candidates: list[str | Path] | None = None) -> tuple[VerifiedFont | None, list[str]]:
    """CADFAB_CJK_FONT is an exclusive override, useful for deterministic builds.

    An invalid override fails safely to ASCII rather than silently using another
    font. Restricted/no-subsetting/bitmap-only fonts are conservatively rejected.
    """
    if candidates is None:
        override = os.environ.get("CADFAB_CJK_FONT")
        candidates = [override] if override else [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "C:/Windows/Fonts/Deng.ttf", "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
    rejected = []
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            rejected.append(f"missing:{path}")
            continue
        # Noto CJK index 2 is Simplified Chinese. All other faces are also checked.
        indices = [2, 0, 1, 3, 4] if path.suffix.lower() == ".ttc" else [0]
        for index in indices:
            try:
                font = TTFont(str(path), fontNumber=index, recalcTimestamp=False)
                try:
                    cmap = font.getBestCmap() or {}
                    coverage = frozenset(code for code, name in cmap.items() if font.getGlyphID(name) != 0)
                    if not all(ord(ch) in coverage for ch in "雨棚铝板"):
                        raise ValueError("CJK probe glyphs missing")
                    if "OS/2" in font and font["OS/2"].fsType & (0x0002 | 0x0100 | 0x0200):
                        raise ValueError("font embedding/subsetting prohibited")
                    stream = BytesIO()
                    font.save(stream)
                    buffer = stream.getvalue()
                finally:
                    font.close()
                import fitz
                renderer_font = fitz.Font(fontbuffer=buffer)
                if not all(renderer_font.has_glyph(ord(ch)) for ch in "雨棚铝板"):
                    raise ValueError("renderer missing probe glyphs")
                return VerifiedFont(str(path), index, renderer_font.name, buffer, coverage,
                                    sha256(buffer).hexdigest()), rejected
            except Exception as exc:
                rejected.append(f"rejected:{path}#{index}:{type(exc).__name__}:{exc}")
    return None, rejected


def verify_font_raster(source_buffer: bytes, embedded_buffer: bytes, text: str) -> bool:
    """Compare actual glyph pixels, catching CID/GID reorder despite correct text.

    Every distinct used non-space character is rendered with both full source
    font and final embedded font. Same glyphs must have identical pixels/metrics.
    """
    import fitz
    characters = "".join(sorted(set(text) - {" ", "\n", "\r", "\t"}))
    if not characters:
        return True
    lines = [characters[i:i+28] for i in range(0, len(characters), 28)]
    rasters = []
    for buffer in (source_buffer, embedded_buffer):
        with fitz.open() as document:
            page = document.new_page(width=620, height=30+len(lines)*28)
            page.insert_font(fontname="GlyphCheck", fontbuffer=buffer)
            for index, line in enumerate(lines):
                page.insert_text((15, 25+index*28), line, fontname="GlyphCheck", fontsize=18)
            rasters.append(page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).samples)
    return rasters[0] == rasters[1]


class LabelPolicy:
    def __init__(self, ir: dict | None = None, *, font_candidates=None, pdf_unicode=True):
        self.ir = ir or {}
        self.translations = dict(TRANSLATIONS)
        project = str(self.ir.get("project", ""))
        if project and not is_ascii_text(project):
            self.translations[project] = stable_display_id(project, "PROJECT")
        self.translations.update(self.ir.get("display_labels", {}))
        if any(not is_ascii_text(str(value)) for value in self.translations.values()):
            raise ValueError("display_labels values must be printable English/pinyin ASCII")
        self.font, self.font_rejections = discover_font(font_candidates) if pdf_unicode else (None, [])
        self.records: dict[str, dict] = {}
        self.overlays: list[dict] = []
        self.fit_issues: list[dict] = []
        self.font_raster_verified = False
        self.page_raster_verified = False
        self.embedding_strategy = None
        self.part_ids = {str(p["id"]): stable_display_id(p["id"]) for p in self.ir.get("parts", [])}
        if len({value.casefold() for value in self.part_ids.values()}) != len(self.part_ids):
            raise ValueError("display ID collision; choose explicit unique ASCII source IDs")
        for raw_id, display_id in self.part_ids.items():
            self._record(raw_id, display_id, "part_id", True, raw_id)

    def _record(self, raw, display, target, translated, raw_id=None):
        key = sha256((target + "\0" + str(raw)).encode("utf-8")).hexdigest()
        record = {"key": key, "raw_id": raw_id, "raw_label": str(raw), "display_label": str(display),
                  "target": target, "semantic_translation_available": translated}
        self.records[key] = record
        return display

    def ascii(self, raw, *, context="label") -> str:
        raw = str(raw)
        if raw in self.part_ids:
            return self._record(raw, self.part_ids[raw], context, True, raw)
        text = raw
        for source in sorted(self.translations, key=len, reverse=True):
            text = text.replace(source, self.translations[source])
        text = " ".join(text.split())
        # Bilingual headings already carry an English counterpart; avoid duplication.
        if " / " in text:
            pieces = text.split(" / ")
            if len(pieces) == 2 and pieces[0].strip().casefold() == pieces[1].strip().casefold():
                text = pieces[1]
        translated = is_ascii_text(text)
        if not translated:
            text = "UNTRANSLATED-" + sha256(raw.encode("utf-8")).hexdigest()[:10].upper()
        return self._record(raw, text, context, translated)

    def pdf(self, raw) -> tuple[str, bool]:
        raw = str(raw)
        if raw in self.part_ids:
            return self._record(raw, self.part_ids[raw], "pdf", True, raw), False
        if is_ascii_text(raw):
            return self._record(raw, raw, "pdf", True), False
        if self.font and self.font.supports(raw):
            return self._record(raw, raw, "pdf", True), True
        return self.ascii(raw, context="pdf"), False

    def embed_overlays(self, path: Path):
        if not self.overlays:
            return
        import fitz
        # Subset before PDF insertion. This also removes duplicate compatibility
        # cmap entries, which otherwise make extracted text differ from raw labels.
        from fontTools import subset
        font = TTFont(BytesIO(self.font.buffer), recalcTimestamp=False)
        options = subset.Options()
        # CID-keyed CFF fonts use glyph IDs as CIDs in the PDF. Renumbering GIDs
        # can preserve ToUnicode extraction while visibly drawing WRONG glyphs.
        options.retain_gids = True
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(text="".join(item["text"] for item in self.overlays))
        subsetter.subset(font)
        stream = BytesIO()
        font.save(stream)
        font.close()
        embedded_buffer = stream.getvalue()
        renderer_font = fitz.Font(fontbuffer=embedded_buffer)
        if any(not renderer_font.has_glyph(ord(ch)) for item in self.overlays for ch in item["text"] if not ch.isspace()):
            raise RuntimeError("font subset lost required glyph coverage")
        self.embedding_strategy = "subset-retained-gids"
        if not verify_font_raster(self.font.buffer, embedded_buffer,
                                  "".join(item["text"] for item in self.overlays)):
            # A larger verified full font is safer than a small corrupt subset.
            embedded_buffer = self.font.buffer
            self.embedding_strategy = "full-font-after-subset-render-rejection"
        self.font_raster_verified = True
        doc = fitz.open(path)
        source_doc = fitz.open(path)
        try:
            for item in self.overlays:
                for target, buffer in ((doc, embedded_buffer), (source_doc, self.font.buffer)):
                    page = target[item["page"] - 1]
                    page.insert_font(fontname="CADFAB_Embedded_CJK", fontbuffer=buffer)
                    page.insert_text((item["x"], item["y"]), item["text"], fontsize=item["size"],
                                     fontname="CADFAB_Embedded_CJK", color=(0, 0, 0), overlay=True)
            # Compare actual engineering sheets, including linework, labels,
            # positions, and all used glyphs, against full-font reference pages.
            self.page_raster_verified = all(
                page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).samples ==
                source_doc[index].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).samples
                for index, page in enumerate(doc))
            if not self.page_raster_verified:
                raise RuntimeError("engineering_page_font_raster_mismatch")
            tmp = path.with_suffix(".embedded.tmp.pdf")
            doc.save(tmp, garbage=4, deflate=True)
        finally:
            source_doc.close()
            doc.close()
        os.replace(tmp, path)

    def metadata(self) -> dict:
        return {
            "policy": "verified_embedded_unicode_pdf_ascii_dxf",
            "font": {"name": self.font.name if self.font else "Helvetica",
                     "source": self.font.source if self.font else "standard PDF ASCII",
                     "face_index": self.font.index if self.font else None,
                     "sha256": self.font.sha256 if self.font else None,
                     "embedded_expected": bool(self.overlays),
                     "glyph_coverage_verified": True,
                     "glyph_raster_matches_source": self.font_raster_verified if self.overlays else None,
                     "whole_page_raster_matches_source": self.page_raster_verified if self.overlays else None,
                     "embedding_strategy": self.embedding_strategy,
                     "unicode_text_count": len(self.overlays),
                     "fallback_reason": None if self.font else "no_verified_embeddable_CJK_font"},
            "part_id_mapping": [{"raw_id": raw, "display_id": display} for raw, display in sorted(self.part_ids.items())],
            "labels": sorted(self.records.values(), key=lambda r: r["key"]),
            "untranslated_labels": [r for r in self.records.values() if not r["semantic_translation_available"]],
            "layout_issues": self.fit_issues,
        }

    def write_sidecar(self, path: Path) -> Path:
        sidecar = path.with_suffix(path.suffix + ".labels.json")
        sidecar.write_text(json.dumps(self.metadata(), ensure_ascii=False, indent=2), encoding="utf-8")
        return sidecar
