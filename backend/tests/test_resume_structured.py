"""Tests for resume JSON layer, layout health, and HTML preview."""
import zipfile
from io import BytesIO

from backend.app.services.resume_structured import (
    enhance_parsed_for_export,
    html_preview_for_resume,
    layout_health_check,
    resume_text_to_resume_json,
    score_templates_for_role,
)
from backend.app.services.resume_template_service import apply_template, parse_resume


def test_layout_health_detects_long_lines():
    long = "x" * 600
    r = layout_health_check("Name\n\nExperience\n" + long)
    assert r["score"] < 100
    assert any(i["code"] == "long_line" for i in r["issues"])


def test_resume_json_skills_split():
    text = """Jane Doe
jane@mail.com | +1-555-0100

Skills
Python, JavaScript, TypeScript, React, Node.js, Docker, Kubernetes, AWS, GCP, Terraform, SQL, PostgreSQL, Redis, Git, CI/CD, Agile

Experience
Acme Corp | Engineer | 2020-2022
Built things.
"""
    doc = resume_text_to_resume_json(text)
    skills = [s for s in doc.sections if "skill" in s.title.lower()]
    assert skills
    assert len(skills[0].lines) > 1


def test_enhance_parsed_roundtrip():
    text = """John Smith
john@example.com

Work Experience
Foo Inc | Dev | 2021–Present
• Did stuff.
"""
    p0 = parse_resume(text)
    p1 = enhance_parsed_for_export(p0)
    assert p1.name or p0.name


def test_html_preview_contains_name():
    html = html_preview_for_resume("Alice\nalice@x.com\n\nSummary\nHello.", "professional_classic")
    assert "Alice" in html
    assert "<!DOCTYPE html>" in html


def test_score_templates_for_role():
    templates = [
        {"name": "A", "industry_tags": ["technology", "software"], "template_id": "1"},
        {"name": "B", "industry_tags": ["finance"], "template_id": "2"},
    ]
    out = score_templates_for_role(templates, "Senior Software Engineer")
    assert out[0].get("recommend_score", 0) >= out[-1].get("recommend_score", 0)


def test_apply_template_produces_valid_docx():
    from unittest.mock import MagicMock

    db = MagicMock()
    sample = """Pat Lee
pat@example.com | github.com/pat

Summary
Builder.

Experience
Co | Role | 2022–Present
• Shipped features.
"""
    raw = apply_template(db, review_id="r1", template_id="professional_classic", resume_content=sample)
    assert zipfile.is_zipfile(BytesIO(raw))


def test_apply_template_options_postprocess_valid_docx():
    from unittest.mock import MagicMock

    db = MagicMock()
    sample = """Pat Lee
pat@example.com | github.com/pat

Summary
Builder.
"""
    raw = apply_template(
        db,
        review_id="r1",
        template_id="professional_classic",
        resume_content=sample,
        template_options={"font_scale_pct": 112, "line_spacing_pct": 118, "accent_color": "teal"},
    )
    assert zipfile.is_zipfile(BytesIO(raw))


def test_apply_template_options_accent_color_emitted():
    from unittest.mock import MagicMock

    db = MagicMock()
    sample = """Pat Lee
pat@example.com

EXPERIENCE
Built features.
"""
    raw = apply_template(
        db,
        review_id="r1",
        template_id="professional_classic",
        resume_content=sample,
        template_options={"accent_color": "gold"},
    )
    with zipfile.ZipFile(BytesIO(raw), "r") as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8")
    assert "BF943E" in document_xml


def test_apply_template_all_builders_produce_docx():
    from unittest.mock import MagicMock

    db = MagicMock()
    sample = """Pat Lee
pat@example.com | github.com/pat

Summary
Builder.

Work History
Co | Role | 2022–Present
• Shipped features.
"""
    for template_id in (
        "professional_classic",
        "modern_tech",
        "creative_portfolio",
        "academic_research",
        "executive",
        "minimalist_clean",
        "corporate_elegance",
        "fresh_graduate",
    ):
        raw = apply_template(db, review_id="r1", template_id=template_id, resume_content=sample)
        assert zipfile.is_zipfile(BytesIO(raw))


def test_parse_resume_handles_inline_section_header():
    parsed = parse_resume(
        """Summary
Short intro.
EXPERIENCE | Acme Corp
Built platform.
"""
    )
    assert any(sec.title.lower().startswith("experience") for sec in parsed.sections)


def test_parse_resume_accepts_work_history_without_name():
    parsed = parse_resume(
        """Summary
Data scientist with internship background.

Work History
Company X
"""
    )
    assert parsed.sections
    assert any("history" in sec.title.lower() for sec in parsed.sections)


def test_resume_json_public_basics_has_contacts():
    doc = resume_text_to_resume_json(
        """Jane Doe
jane@example.com | +852 1234 5678 | linkedin.com/in/jane

Summary
Hello.
"""
    )
    public = doc.to_public_dict()
    assert public["contact_lines"]
    assert public["basics"]["email"]


def test_html_preview_applies_template_options():
    html = html_preview_for_resume(
        "Alice\nalice@x.com\n\nSummary\nHello.",
        "professional_classic",
        {"font_scale_pct": 115, "line_spacing_pct": 120, "accent_color": "gold"},
    )
    assert "font-size:115%" in html
    assert "#bf943e" in html
