"""
Structured resume (JSON intermediate layer), layout health checks, and HTML preview.

Used to improve consistency between sources (PDF/DOCX) and to power preview/export UX.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from backend.app.services.resume_template_service import ParsedResume, ResumeSection, parse_resume

SectionKind = Literal["summary", "experience", "education", "skills", "projects", "other"]


def _contains_cjk(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text))


def classify_section_kind(title: str) -> SectionKind:
    t = (title or "").strip().lower()
    zh = (title or "").strip()
    if any(
        k in t
        for k in (
            "summary",
            "profile",
            "objective",
            "about",
        )
    ) or any(x in zh for x in ("简介", "摘要", "自我评价", "求职意向")):
        return "summary"
    if any(
        k in t
        for k in (
            "experience",
            "employment",
            "work",
            "internship",
        )
    ) or any(x in zh for x in ("工作经历", "工作经验", "实习")):
        return "experience"
    if "education" in t or any(x in zh for x in ("教育", "学历")):
        return "education"
    if "skill" in t or "competenc" in t or any(x in zh for x in ("技能", "能力")):
        return "skills"
    if "project" in t or "作品" in zh:
        return "projects"
    return "other"


@dataclass
class StructuredSection:
    title: str
    kind: SectionKind
    lines: List[str] = field(default_factory=list)


@dataclass
class ResumeJsonDocument:
    """Server-side mirror of web ResumeJsonDocument + section kinds."""

    name: str = ""
    contact_lines: List[str] = field(default_factory=list)
    sections: List[StructuredSection] = field(default_factory=list)
    locale_hint: str = "auto"  # en | zh | mixed | auto

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "basics": {
                "name": self.name or None,
                "summary": None,
            },
            "sections": [
                {"title": s.title, "kind": s.kind, "lines": s.lines}
                for s in self.sections
            ],
            "locale_hint": self.locale_hint,
        }


def parsed_to_resume_json(parsed: ParsedResume) -> ResumeJsonDocument:
    """Build structured JSON from heuristic parse (Phase 2 intermediate layer)."""
    blob = "\n".join(
        [parsed.name]
        + parsed.contact_lines
        + [" ".join(sec.lines) for sec in parsed.sections]
    )
    if _contains_cjk(blob) and re.search(r"[a-zA-Z]{3,}", blob):
        locale = "mixed"
    elif _contains_cjk(blob):
        locale = "zh"
    else:
        locale = "en"

    sections: List[StructuredSection] = []
    for sec in parsed.sections:
        kind = classify_section_kind(sec.title)
        lines = [ln for ln in sec.lines if ln.strip()]
        if kind == "skills":
            lines = _normalize_skill_lines(lines)
        sections.append(StructuredSection(title=sec.title, kind=kind, lines=lines))

    return ResumeJsonDocument(
        name=parsed.name,
        contact_lines=list(parsed.contact_lines),
        sections=sections,
        locale_hint=locale,
    )


def _normalize_skill_lines(lines: List[str]) -> List[str]:
    """Split very long comma-separated skill lines for nicer DOCX wrapping."""
    out: List[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if len(s) > 120 and ("," in s or "，" in s):
            parts = re.split(r"[,，、;；]\s*", s)
            for p in parts:
                p = p.strip()
                if p:
                    out.append(p)
        else:
            out.append(s)
    return out


def resume_text_to_resume_json(text: str) -> ResumeJsonDocument:
    return parsed_to_resume_json(parse_resume(text or ""))


def structured_to_parsed(doc: ResumeJsonDocument) -> ParsedResume:
    """Round-trip for template builders (semantic normalization + ParsedResume)."""
    sections = [ResumeSection(title=s.title, lines=list(s.lines)) for s in doc.sections]
    return ParsedResume(name=doc.name, contact_lines=list(doc.contact_lines), sections=sections)


def enhance_parsed_for_export(parsed: ParsedResume) -> ParsedResume:
    """Normalize skills lines and section structure before DOCX build."""
    return structured_to_parsed(parsed_to_resume_json(parsed))


def layout_health_check(resume_text: str) -> Dict[str, Any]:
    """
    Heuristic layout / readability issues before export (Phase 3 "版面体检").
    """
    text = resume_text or ""
    issues: List[Dict[str, str]] = []
    if len(text.strip()) < 200:
        issues.append({"level": "warn", "code": "short", "message": "Content is quite short; add sections for a stronger CV."})
    lines = text.splitlines()
    long_lines = [i for i, ln in enumerate(lines) if len(ln) > 500]
    if long_lines:
        issues.append(
            {
                "level": "warn",
                "code": "long_line",
                "message": f"Found {len(long_lines)} very long line(s); exported layout may look dense.",
            }
        )
    huge_paras = sum(1 for ln in lines if len(ln) > 800)
    if huge_paras:
        issues.append({"level": "info", "code": "dense_block", "message": "Some blocks are very long; consider bullet points."})
    if not re.search(r"(?i)(experience|education|skills|work|项目|教育|技能)", text):
        issues.append({"level": "info", "code": "weak_sections", "message": "No clear section headers detected; export grouping may be generic."})
    score = max(0, 100 - len(issues) * 12)
    return {"score": score, "issues": issues, "locale_hint": "zh" if _contains_cjk(text) else "en"}


# ── HTML preview (approximate WYSIWYG for web; not Word-perfect) ──────────────

_TEMPLATE_PREVIEW_STYLES: Dict[str, Dict[str, str]] = {
    "professional_classic": {"bg": "#1a1a2e", "accent": "#e2b04a", "font": "Calibri, sans-serif"},
    "modern_tech": {"bg": "#0f172a", "accent": "#38bdf8", "font": "Arial, sans-serif"},
    "creative_portfolio": {"bg": "#4c1d95", "accent": "#c4b5fd", "font": "Georgia, serif"},
    "academic_research": {"bg": "#0a2a4a", "accent": "#99d5c9", "font": "Times New Roman, serif"},
    "executive": {"bg": "#1b2a4a", "accent": "#bf943e", "font": "Cambria, serif"},
    "minimalist_clean": {"bg": "#f5f5f5", "accent": "#111111", "font": "Calibri, sans-serif"},
    "corporate_elegance": {"bg": "#134e4a", "accent": "#14b8a6", "font": "Calibri, sans-serif"},
    "fresh_graduate": {"bg": "#1e40af", "accent": "#93c5fd", "font": "Arial, sans-serif"},
}


def html_preview_for_resume(resume_text: str, template_key: str) -> str:
    """Generate a single-page HTML preview mirroring template palette."""
    doc = resume_text_to_resume_json(resume_text)
    st = _TEMPLATE_PREVIEW_STYLES.get(template_key, _TEMPLATE_PREVIEW_STYLES["professional_classic"])
    name = html.escape(doc.name or "Your Name")
    contact = html.escape("  |  ".join(_flatten_contact(doc.contact_lines)))

    parts: List[str] = []
    for sec in doc.sections:
        title = html.escape(sec.title)
        parts.append(f'<section class="sec"><h2>{title}</h2><div class="body">')
        for ln in sec.lines:
            line = html.escape(ln.strip())
            if ln.strip().startswith(("•", "-", "–", "*")) or re.match(r"^\d{1,2}[\.\)]\s", ln.strip()):
                parts.append(f'<p class="bullet">{line}</p>')
            else:
                parts.append(f"<p>{line}</p>")
        parts.append("</div></section>")

    body_html = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Resume preview</title>
<style>
body {{ margin:0; background:{st["bg"]}; font-family:{st["font"]}; color:#e5e7eb; }}
.wrap {{ max-width:720px; margin:0 auto; padding:24px; background:rgba(0,0,0,0.25); min-height:100vh; }}
header {{ text-align:center; padding:16px 0; border-bottom:2px solid {st["accent"]}; margin-bottom:16px; }}
h1 {{ margin:0; font-size:1.75rem; letter-spacing:0.05em; color:#fff; }}
.contact {{ font-size:0.85rem; color:#cbd5e1; margin-top:8px; }}
.sec h2 {{ font-size:0.95rem; color:{st["accent"]}; text-transform:uppercase; letter-spacing:0.08em; border-bottom:1px solid rgba(255,255,255,0.15); padding-bottom:4px; margin:20px 0 8px; }}
.body p {{ margin:6px 0; font-size:0.9rem; line-height:1.45; color:#d1d5db; }}
.bullet {{ padding-left:12px; border-left:2px solid {st["accent"]}; }}
</style></head><body><div class="wrap">
<header><h1>{name}</h1><div class="contact">{contact}</div></header>
{body_html}
<p style="text-align:center;font-size:0.75rem;color:#6b7280;margin-top:32px;">Preview approximates export styling — Word may differ slightly.</p>
</div></body></html>"""


