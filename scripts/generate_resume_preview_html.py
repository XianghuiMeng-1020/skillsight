"""Generate per-template HTML previews from backend render pipeline."""

from __future__ import annotations

from pathlib import Path

from backend.app.services.resume_structured import html_preview_for_resume


SAMPLE_RESUME = """Alex Chen
alex.chen@example.com | +852 9123 4567 | linkedin.com/in/alexchen

Summary
Data-oriented product analyst with strong communication and execution across cross-functional teams.

Experience
Product Analyst | HK Startup | 2022-Present
- Built KPI dashboards reducing weekly reporting time by 35%.
- Partnered with engineering to launch 3 workflow automations.

Education
BSc in Information Management, The University of Hong Kong

Skills
Python, SQL, Tableau, A/B Testing, Stakeholder Management, Communication
"""

TEMPLATE_KEYS = [
    "professional_classic",
    "modern_tech",
    "creative_portfolio",
    "academic_research",
    "executive",
    "minimalist_clean",
    "corporate_elegance",
    "fresh_graduate",
]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "web" / "public" / "resume-templates" / "_html"
    out_dir.mkdir(parents=True, exist_ok=True)
    for key in TEMPLATE_KEYS:
        html = html_preview_for_resume(SAMPLE_RESUME, key)
        (out_dir / f"{key}.html").write_text(html, encoding="utf-8")
    print(f"Generated HTML previews under {out_dir}")


if __name__ == "__main__":
    main()
