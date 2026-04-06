"""
Resume template service: parse resume text into structured sections,
then build a fully-formatted DOCX with distinct layouts per template.

8 Templates (inspired by popular LinkedIn / professional resume designs):
  1. Professional Classic  – single-column, centered name, horizontal rules (Calibri)
  2. Modern Tech           – two-column dark sidebar, blue accents (Arial)
  3. Creative Portfolio    – purple accents, decorative markers (Georgia)
  4. Academic CV           – formal "Curriculum Vitae" (Times New Roman)
  5. Executive             – navy+gold, premium spacing (Cambria)
  6. Minimalist Clean      – ultra-clean, monochrome, max whitespace (Calibri Light)
  7. Corporate Elegance    – teal header block, single-column body (Calibri)
  8. Fresh Graduate        – blue header bar, skills-first, compact (Arial)
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

_log = logging.getLogger(__name__)

TEMPLATES_BASE = Path(__file__).resolve().parents[2] / "data" / "templates"

# ──────────────────────────────────────────────────────────────────────────────
# Resume text parser
# ──────────────────────────────────────────────────────────────────────────────

_SECTION_KEYWORDS = [
    "summary", "profile", "objective", "about", "professional summary",
    "experience", "work experience", "professional experience", "employment",
    "education", "academic background",
    "skills", "technical skills", "core competencies", "competencies",
    "projects", "project experience",
    "certifications", "certificates", "licenses",
    "publications", "research",
    "awards", "honors", "achievements",
    "languages",
    "interests", "hobbies",
    "references", "volunteer", "volunteering",
    "activities", "extracurricular",
    "contact", "personal information",
]

_SECTION_RE = re.compile(
    r"^(?:" + "|".join(re.escape(k) for k in _SECTION_KEYWORDS) + r")\s*:?\s*$",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"[\+]?[\d\s\-().]{7,15}")
_URL_RE = re.compile(r"(?:https?://|www\.)[\w./?=&%-]+", re.IGNORECASE)


@dataclass
class ResumeSection:
    title: str
    lines: List[str] = field(default_factory=list)


@dataclass
class ParsedResume:
    name: str = ""
    contact_lines: List[str] = field(default_factory=list)
    sections: List[ResumeSection] = field(default_factory=list)


def _is_section_header(line: str) -> bool:
    stripped = line.strip().rstrip(":")
    if not stripped:
        return False
    if _SECTION_RE.match(stripped):
        return True
    words = stripped.split()
    if 1 <= len(words) <= 5 and stripped == stripped.upper() and len(stripped) > 2:
        return True
    if 1 <= len(words) <= 5 and all(w[0].isupper() for w in words if w.isalpha()):
        lower = stripped.lower().rstrip(":")
        for kw in _SECTION_KEYWORDS:
            if lower == kw or lower.startswith(kw):
                return True
    return False


def _looks_like_contact(line: str) -> bool:
    s = line.strip()
    if _EMAIL_RE.search(s):
        return True
    if _URL_RE.search(s):
        return True
    parts = [p.strip() for p in re.split(r"[|·•,]", s) if p.strip()]
    if len(parts) >= 2:
        has_contact = any(
            _EMAIL_RE.search(p) or _PHONE_RE.fullmatch(p.strip()) or _URL_RE.search(p)
            for p in parts
        )
        if has_contact:
            return True
    if _PHONE_RE.fullmatch(s):
        return True
    return False


def _normalize_resume_text(text: str) -> str:
    """Improve structure from mixed PDF/DOCX extraction: split very long lines, cap blank runs.

    Limitations (future work if export quality must match original layout):
    - Chunk order follows DB ``idx``/``created_at``; complex PDFs (multi-column, scanned) may extract out of reading order.
    - Image-only PDFs need OCR; not handled here.
    - Suggestion application uses substring replace; multiple similar spans can reduce match reliability across mixed uploads.
    Consider: MIME-specific parsers, reading-order heuristics, OCR pipeline, or structured DOCX round-trips before ``parse_resume``.
    """
    if not text or not text.strip():
        return text
    out_lines: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out_lines.append("")
            continue
        if len(s) > 400:
            parts = re.split(r"(?<=[.!?])\s+", s)
            for p in parts:
                if p.strip():
                    out_lines.append(p.strip())
        else:
            out_lines.append(s)
    collapsed: List[str] = []
    blank_run = 0
    for line in out_lines:
        if not line.strip():
            blank_run += 1
            if blank_run <= 2:
                collapsed.append("")
        else:
            blank_run = 0
            collapsed.append(line)
    return "\n".join(collapsed).strip()


def parse_resume(text: str) -> ParsedResume:
    """Split resume plain-text into name, contact lines, and titled sections."""
    text = _normalize_resume_text(text)
    lines = text.splitlines()
    result = ParsedResume()

    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx < len(lines):
        candidate = lines[idx].strip()
        if candidate and not _is_section_header(candidate) and len(candidate) < 80:
            result.name = candidate
            idx += 1

    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            idx += 1
            continue
        if _looks_like_contact(line):
            result.contact_lines.append(line)
            idx += 1
        elif _is_section_header(line):
            break
        elif len(result.contact_lines) == 0 and len(line) < 120:
            if "|" in line or "·" in line or "•" in line:
                result.contact_lines.append(line)
                idx += 1
            else:
                break
        else:
            break

    current_section: Optional[ResumeSection] = None
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if _is_section_header(stripped):
            if current_section is not None:
                result.sections.append(current_section)
            current_section = ResumeSection(title=stripped.rstrip(":").strip())
            idx += 1
            continue
        if current_section is None:
            if stripped:
                current_section = ResumeSection(title="Summary")
                current_section.lines.append(line)
        else:
            current_section.lines.append(line)
        idx += 1

    if current_section is not None:
        result.sections.append(current_section)

    for sec in result.sections:
        while sec.lines and not sec.lines[-1].strip():
            sec.lines.pop()

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_docx():
    try:
        from docx import Document  # noqa: F401
        return True
    except ImportError:
        raise RuntimeError("python-docx is required for template export")


def _set_cell_shading(cell, hex_color: str):
    from docx.oxml.ns import qn
    from lxml import etree
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:shd"))
    if existing is not None:
        tc_pr.remove(existing)
    shading = etree.SubElement(tc_pr, qn("w:shd"))
    shading.set(qn("w:fill"), hex_color)
    shading.set(qn("w:val"), "clear")


def _set_cell_margins(cell, top=0, bottom=0, left=0, right=0):
    """Set cell margins (in twips: 1pt = 20 twips)."""
    from docx.oxml.ns import qn
    from lxml import etree
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:tcMar"))
    if existing is not None:
        tc_pr.remove(existing)
    tc_mar = etree.SubElement(tc_pr, qn("w:tcMar"))
    for edge, val in [("top", top), ("bottom", bottom), ("start", left), ("end", right)]:
        el = etree.SubElement(tc_mar, qn(f"w:{edge}"))
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")


def _set_cell_vertical_alignment(cell, align="top"):
    """Set vertical alignment of table cell content."""
    from docx.oxml.ns import qn
    from lxml import etree
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    existing = tc_pr.find(qn("w:vAlign"))
    if existing is not None:
        tc_pr.remove(existing)
    v_align = etree.SubElement(tc_pr, qn("w:vAlign"))
    v_align.set(qn("w:val"), align)


def _set_paragraph_spacing(paragraph, before=0, after=0, line=None):
    from docx.shared import Pt
    pf = paragraph.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if line:
        pf.line_spacing = Pt(line)


def _set_paragraph_bottom_border(paragraph, color_hex, sz="4", space="1"):
    """Add a bottom border to a paragraph, removing any existing pBdr first."""
    from docx.oxml.ns import qn
    from lxml import etree
    pPr = paragraph._p.get_or_add_pPr()
    existing = pPr.find(qn("w:pBdr"))
    if existing is not None:
        pPr.remove(existing)
    pBdr = etree.SubElement(pPr, qn("w:pBdr"))
    bottom = etree.SubElement(pBdr, qn("w:bottom"))
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), sz)
    bottom.set(qn("w:space"), space)
    bottom.set(qn("w:color"), color_hex)


def _add_horizontal_line(doc_or_cell, color_hex="444444", width_pt=0.5):
    p = doc_or_cell.add_paragraph()
    _set_paragraph_bottom_border(p, color_hex, sz=str(int(width_pt * 8)))
    _set_paragraph_spacing(p, before=2, after=4)
    return p


def _set_run_font(run, font_name, fallback_name=None):
    """Set font name on a run with optional rFonts fallback for cross-platform."""
    run.font.name = font_name
    if fallback_name:
        from docx.oxml.ns import qn
        rPr = run._r.get_or_add_rPr()
        r_fonts = rPr.find(qn("w:rFonts"))
        if r_fonts is not None:
            r_fonts.set(qn("w:hAnsi"), font_name)
            r_fonts.set(qn("w:cs"), fallback_name)
        else:
            from lxml import etree
            r_fonts = etree.SubElement(rPr, qn("w:rFonts"))
            r_fonts.set(qn("w:ascii"), font_name)
            r_fonts.set(qn("w:hAnsi"), font_name)
            r_fonts.set(qn("w:cs"), fallback_name)


def _is_sub_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if re.match(r"^.{3,60}\s*[|–—-]\s*.{3,60}$", stripped):
        return True
    if re.match(r"^.{3,50}\s*\(\s*\d{4}", stripped):
        return True
    if stripped.endswith(":") and len(stripped) < 60 and not _is_section_header(stripped):
        return True
    return False


def _split_contact_parts(contact_lines: List[str]) -> List[str]:
    """Flatten contact lines separated by | . into individual items."""
    parts = []
    for cl in contact_lines:
        for p in re.split(r"[|·•]", cl):
            p = p.strip()
            if p:
                parts.append(p)
    return parts


_SIDEBAR_SECTION_NAMES = {
    "skills", "technical skills", "core competencies", "competencies",
    "languages", "certifications", "certificates", "licenses",
    "interests", "hobbies", "contact", "personal information",
    "awards", "honors", "achievements",
}


def _partition_sections(parsed: ParsedResume):
    """Split sections into sidebar vs main content."""
    sidebar, main = [], []
    for sec in parsed.sections:
        if sec.title.lower() in _SIDEBAR_SECTION_NAMES:
            sidebar.append(sec)
        else:
            main.append(sec)
    return sidebar, main


def _remove_table_borders(table):
    """Remove all borders from a table."""
    from docx.oxml.ns import qn
    from lxml import etree
    tbl = table._tbl
    tbl_pr = tbl.tblPr if tbl.tblPr is not None else etree.SubElement(tbl, qn("w:tblPr"))
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is not None:
        tbl_pr.remove(borders)
    borders = etree.SubElement(tbl_pr, qn("w:tblBorders"))
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = etree.SubElement(borders, qn(f"w:{edge}"))
        e.set(qn("w:val"), "none")
        e.set(qn("w:sz"), "0")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "auto")


def _is_skills_section(title: str) -> bool:
    return title.lower() in {
        "skills", "technical skills", "core competencies", "competencies",
    }


def _format_skills_inline(lines: List[str]) -> str:
    """Convert bullet-list skills into a comma-separated string."""
    items = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        stripped = stripped.lstrip("•-–▪►✦*▸ ").strip()
        if not stripped:
            continue
        for part in re.split(r"[,;]", stripped):
            part = part.strip()
            if part:
                items.append(part)
    return ", ".join(items)


def _get_first_paragraph(cell):
    """Get first paragraph of a cell, reusing the existing empty one if possible."""
    if cell.paragraphs and not cell.paragraphs[0].text:
        return cell.paragraphs[0]
    return cell.add_paragraph()


# ══════════════════════════════════════════════════════════════════════════════
# Template 1: Professional Classic
# Single-column, centered name, horizontal rules. ATS-friendly.
# Font: Calibri (universal). Inspired by Resume.io "London" / Zety "Traditional".
# ══════════════════════════════════════════════════════════════════════════════

def _build_professional_classic(parsed: ParsedResume) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    NAVY = RGBColor(0x1a, 0x1a, 0x2e)
    DARK = RGBColor(0x33, 0x33, 0x33)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style.font.color.rgb = DARK
    style.paragraph_format.space_after = Pt(2)

    sec = doc.sections[0]
    sec.top_margin = Cm(2)
    sec.bottom_margin = Cm(2)
    sec.left_margin = Cm(2.5)
    sec.right_margin = Cm(2.5)

    if parsed.name:
        h = doc.add_paragraph()
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = h.add_run(parsed.name.upper())
        run.font.size = Pt(22)
        run.font.color.rgb = NAVY
        run.font.bold = True
        run.font.name = "Calibri"
        run.font.letter_spacing = Pt(2)
        _set_paragraph_spacing(h, before=0, after=4)

    if parsed.contact_lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_text = "  |  ".join(_split_contact_parts(parsed.contact_lines))
        run = p.add_run(contact_text)
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        run.font.name = "Calibri"
        run.font.letter_spacing = Pt(0.3)
        _set_paragraph_spacing(p, before=0, after=6)

    _add_horizontal_line(doc, "1a1a2e", 1)

    for section in parsed.sections:
        p = doc.add_paragraph()
        run = p.add_run(section.title.upper())
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = NAVY
        run.font.name = "Calibri"
        run.font.letter_spacing = Pt(1.5)
        _set_paragraph_spacing(p, before=10, after=3)
        _add_horizontal_line(doc, "cccccc", 0.5)

        for line in section.lines:
            stripped = line.strip()
            if not stripped:
                p = doc.add_paragraph()
                _set_paragraph_spacing(p, before=0, after=2)
                continue
            is_bullet = stripped.startswith(("•", "-", "–", "▪", "►", "✦", "*"))
            is_sub = _is_sub_header(stripped) and not is_bullet
            p = doc.add_paragraph()
            if is_bullet:
                text = stripped.lstrip("•-–▪►✦* ").strip()
                p.paragraph_format.left_indent = Inches(0.3)
                p.paragraph_format.first_line_indent = Inches(-0.15)
                run = p.add_run("•  " + text)
                run.font.size = Pt(10.5)
                run.font.color.rgb = DARK
            elif is_sub:
                run = p.add_run(stripped)
                run.font.size = Pt(11)
                run.font.bold = True
                run.font.color.rgb = RGBColor(0x2a, 0x2a, 0x2a)
            else:
                run = p.add_run(stripped)
                run.font.size = Pt(10.5)
                run.font.color.rgb = DARK
            run.font.name = "Calibri"
            _set_paragraph_spacing(p, before=1, after=1, line=14)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# Template 2: Modern Tech (two-column, dark sidebar)
# Font: Arial (universal fallback for Segoe UI). Inspired by Resume.io "Dublin".
# ══════════════════════════════════════════════════════════════════════════════

def _build_modern_tech(parsed: ParsedResume) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches

    SIDEBAR_BG = "0f172a"
    ACCENT = RGBColor(0x38, 0xbd, 0xf8)
    WHITE = RGBColor(0xff, 0xff, 0xff)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(10)
    style.font.color.rgb = RGBColor(0x2d, 0x2d, 0x2d)

    sec = doc.sections[0]
    sec.top_margin = Cm(0)
    sec.bottom_margin = Cm(1)
    sec.left_margin = Cm(0)
    sec.right_margin = Cm(0)

    sidebar_sections, main_sections = _partition_sections(parsed)

    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    table.allow_autofit = False
    _remove_table_borders(table)

    page_width = sec.page_width
    sidebar_w = int(page_width * 0.32)
    main_w = page_width - sidebar_w
    table.columns[0].width = sidebar_w
    table.columns[1].width = main_w

    left_cell = table.cell(0, 0)
    right_cell = table.cell(0, 1)
    left_cell.width = sidebar_w
    right_cell.width = main_w
    _set_cell_shading(left_cell, SIDEBAR_BG)
    _set_cell_margins(left_cell, top=300, bottom=300, left=170, right=100)
    _set_cell_vertical_alignment(left_cell, "top")
    _set_cell_margins(right_cell, top=300, bottom=200, left=200, right=200)
    _set_cell_vertical_alignment(right_cell, "top")

    for p in left_cell.paragraphs:
        p.clear()

    if parsed.name:
        p = _get_first_paragraph(left_cell)
        run = p.add_run(parsed.name)
        run.font.size = Pt(18)
        run.font.bold = True
        run.font.color.rgb = WHITE
        run.font.name = "Arial"
        _set_paragraph_spacing(p, before=6, after=4)
        p.paragraph_format.left_indent = Inches(0.15)

    if parsed.contact_lines:
        for part in _split_contact_parts(parsed.contact_lines):
            p = left_cell.add_paragraph()
            run = p.add_run(part)
            run.font.size = Pt(8.5)
            run.font.color.rgb = RGBColor(0x94, 0xa3, 0xb8)
            run.font.name = "Arial"
            _set_paragraph_spacing(p, before=1, after=1)
            p.paragraph_format.left_indent = Inches(0.15)

    for ssec in sidebar_sections:
        p = left_cell.add_paragraph()
        _set_paragraph_spacing(p, before=12, after=2)
        p.paragraph_format.left_indent = Inches(0.15)
        _set_paragraph_bottom_border(p, "38bdf8", sz="3")

        p = left_cell.add_paragraph()
        run = p.add_run(ssec.title.upper())
        run.font.size = Pt(10)
        run.font.bold = True
        run.font.color.rgb = ACCENT
        run.font.name = "Arial"
        run.font.letter_spacing = Pt(1)
        _set_paragraph_spacing(p, before=1, after=4)
        p.paragraph_format.left_indent = Inches(0.15)

        for line in ssec.lines:
            stripped = line.strip()
            if not stripped:
                continue
            is_bullet = stripped.startswith(("•", "-", "–", "▪", "►", "✦", "*"))
            if is_bullet:
                stripped = stripped.lstrip("•-–▪►✦* ").strip()
            p = left_cell.add_paragraph()
            run = p.add_run(("- " if is_bullet else "") + stripped)
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0xcb, 0xd5, 0xe1)
            run.font.name = "Arial"
            _set_paragraph_spacing(p, before=1, after=1)
            p.paragraph_format.left_indent = Inches(0.15)

    p = left_cell.add_paragraph()
    _set_paragraph_spacing(p, before=0, after=10)

    _set_cell_shading(right_cell, "ffffff")
    for p in right_cell.paragraphs:
        p.clear()

    first_main = True
    for msec in main_sections:
        p = _get_first_paragraph(right_cell) if first_main else right_cell.add_paragraph()
        first_main = False
        run = p.add_run(msec.title.upper())
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x0f, 0x17, 0x2a)
        run.font.name = "Arial"
        run.font.letter_spacing = Pt(1.5)
        _set_paragraph_spacing(p, before=10, after=2)
        p.paragraph_format.left_indent = Inches(0.1)

        p = right_cell.add_paragraph()
        _set_paragraph_bottom_border(p, "38bdf8", sz="4")
        _set_paragraph_spacing(p, before=0, after=6)
        p.paragraph_format.left_indent = Inches(0.1)

        for line in msec.lines:
            stripped = line.strip()
            if not stripped:
                p = right_cell.add_paragraph()
                _set_paragraph_spacing(p, before=0, after=3)
                continue
            is_bullet = stripped.startswith(("•", "-", "–", "▪", "►", "✦", "*"))
            is_sub = _is_sub_header(stripped) and not is_bullet
            p = right_cell.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.1)
            if is_bullet:
                text = stripped.lstrip("•-–▪►✦* ").strip()
                p.paragraph_format.left_indent = Inches(0.35)
                p.paragraph_format.first_line_indent = Inches(-0.15)
                run = p.add_run("- " + text)
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
            elif is_sub:
                run = p.add_run(stripped)
                run.font.size = Pt(10.5)
                run.font.bold = True
                run.font.color.rgb = RGBColor(0x1e, 0x29, 0x3b)
            else:
                run = p.add_run(stripped)
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
            run.font.name = "Arial"
            _set_paragraph_spacing(p, before=1, after=1, line=13.5)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# Template 3: Creative Portfolio
# Font: Georgia (universal serif). Inspired by Novoresume "Creative".
# ══════════════════════════════════════════════════════════════════════════════

def _build_creative_portfolio(parsed: ParsedResume) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches

    PURPLE = RGBColor(0x7c, 0x3a, 0xed)
    DARK = RGBColor(0x2d, 0x2d, 0x2d)
    GRAY = RGBColor(0x55, 0x55, 0x55)
    LIGHT_PURPLE = "c4b5fd"

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Georgia"
    style.font.size = Pt(10.5)
    style.font.color.rgb = DARK

    sec = doc.sections[0]
    sec.top_margin = Cm(2)
    sec.bottom_margin = Cm(2)
    sec.left_margin = Cm(2.5)
    sec.right_margin = Cm(2.5)

    if parsed.name:
        h = doc.add_paragraph()
        name = parsed.name
        if len(name) > 1:
            run1 = h.add_run(name[0])
            run1.font.size = Pt(36)
            run1.font.bold = True
            run1.font.color.rgb = PURPLE
            run1.font.name = "Georgia"
            run2 = h.add_run(name[1:])
            run2.font.size = Pt(28)
            run2.font.color.rgb = DARK
            run2.font.name = "Georgia"
        else:
            run = h.add_run(name)
            run.font.size = Pt(28)
            run.font.bold = True
            run.font.color.rgb = PURPLE
            run.font.name = "Georgia"
        _set_paragraph_spacing(h, before=0, after=2)

    # Purple accent bar
    p = doc.add_paragraph()
    _set_paragraph_bottom_border(p, "7c3aed", sz="12")
    _set_paragraph_spacing(p, before=0, after=4)

    if parsed.contact_lines:
        p = doc.add_paragraph()
        run = p.add_run("  |  ".join(_split_contact_parts(parsed.contact_lines)))
        run.font.size = Pt(9)
        run.font.color.rgb = GRAY
        run.font.name = "Georgia"
        run.font.italic = True
        _set_paragraph_spacing(p, before=0, after=10)

    for section in parsed.sections:
        p = doc.add_paragraph()
        _set_paragraph_spacing(p, before=14, after=2)
        run = p.add_run(section.title)
        run.font.size = Pt(14)
        run.font.bold = True
        run.font.color.rgb = PURPLE
        run.font.name = "Georgia"

        # Light purple underline
        _set_paragraph_bottom_border(p, LIGHT_PURPLE, sz="4")

        for line in section.lines:
            stripped = line.strip()
            if not stripped:
                p = doc.add_paragraph()
                _set_paragraph_spacing(p, before=0, after=3)
                continue
            is_bullet = stripped.startswith(("•", "-", "–", "▪", "►", "✦", "*"))
            is_sub = _is_sub_header(stripped) and not is_bullet
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.2)
            if is_bullet:
                text = stripped.lstrip("•-–▪►✦* ").strip()
                p.paragraph_format.left_indent = Inches(0.4)
                p.paragraph_format.first_line_indent = Inches(-0.15)
                run = p.add_run("- " + text)
                run.font.size = Pt(10.5)
                run.font.color.rgb = DARK
            elif is_sub:
                run = p.add_run(stripped)
                run.font.size = Pt(11)
                run.font.bold = True
                run.font.color.rgb = RGBColor(0x4a, 0x4a, 0x4a)
                run.font.italic = True
            else:
                run = p.add_run(stripped)
                run.font.size = Pt(10.5)
                run.font.color.rgb = DARK
            run.font.name = "Georgia"
            _set_paragraph_spacing(p, before=1, after=1, line=14)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# Template 4: Academic CV
# Font: Times New Roman (universal). Inspired by classic CV format.
# ══════════════════════════════════════════════════════════════════════════════

def _build_academic_research(parsed: ParsedResume) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    NAVY = RGBColor(0x0a, 0x2a, 0x4a)
    DARK = RGBColor(0x1a, 0x1a, 0x1a)
    GRAY = RGBColor(0x44, 0x44, 0x44)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)
    style.font.color.rgb = DARK
    style.paragraph_format.space_after = Pt(2)

    sec = doc.sections[0]
    sec.top_margin = Cm(2.54)
    sec.bottom_margin = Cm(2.54)
    sec.left_margin = Cm(2.54)
    sec.right_margin = Cm(2.54)

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = h.add_run("CURRICULUM VITAE")
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = NAVY
    run.font.name = "Times New Roman"
    run.font.letter_spacing = Pt(3)
    _set_paragraph_spacing(h, before=0, after=6)

    _add_horizontal_line(doc, "0a2a4a", 1.5)

    if parsed.name:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(parsed.name)
        run.font.size = Pt(18)
        run.font.bold = True
        run.font.color.rgb = DARK
        run.font.name = "Times New Roman"
        _set_paragraph_spacing(p, before=4, after=4)

    if parsed.contact_lines:
        for cl in parsed.contact_lines:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(cl)
            run.font.size = Pt(10)
            run.font.color.rgb = GRAY
            run.font.name = "Times New Roman"
            _set_paragraph_spacing(p, before=0, after=2)
        _add_horizontal_line(doc, "0a2a4a", 0.5)

    for section in parsed.sections:
        p = doc.add_paragraph()
        run = p.add_run(section.title.upper())
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = NAVY
        run.font.name = "Times New Roman"
        run.font.letter_spacing = Pt(1)
        _set_paragraph_spacing(p, before=14, after=2)
        _set_paragraph_bottom_border(p, "0a2a4a", sz="4")

        for line in section.lines:
            stripped = line.strip()
            if not stripped:
                p = doc.add_paragraph()
                _set_paragraph_spacing(p, before=0, after=3)
                continue
            is_bullet = stripped.startswith(("•", "-", "–", "▪", "►", "✦", "*"))
            is_sub = _is_sub_header(stripped) and not is_bullet
            p = doc.add_paragraph()
            if is_bullet:
                text = stripped.lstrip("•-–▪►✦* ").strip()
                p.paragraph_format.left_indent = Inches(0.5)
                p.paragraph_format.first_line_indent = Inches(-0.2)
                run = p.add_run("- " + text)
                run.font.size = Pt(11)
                run.font.color.rgb = DARK
            elif is_sub:
                p.paragraph_format.left_indent = Inches(0.3)
                run = p.add_run(stripped)
                run.font.size = Pt(11)
                run.font.bold = True
                run.font.color.rgb = DARK
            else:
                p.paragraph_format.left_indent = Inches(0.3)
                run = p.add_run(stripped)
                run.font.size = Pt(11)
                run.font.color.rgb = DARK
            run.font.name = "Times New Roman"
            _set_paragraph_spacing(p, before=1, after=1, line=15)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# Template 5: Executive (navy + gold, premium spacing)
# Font: Cambria (universal serif, replaces Garamond). Inspired by Resume.io "Sterling".
# ══════════════════════════════════════════════════════════════════════════════

def _build_executive(parsed: ParsedResume) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    NAVY = RGBColor(0x1b, 0x2a, 0x4a)
    GOLD = RGBColor(0xbf, 0x94, 0x3e)
    DARK = RGBColor(0x22, 0x22, 0x22)
    GRAY = RGBColor(0x66, 0x66, 0x66)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Cambria"
    style.font.size = Pt(11)
    style.font.color.rgb = DARK
    style.paragraph_format.space_after = Pt(3)

    sec = doc.sections[0]
    sec.top_margin = Cm(2.5)
    sec.bottom_margin = Cm(2.5)
    sec.left_margin = Cm(3)
    sec.right_margin = Cm(3)

    # Gold top border
    p = doc.add_paragraph()
    _set_paragraph_bottom_border(p, "bf943e", sz="12")
    _set_paragraph_spacing(p, before=0, after=10)

    if parsed.name:
        h = doc.add_paragraph()
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = h.add_run(parsed.name.upper())
        run.font.size = Pt(26)
        run.font.bold = True
        run.font.color.rgb = NAVY
        _set_run_font(run, "Cambria", "Georgia")
        run.font.letter_spacing = Pt(4)
        _set_paragraph_spacing(h, before=0, after=6)

    if parsed.contact_lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        parts = _split_contact_parts(parsed.contact_lines)
        run = p.add_run("  |  ".join(parts))
        run.font.size = Pt(9)
        run.font.color.rgb = GRAY
        _set_run_font(run, "Cambria", "Georgia")
        _set_paragraph_spacing(p, before=0, after=4)

    # Gold bottom border
    p = doc.add_paragraph()
    _set_paragraph_bottom_border(p, "bf943e", sz="12")
    _set_paragraph_spacing(p, before=4, after=12)

    for section in parsed.sections:
        p = doc.add_paragraph()
        run = p.add_run(section.title.upper())
        run.font.size = Pt(12.5)
        run.font.bold = True
        run.font.color.rgb = NAVY
        _set_run_font(run, "Cambria", "Georgia")
        run.font.letter_spacing = Pt(2)
        _set_paragraph_spacing(p, before=12, after=2)
        _set_paragraph_bottom_border(p, "bf943e", sz="6", space="2")

        for line in section.lines:
            stripped = line.strip()
            if not stripped:
                p = doc.add_paragraph()
                _set_paragraph_spacing(p, before=0, after=4)
                continue
            is_bullet = stripped.startswith(("•", "-", "–", "▪", "►", "✦", "*"))
            is_sub = _is_sub_header(stripped) and not is_bullet
            p = doc.add_paragraph()
            if is_bullet:
                text = stripped.lstrip("•-–▪►✦* ").strip()
                p.paragraph_format.left_indent = Inches(0.4)
                p.paragraph_format.first_line_indent = Inches(-0.2)
                run = p.add_run("•  " + text)
                run.font.size = Pt(11)
                run.font.color.rgb = DARK
            elif is_sub:
                run = p.add_run(stripped)
                run.font.size = Pt(11.5)
                run.font.bold = True
                run.font.color.rgb = NAVY
            else:
                p.paragraph_format.left_indent = Inches(0.1)
                run = p.add_run(stripped)
                run.font.size = Pt(11)
                run.font.color.rgb = DARK
            _set_run_font(run, "Cambria", "Georgia")
            _set_paragraph_spacing(p, before=2, after=2, line=15)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# Template 6: Minimalist Clean
# Font: Calibri Light (universal, replaces Helvetica). #1 most downloaded style.
# Inspired by Canva "Black White Minimalist" / Resume.io "Essential".
# ══════════════════════════════════════════════════════════════════════════════

def _build_minimalist_clean(parsed: ParsedResume) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches

    BLACK = RGBColor(0x11, 0x11, 0x11)
    MID = RGBColor(0x55, 0x55, 0x55)
    LIGHT = RGBColor(0x99, 0x99, 0x99)
    FONT = "Calibri Light"

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(10)
    style.font.color.rgb = MID
    style.paragraph_format.space_after = Pt(2)

    sec = doc.sections[0]
    sec.top_margin = Cm(3.5)
    sec.bottom_margin = Cm(3)
    sec.left_margin = Cm(3)
    sec.right_margin = Cm(3)

    if parsed.name:
        h = doc.add_paragraph()
        run = h.add_run(parsed.name)
        run.font.size = Pt(28)
        run.font.color.rgb = BLACK
        run.font.name = FONT
        _set_paragraph_spacing(h, before=0, after=4)

    if parsed.contact_lines:
        p = doc.add_paragraph()
        parts = _split_contact_parts(parsed.contact_lines)
        run = p.add_run("    ".join(parts))
        run.font.size = Pt(8.5)
        run.font.color.rgb = LIGHT
        run.font.name = FONT
        _set_paragraph_spacing(p, before=0, after=18)

    for section in parsed.sections:
        p = doc.add_paragraph()
        run = p.add_run(section.title.lower())
        run.font.size = Pt(9)
        run.font.bold = True
        run.font.color.rgb = BLACK
        run.font.name = FONT
        run.font.letter_spacing = Pt(2)
        _set_paragraph_spacing(p, before=16, after=6)
        _add_horizontal_line(doc, "dddddd", 0.25)

        for line in section.lines:
            stripped = line.strip()
            if not stripped:
                p = doc.add_paragraph()
                _set_paragraph_spacing(p, before=0, after=4)
                continue
            is_bullet = stripped.startswith(("•", "-", "–", "▪", "►", "✦", "*"))
            is_sub = _is_sub_header(stripped) and not is_bullet
            p = doc.add_paragraph()
            if is_bullet:
                text = stripped.lstrip("•-–▪►✦* ").strip()
                p.paragraph_format.left_indent = Inches(0.2)
                run = p.add_run("-  " + text)
                run.font.size = Pt(10)
                run.font.color.rgb = MID
            elif is_sub:
                run = p.add_run(stripped)
                run.font.size = Pt(10.5)
                run.font.bold = True
                run.font.color.rgb = BLACK
            else:
                run = p.add_run(stripped)
                run.font.size = Pt(10)
                run.font.color.rgb = MID
            run.font.name = FONT
            _set_paragraph_spacing(p, before=1, after=1, line=14)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# Template 7: Corporate Elegance (single-column with teal header block)
# Restructured from two-column to single-column for better ATS compatibility
# and visual differentiation from Modern Tech.
# Font: Calibri (universal). Inspired by Resume.io "Corporate" / Zety "Elegant".
# ══════════════════════════════════════════════════════════════════════════════

def _build_corporate_elegance(parsed: ParsedResume) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    TEAL_BG = "134e4a"
    TEAL = RGBColor(0x14, 0xb8, 0xa6)
    DARK = RGBColor(0x1f, 0x2a, 0x37)
    GRAY = RGBColor(0x4b, 0x55, 0x63)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style.font.color.rgb = DARK

    sec = doc.sections[0]
    sec.top_margin = Cm(0)
    sec.bottom_margin = Cm(2)
    sec.left_margin = Cm(2.5)
    sec.right_margin = Cm(2.5)

    # Teal header block using full-width table
    header_tbl = doc.add_table(rows=1, cols=1)
    header_tbl.autofit = True
    _remove_table_borders(header_tbl)
    header_cell = header_tbl.cell(0, 0)
    _set_cell_shading(header_cell, TEAL_BG)
    _set_cell_margins(header_cell, top=350, bottom=350, left=300, right=300)

    for p in header_cell.paragraphs:
        p.clear()

    if parsed.name:
        p = _get_first_paragraph(header_cell)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(parsed.name.upper())
        run.font.size = Pt(24)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0xff, 0xff, 0xff)
        run.font.name = "Calibri"
        run.font.letter_spacing = Pt(3)
        _set_paragraph_spacing(p, before=4, after=4)

    if parsed.contact_lines:
        p = header_cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        parts = _split_contact_parts(parsed.contact_lines)
        run = p.add_run("  |  ".join(parts))
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xa7, 0xf3, 0xd0)
        run.font.name = "Calibri"
        _set_paragraph_spacing(p, before=0, after=4)

    # Teal accent line after header
    p = doc.add_paragraph()
    _set_paragraph_bottom_border(p, "14b8a6", sz="8")
    _set_paragraph_spacing(p, before=0, after=8)

    for section in parsed.sections:
        p = doc.add_paragraph()
        run = p.add_run(section.title.upper())
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0x13, 0x4e, 0x4a)
        run.font.name = "Calibri"
        run.font.letter_spacing = Pt(1.5)
        _set_paragraph_spacing(p, before=12, after=2)
        _set_paragraph_bottom_border(p, "14b8a6", sz="3")

        for line in section.lines:
            stripped = line.strip()
            if not stripped:
                p = doc.add_paragraph()
                _set_paragraph_spacing(p, before=0, after=3)
                continue
            is_bullet = stripped.startswith(("•", "-", "–", "▪", "►", "✦", "*"))
            is_sub = _is_sub_header(stripped) and not is_bullet
            p = doc.add_paragraph()
            if is_bullet:
                text = stripped.lstrip("•-–▪►✦* ").strip()
                p.paragraph_format.left_indent = Inches(0.35)
                p.paragraph_format.first_line_indent = Inches(-0.15)
                run = p.add_run("•  " + text)
                run.font.size = Pt(10.5)
                run.font.color.rgb = GRAY
            elif is_sub:
                run = p.add_run(stripped)
                run.font.size = Pt(11)
                run.font.bold = True
                run.font.color.rgb = DARK
            else:
                run = p.add_run(stripped)
                run.font.size = Pt(10.5)
                run.font.color.rgb = GRAY
            run.font.name = "Calibri"
            _set_paragraph_spacing(p, before=1, after=1, line=14)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# Template 8: Fresh Graduate (compact, friendly, skills-first)
# Font: Arial (universal). Inspired by Novoresume "Functional Modern".
# Skills sections are formatted as comma-separated inline text.
# ══════════════════════════════════════════════════════════════════════════════

def _build_fresh_graduate(parsed: ParsedResume) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    BLUE = RGBColor(0x25, 0x63, 0xeb)
    DARK = RGBColor(0x1e, 0x29, 0x3b)
    GRAY = RGBColor(0x4b, 0x55, 0x63)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(10)
    style.font.color.rgb = DARK

    sec = doc.sections[0]
    sec.top_margin = Cm(0)
    sec.bottom_margin = Cm(1.5)
    sec.left_margin = Cm(2)
    sec.right_margin = Cm(2)

    # Blue header bar
    header_tbl = doc.add_table(rows=1, cols=1)
    header_tbl.autofit = True
    _remove_table_borders(header_tbl)
    header_cell = header_tbl.cell(0, 0)
    _set_cell_shading(header_cell, "2563eb")
    _set_cell_margins(header_cell, top=250, bottom=250, left=200, right=200)

    for p in header_cell.paragraphs:
        p.clear()

    if parsed.name:
        p = _get_first_paragraph(header_cell)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(parsed.name.upper())
        run.font.size = Pt(22)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0xff, 0xff, 0xff)
        run.font.name = "Arial"
        run.font.letter_spacing = Pt(3)
        _set_paragraph_spacing(p, before=4, after=4)

    if parsed.contact_lines:
        p = header_cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        parts = _split_contact_parts(parsed.contact_lines)
        run = p.add_run("  |  ".join(parts))
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xdb, 0xea, 0xfe)
        run.font.name = "Arial"
        _set_paragraph_spacing(p, before=0, after=4)

    p = doc.add_paragraph()
    _set_paragraph_spacing(p, before=4, after=4)

    # Reorder: put skills/education before experience for fresh grads
    skills_first = []
    experience_later = []
    for s in parsed.sections:
        title_lower = s.title.lower()
        if any(k in title_lower for k in ("skill", "education", "certif", "language", "award")):
            skills_first.append(s)
        else:
            experience_later.append(s)
    ordered_sections = skills_first + experience_later

    for section in ordered_sections:
        p = doc.add_paragraph()
        run = p.add_run(section.title.upper())
        run.font.size = Pt(11.5)
        run.font.bold = True
        run.font.color.rgb = DARK
        run.font.name = "Arial"
        run.font.letter_spacing = Pt(1)
        _set_paragraph_spacing(p, before=10, after=2)
        _set_paragraph_bottom_border(p, "93c5fd", sz="4")

        # Format skills sections as comma-separated inline text
        if _is_skills_section(section.title):
            inline = _format_skills_inline(section.lines)
            if inline:
                p = doc.add_paragraph()
                run = p.add_run(inline)
                run.font.size = Pt(10)
                run.font.color.rgb = GRAY
                run.font.name = "Arial"
                _set_paragraph_spacing(p, before=3, after=3, line=14)
            continue

        for line in section.lines:
            stripped = line.strip()
            if not stripped:
                p = doc.add_paragraph()
                _set_paragraph_spacing(p, before=0, after=2)
                continue
            is_bullet = stripped.startswith(("•", "-", "–", "▪", "►", "✦", "*"))
            is_sub = _is_sub_header(stripped) and not is_bullet
            p = doc.add_paragraph()
            if is_bullet:
                text = stripped.lstrip("•-–▪►✦* ").strip()
                p.paragraph_format.left_indent = Inches(0.3)
                p.paragraph_format.first_line_indent = Inches(-0.15)
                run = p.add_run("- " + text)
                run.font.size = Pt(10)
                run.font.color.rgb = GRAY
            elif is_sub:
                run = p.add_run(stripped)
                run.font.size = Pt(10.5)
                run.font.bold = True
                run.font.color.rgb = DARK
            else:
                run = p.add_run(stripped)
                run.font.size = Pt(10)
                run.font.color.rgb = GRAY
            run.font.name = "Arial"
            _set_paragraph_spacing(p, before=1, after=1, line=13)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

_TEMPLATE_BUILDERS = {
    "professional_classic": _build_professional_classic,
    "modern_tech": _build_modern_tech,
    "creative_portfolio": _build_creative_portfolio,
    "academic_research": _build_academic_research,
    "executive": _build_executive,
    "minimalist_clean": _build_minimalist_clean,
    "corporate_elegance": _build_corporate_elegance,
    "fresh_graduate": _build_fresh_graduate,
}


def _resolve_template_key(template_id: str, db: Session) -> str:
    """Map template_id to a builder key."""
    clean = template_id.strip().lstrip("_")
    for key in _TEMPLATE_BUILDERS:
        if clean == key or clean.replace(".docx", "") == key:
            return key

    row = db.execute(
        sa_text("SELECT template_file FROM resume_templates WHERE template_id = :tid AND is_active = TRUE LIMIT 1"),
        {"tid": template_id},
    ).mappings().first()
    if row:
        fname = (row.get("template_file") or "").replace(".docx", "").strip()
        if fname in _TEMPLATE_BUILDERS:
            return fname

    return "professional_classic"


def apply_template(
    db: Session,
    review_id: str,
    template_id: str,
    resume_content: str,
    template_file: Optional[str] = None,
) -> bytes:
    """
    Parse resume_content into structured sections, then build a fully-formatted
    DOCX using the template identified by template_id.
    """
    _ensure_docx()

    key = _resolve_template_key(template_id, db)

    if template_file:
        fname = template_file.replace(".docx", "").strip()
        if fname in _TEMPLATE_BUILDERS:
            key = fname

    _log.info("apply_template: using builder '%s' for template_id='%s'", key, template_id)

    parsed = parse_resume(resume_content or "")
    _log.info(
        "apply_template: parsed name='%s', %d contact lines, %d sections",
        parsed.name, len(parsed.contact_lines), len(parsed.sections),
    )

    builder = _TEMPLATE_BUILDERS.get(key, _build_professional_classic)
    return builder(parsed)
