#!/usr/bin/env python3
"""
Create 8 sample resume template DOCX files under backend/data/templates/.

The actual export builds documents programmatically in resume_template_service.py.
This script generates sample files using the same builders for previewing/debugging.
"""
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

TEMPLATES_DIR = project_root / "backend" / "data" / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_CONTENT = """John Smith
john.smith@email.com | +1 (555) 123-4567 | linkedin.com/in/johnsmith | New York, NY

SUMMARY
Results-driven software engineer with 5+ years of experience in full-stack development.
Passionate about building scalable applications and mentoring junior developers.

EXPERIENCE
Senior Software Engineer — TechCorp Inc. (2021 – Present)
• Led a team of 6 engineers to deliver a microservices platform serving 2M+ users
• Redesigned the authentication system, reducing login failures by 40%
• Implemented CI/CD pipelines that cut deployment time from 2 hours to 15 minutes

Software Engineer — StartupXYZ (2019 – 2021)
• Built RESTful APIs using Python/FastAPI handling 10K+ requests per second
• Developed React-based dashboard used by 500+ enterprise clients
• Reduced database query times by 60% through query optimization and indexing

EDUCATION
Master of Science in Computer Science — Stanford University (2019)
Bachelor of Science in Computer Science — UC Berkeley (2017)

SKILLS
• Python, JavaScript, TypeScript, Go
• React, Next.js, FastAPI, Django
• PostgreSQL, Redis, MongoDB
• AWS, Docker, Kubernetes, CI/CD
• System Design, Agile/Scrum

CERTIFICATIONS
• AWS Solutions Architect – Professional
• Google Cloud Professional Data Engineer

PROJECTS
Open-Source Resume Builder (2022)
• Built a tool that generates ATS-friendly resumes from YAML input
• 500+ GitHub stars, 50+ contributors

LANGUAGES
• English (Native)
• Mandarin Chinese (Fluent)
"""


def create_all():
    from backend.app.services.resume_template_service import parse_resume, _TEMPLATE_BUILDERS

    parsed = parse_resume(SAMPLE_CONTENT)
    for key, builder in _TEMPLATE_BUILDERS.items():
        doc_bytes = builder(parsed)
        out_path = TEMPLATES_DIR / f"{key}.docx"
        out_path.write_bytes(doc_bytes)
        print(f"  Created: {key}.docx ({len(doc_bytes)} bytes)")


if __name__ == "__main__":
    create_all()
    print(f"\nAll {8} template DOCX files created in {TEMPLATES_DIR}")