def _flatten_contact(contact_lines: List[str]) -> List[str]:
    parts: List[str] = []
    for cl in contact_lines:
        for p in re.split(r"[|·•]", cl):
            p = p.strip()
            if p:
                parts.append(p)
    return parts


def score_templates_for_role(
    templates: List[Dict[str, Any]],
    role_title: Optional[str],
) -> List[Dict[str, Any]]:
    """Attach recommend_score (0-100) and recommended flag for gallery sorting."""
    if not role_title:
        for t in templates:
            t["recommend_score"] = 50
            t["recommended"] = False
        return templates
    title_l = role_title.lower()
    keywords = set(re.findall(r"[a-zA-Z]{3,}", title_l))
    for t in templates:
        tags = t.get("industry_tags") or []
        if isinstance(tags, str):
            tags = []
        tag_blob = " ".join(str(x).lower() for x in tags)
        score = 40
        for kw in keywords:
            if kw in tag_blob:
                score += 15
        if any(x in title_l for x in ("engineer", "developer", "software")) and any(
            x in tag_blob for x in ("tech", "software", "engineering")
        ):
            score += 20
        if any(x in title_l for x in ("manager", "lead", "director")) and "executive" in tag_blob:
            score += 20
        if any(x in title_l for x in ("research", "phd", "academic")) and "academic" in tag_blob:
            score += 20
        score = min(100, score)
        t["recommend_score"] = score
        t["recommended"] = score >= 70
    templates.sort(key=lambda x: (-x.get("recommend_score", 0), x.get("name", "")))
    return templates
