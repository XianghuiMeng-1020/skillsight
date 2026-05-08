#!/usr/bin/env python3
"""
Phase 2: Enrich LinkedIn jobs with full descriptions, extract skills, and load everything into SkillSight.

Steps:
  1. Read roles_import_*_linkedin.json (from Phase 1 crawl)
  2. For each job, fetch the LinkedIn public detail page -> extract full job description
  3. Extract skills from full description using comprehensive keyword matching
  4. Write enriched roles JSON + updated CSV
  5. Generate skills seed, courses seed, course-skill map from the two programme PDFs
  6. Import everything into the running SkillSight API

Usage:
  export LINKEDIN_CRAWL_ALLOWED=1
  python3 scripts/enrich_and_load.py
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

REPO_ROOT = Path(__file__).resolve().parents[1]

BROWSER_UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

MIN_DELAY = 4.0
MAX_DELAY = 8.0

# ---------------------------------------------------------------------------
# Comprehensive skill keyword bank (covers both SDS and IM programmes)
# ---------------------------------------------------------------------------
SKILL_BANK = {
    "HKU.SKILL.PYTHON.v1": {
        "canonical_name": "Python Programming",
        "keywords": ["python"],
        "aliases": ["Python", "Python3", "Python coding"],
        "definition": "Writing, debugging, and maintaining Python programs for data processing, automation, and analysis.",
        "evidence_rules": "Evidence includes runnable Python code demonstrating correct logic.",
        "level_rubric": {"0": "No Python artifact.", "1": "Small scripts with guidance.", "2": "Multi-step tasks independently.", "3": "Robust modules, tests, clear APIs."},
    },
    "HKU.SKILL.R.v1": {
        "canonical_name": "R Programming",
        "keywords": ["\\br\\b", "r programming", "r studio", "rstudio", "tidyverse", "ggplot"],
        "aliases": ["R", "R language", "RStudio"],
        "definition": "Using R for statistical computing, data analysis, and visualization.",
        "evidence_rules": "Evidence includes R scripts, analysis outputs, or Shiny apps.",
        "level_rubric": {"0": "No R artifact.", "1": "Basic scripts with guidance.", "2": "Independent analysis and visualization.", "3": "Reproducible workflows, packages."},
    },
    "HKU.SKILL.SQL.v1": {
        "canonical_name": "SQL & Databases",
        "keywords": ["sql", "database", "postgresql", "mysql", "oracle", "nosql", "mongodb", "relational database"],
        "aliases": ["SQL", "database management", "RDBMS"],
        "definition": "Querying and managing relational/non-relational databases.",
        "evidence_rules": "Evidence includes queries, schema design, or database artifacts.",
        "level_rubric": {"0": "No database evidence.", "1": "Simple SELECT with guidance.", "2": "Joins, aggregation, design.", "3": "Complex queries, optimization, administration."},
    },
    "HKU.SKILL.STATISTICS.v1": {
        "canonical_name": "Statistics & Quantitative Methods",
        "keywords": ["statistics", "statistical", "regression", "hypothesis test", "quantitative", "econometrics", "bayesian", "anova", "spss", "stata"],
        "aliases": ["statistics", "statistical analysis", "quantitative methods"],
        "definition": "Applying statistical methods for data analysis, inference, and modeling.",
        "evidence_rules": "Evidence shows use of descriptive/inferential statistics, tests, or models.",
        "level_rubric": {"0": "No statistical evidence.", "1": "Basic descriptive stats.", "2": "Inference, regression, interpretation.", "3": "Advanced modeling, validation."},
    },
    "HKU.SKILL.DATA_VIS.v1": {
        "canonical_name": "Data Visualization",
        "keywords": ["data visualization", "visualization", "tableau", "power bi", "dashboard", "matplotlib", "seaborn", "d3.js", "grafana", "qlik"],
        "aliases": ["data visualization", "dashboarding", "visual analytics"],
        "definition": "Creating clear visual representations of data for analysis and communication.",
        "evidence_rules": "Evidence includes charts, dashboards, or visualization code.",
        "level_rubric": {"0": "No visualization evidence.", "1": "Basic charts.", "2": "Appropriate chart choice, clarity.", "3": "Interactive or publication-ready visuals."},
    },
    "HKU.SKILL.ML.v1": {
        "canonical_name": "Machine Learning",
        "keywords": ["machine learning", "deep learning", "neural network", "tensorflow", "pytorch", "scikit-learn", "sklearn", "xgboost", "random forest", "classification", "clustering"],
        "aliases": ["machine learning", "ML", "deep learning"],
        "definition": "Building and evaluating ML models for prediction, classification, or clustering.",
        "evidence_rules": "Evidence includes model training, evaluation, or ML pipelines.",
        "level_rubric": {"0": "No ML evidence.", "1": "Simple models with guidance.", "2": "Train/evaluate, basic tuning.", "3": "Pipeline design, deployment, validation."},
    },
    "HKU.SKILL.PROJECT_MGMT.v1": {
        "canonical_name": "Project Management",
        "keywords": ["project management", "agile", "scrum", "waterfall", "jira", "stakeholder management", "project planning", "pmp", "prince2"],
        "aliases": ["project management", "PM", "Agile"],
        "definition": "Planning, executing, and closing projects with scope, time, and stakeholder management.",
        "evidence_rules": "Evidence shows planning, tracking, or delivery of projects.",
        "level_rubric": {"0": "No PM evidence.", "1": "Contributed to planned tasks.", "2": "Led or coordinated deliverables.", "3": "Full lifecycle, risk handling, multi-team."},
    },
    "HKU.SKILL.DATA_ANALYSIS.v1": {
        "canonical_name": "Data Analysis",
        "keywords": ["data analysis", "data analytics", "data-driven", "data cleaning", "data wrangling", "etl", "data pipeline"],
        "aliases": ["data analysis", "data analytics", "analytics"],
        "definition": "End-to-end data analysis: cleaning, exploration, and insight generation.",
        "evidence_rules": "Evidence shows data handling, analysis, and conclusions.",
        "level_rubric": {"0": "No analysis evidence.", "1": "Basic cleaning and summary.", "2": "Structured analysis, clear findings.", "3": "Rigorous methodology, reproducibility."},
    },
    "HKU.SKILL.NLP.v1": {
        "canonical_name": "Natural Language Processing",
        "keywords": ["nlp", "natural language", "text mining", "text analysis", "sentiment analysis", "tokenization", "named entity", "language model", "llm", "chatgpt", "gpt"],
        "aliases": ["NLP", "text mining", "natural language processing"],
        "definition": "Processing and analyzing text data using NLP techniques.",
        "evidence_rules": "Evidence includes text processing, NLP models, or text pipelines.",
        "level_rubric": {"0": "No NLP evidence.", "1": "Basic text handling.", "2": "Models or pipelines applied.", "3": "Custom models, evaluation, deployment."},
    },
    "HKU.SKILL.IR.v1": {
        "canonical_name": "Information Retrieval & Management",
        "keywords": ["information retrieval", "information management", "knowledge management", "content management", "metadata", "taxonomy", "information architecture", "search engine"],
        "aliases": ["information retrieval", "knowledge management", "information architecture"],
        "definition": "Design and evaluation of systems for organizing, storing, and retrieving information.",
        "evidence_rules": "Evidence shows search systems, indexing, metadata, or retrieval evaluation.",
        "level_rubric": {"0": "No IR evidence.", "1": "Basic search or indexing.", "2": "Evaluation, ranking, or taxonomy.", "3": "System design, optimization."},
    },
    "HKU.SKILL.COMMUNICATION.v1": {
        "canonical_name": "Communication & Presentation",
        "keywords": ["communication", "presentation", "writing", "report writing", "public speaking", "stakeholder communication", "interpersonal"],
        "aliases": ["communication", "presentation skills", "report writing"],
        "definition": "Effective written and verbal communication for professional and academic contexts.",
        "evidence_rules": "Evidence shows clear structure, audience awareness, and professional tone.",
        "level_rubric": {"0": "No communication evidence.", "1": "Basic written communication.", "2": "Clear, audience-aware communication.", "3": "Multi-format, persuasive, leadership-level."},
    },
    "HKU.SKILL.EXCEL.v1": {
        "canonical_name": "Excel & Spreadsheets",
        "keywords": ["excel", "spreadsheet", "pivot table", "vlookup", "google sheets"],
        "aliases": ["Excel", "spreadsheets", "Google Sheets"],
        "definition": "Using spreadsheet tools for data organization, analysis, and reporting.",
        "evidence_rules": "Evidence includes spreadsheet formulas, pivot tables, or reports.",
        "level_rubric": {"0": "No spreadsheet evidence.", "1": "Basic formulas.", "2": "Pivot tables, charts, functions.", "3": "Advanced modeling, macros, automation."},
    },
    "HKU.SKILL.CLOUD.v1": {
        "canonical_name": "Cloud Computing & DevOps",
        "keywords": ["aws", "azure", "gcp", "cloud", "docker", "kubernetes", "devops", "ci/cd", "terraform"],
        "aliases": ["AWS", "Azure", "cloud computing", "DevOps"],
        "definition": "Deploying and managing applications and data infrastructure on cloud platforms.",
        "evidence_rules": "Evidence shows cloud service usage, deployment, or infrastructure.",
        "level_rubric": {"0": "No cloud evidence.", "1": "Basic service usage.", "2": "Multi-service architecture.", "3": "Production deployment, optimization."},
    },
    "HKU.SKILL.GIS.v1": {
        "canonical_name": "GIS & Spatial Analysis",
        "keywords": ["gis", "geographic information", "spatial analysis", "arcgis", "qgis", "geospatial", "mapping"],
        "aliases": ["GIS", "geospatial analysis", "spatial data"],
        "definition": "Using geographic information systems for spatial data analysis and mapping.",
        "evidence_rules": "Evidence includes GIS projects, spatial analysis, or map outputs.",
        "level_rubric": {"0": "No GIS evidence.", "1": "Basic mapping.", "2": "Spatial analysis, data integration.", "3": "Advanced modeling, custom tools."},
    },
    "HKU.SKILL.WEB_DEV.v1": {
        "canonical_name": "Web Development",
        "keywords": ["web development", "html", "css", "javascript", "react", "angular", "vue", "frontend", "backend", "full stack", "api development", "rest api"],
        "aliases": ["web development", "frontend", "full-stack"],
        "definition": "Building and maintaining web applications and APIs.",
        "evidence_rules": "Evidence includes web applications, code, or deployed sites.",
        "level_rubric": {"0": "No web dev evidence.", "1": "Basic pages.", "2": "Full app with backend.", "3": "Production-grade, tested, deployed."},
    },
    "HKU.SKILL.CRITICAL_THINKING.v1": {
        "canonical_name": "Critical Thinking & Problem Solving",
        "keywords": ["critical thinking", "problem solving", "analytical thinking", "decision making", "logical reasoning"],
        "aliases": ["critical thinking", "problem solving", "analytical skills"],
        "definition": "Analyzing complex problems, evaluating evidence, and making reasoned decisions.",
        "evidence_rules": "Evidence shows structured reasoning, alternatives analysis, or evidence-based conclusions.",
        "level_rubric": {"0": "No evidence.", "1": "Basic problem identification.", "2": "Structured analysis with alternatives.", "3": "Complex multi-factor evaluation."},
    },
    "HKU.SKILL.TEAMWORK.v1": {
        "canonical_name": "Teamwork & Collaboration",
        "keywords": ["teamwork", "collaboration", "cross-functional", "team player", "collaborative"],
        "aliases": ["teamwork", "collaboration"],
        "definition": "Working effectively in teams, contributing to shared goals.",
        "evidence_rules": "Evidence shows team contributions, coordination, or peer feedback.",
        "level_rubric": {"0": "No teamwork evidence.", "1": "Participated in team tasks.", "2": "Active contributor, coordination.", "3": "Led teams, resolved conflicts."},
    },
    "HKU.SKILL.RESEARCH.v1": {
        "canonical_name": "Research Methods",
        "keywords": ["research method", "research design", "qualitative research", "quantitative research", "survey", "literature review", "academic research"],
        "aliases": ["research methods", "research design"],
        "definition": "Designing and conducting research using qualitative and/or quantitative methods.",
        "evidence_rules": "Evidence shows research design, data collection, or analysis methodology.",
        "level_rubric": {"0": "No research evidence.", "1": "Assisted with data collection.", "2": "Independent research design.", "3": "Published or presented research."},
    },
}


def _rand_delay(lo: float = MIN_DELAY, hi: float = MAX_DELAY) -> None:
    time.sleep(random.uniform(lo, hi))


def _get_session():
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(BROWSER_UAS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    })
    return s


def fetch_job_detail(session, url: str) -> str:
    """Fetch LinkedIn public job detail page and extract description text."""
    if not url:
        return ""
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 429:
            wait = random.uniform(30, 60)
            print(f"  429 rate limited, waiting {wait:.0f}s ...", file=sys.stderr)
            time.sleep(wait)
            session.headers["User-Agent"] = random.choice(BROWSER_UAS)
            r = session.get(url, timeout=20)
        if r.status_code != 200:
            return ""
        html = r.text
        # Description is typically in show-more-less-html__markup or description__text
        m = re.search(
            r'class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>',
            html, re.I | re.S,
        )
        if not m:
            m = re.search(
                r'class="[^"]*description__text[^"]*"[^>]*>(.*?)</section>',
                html, re.I | re.S,
            )
        if m:
            raw = m.group(1)
            text = re.sub(r"<br\s*/?>", "\n", raw)
            text = re.sub(r"<li[^>]*>", "\n• ", text)
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"&amp;", "&", text)
            text = re.sub(r"&lt;", "<", text)
            text = re.sub(r"&gt;", ">", text)
            text = re.sub(r"&#39;", "'", text)
            text = re.sub(r"&quot;", '"', text)
            text = re.sub(r"&nbsp;", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()[:4000]
    except Exception as e:
        print(f"  detail fetch failed {url}: {e}", file=sys.stderr)
    return ""


def extract_skills(text: str) -> list[dict]:
    """Extract skill_ids from text using the comprehensive SKILL_BANK with regex keywords."""
    if not text:
        return []
    lower = text.lower()
    matched: list[dict] = []
    seen: set[str] = set()
    for skill_id, info in SKILL_BANK.items():
        if skill_id in seen:
            continue
        for kw in info["keywords"]:
            if kw.startswith("\\b"):
                if re.search(kw, lower):
                    seen.add(skill_id)
                    matched.append({"skill_id": skill_id, "target_level": "2", "required": True, "weight": 1.0})
                    break
            elif kw in lower:
                seen.add(skill_id)
                matched.append({"skill_id": skill_id, "target_level": "2", "required": True, "weight": 1.0})
                break
    return matched


def main() -> None:
    if os.getenv("LINKEDIN_CRAWL_ALLOWED") != "1":
        print("Set LINKEDIN_CRAWL_ALLOWED=1", file=sys.stderr)
        sys.exit(1)

    # Load Phase 1 CSVs to get LinkedIn URLs
    sds_csv = REPO_ROOT / "roles_import_basc_sds_linkedin.csv"
    im_csv = REPO_ROOT / "roles_import_bsc_im_linkedin.csv"
    sds_json = REPO_ROOT / "roles_import_basc_sds_linkedin.json"
    im_json = REPO_ROOT / "roles_import_bsc_im_linkedin.json"

    jobs_by_prog: dict[str, list[dict]] = {"basc_sds": [], "bsc_im": []}
    for csv_path, prog in [(sds_csv, "basc_sds"), (im_csv, "bsc_im")]:
        if not csv_path.exists():
            print(f"Missing {csv_path}, run fetch_linkedin_jobs.py first", file=sys.stderr)
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                jobs_by_prog[prog].append(row)

    total = sum(len(v) for v in jobs_by_prog.values())
    print(f"Loaded {total} jobs from CSVs. Fetching detail pages...", file=sys.stderr)

    session = _get_session()
    enriched: dict[str, list[dict]] = {"basc_sds": [], "bsc_im": []}
    counter = 0

    for prog, jobs in jobs_by_prog.items():
        for job in jobs:
            counter += 1
            url = job.get("linkedin_url", "")
            title = job.get("job_title", "")
            print(f"[{counter}/{total}] {title[:50]}...", file=sys.stderr)

            description = fetch_job_detail(session, url)
            combined = f"{title} {job.get('employer', '')} {description}"
            skills = extract_skills(combined)
            if not skills:
                skills = [{"skill_id": "HKU.SKILL.DATA_ANALYSIS.v1", "target_level": "2", "required": True, "weight": 1.0}]

            role_id = job.get("role_id", f"HKU.ROLE.LINKEDIN.{prog.upper()}.{counter:04d}.v1")
            desc_parts = []
            if job.get("employer"):
                desc_parts.append(f"Employer: {job['employer']}")
            if job.get("location"):
                desc_parts.append(f"Location: {job['location']}")
            if description:
                desc_parts.append(description)

            enriched[prog].append({
                "role_id": role_id,
                "role_title": title,
                "description": "\n".join(desc_parts)[:3000] or None,
                "version": "v1",
                "skills_required": skills,
                "_meta": {
                    "linkedin_url": url,
                    "employer": job.get("employer", ""),
                    "location": job.get("location", ""),
                    "date_posted": job.get("date_posted", ""),
                    "skill_ids_found": [s["skill_id"] for s in skills],
                },
            })
            session.headers["User-Agent"] = random.choice(BROWSER_UAS)
            _rand_delay()

    # ---- Write enriched JSON ----
    for prog, roles in enriched.items():
        export = []
        for r in roles:
            clean = {k: v for k, v in r.items() if k != "_meta"}
            export.append(clean)
        out = REPO_ROOT / f"roles_enriched_{prog}_linkedin.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(export, f, ensure_ascii=False, indent=2)
        print(f"Enriched JSON -> {out} ({len(export)} roles)")

    # ---- Write enriched CSV ----
    for prog, roles in enriched.items():
        out = REPO_ROOT / f"roles_enriched_{prog}_linkedin.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["role_id", "job_title", "employer", "location", "date_posted",
                         "linkedin_url", "matched_skill_ids", "skill_count", "description_length"])
            for r in roles:
                m = r.get("_meta", {})
                w.writerow([
                    r["role_id"], r["role_title"], m.get("employer", ""), m.get("location", ""),
                    m.get("date_posted", ""), m.get("linkedin_url", ""),
                    "; ".join(m.get("skill_ids_found", [])),
                    len(r.get("skills_required", [])),
                    len(r.get("description") or ""),
                ])
        print(f"Enriched CSV  -> {out}")

    # ---- Generate comprehensive skills seed ----
    skills_seed = []
    for skill_id, info in SKILL_BANK.items():
        skills_seed.append({
            "skill_id": skill_id,
            "canonical_name": info["canonical_name"],
            "aliases": info.get("aliases", []),
            "definition": info["definition"],
            "evidence_rules": info["evidence_rules"],
            "level_rubric": info["level_rubric"],
            "version": "v1",
            "source": "HKU",
        })
    skills_path = REPO_ROOT / "backend" / "data" / "seeds" / "skills_comprehensive.json"
    with open(skills_path, "w", encoding="utf-8") as f:
        json.dump(skills_seed, f, ensure_ascii=False, indent=2)
    print(f"Skills seed   -> {skills_path} ({len(skills_seed)} skills)")

    # ---- Generate courses seed from the two PDFs ----
    courses = _build_courses_seed()
    courses_path = REPO_ROOT / "backend" / "data" / "seeds" / "courses_hku.json"
    with open(courses_path, "w", encoding="utf-8") as f:
        json.dump(courses, f, ensure_ascii=False, indent=2)
    print(f"Courses seed  -> {courses_path} ({len(courses)} courses)")

    # ---- Generate course-skill mapping ----
    csmap = _build_course_skill_map()
    csmap_path = REPO_ROOT / "backend" / "data" / "seeds" / "course_skill_map.json"
    with open(csmap_path, "w", encoding="utf-8") as f:
        json.dump(csmap, f, ensure_ascii=False, indent=2)
    print(f"Course-skill  -> {csmap_path} ({len(csmap)} mappings)")

    # ---- Skill frequency summary ----
    freq: dict[str, int] = {}
    for prog_roles in enriched.values():
        for r in prog_roles:
            for s in r.get("skills_required", []):
                sid = s["skill_id"]
                freq[sid] = freq.get(sid, 0) + 1
    print("\n=== Skill Frequency Across All Roles ===", file=sys.stderr)
    for sid, count in sorted(freq.items(), key=lambda x: -x[1]):
        name = SKILL_BANK.get(sid, {}).get("canonical_name", sid)
        print(f"  {name:40s} {count:3d} roles", file=sys.stderr)

    print(f"\nDone. Total enriched: {sum(len(v) for v in enriched.values())} roles")


# ---- Course data from the two programme PDFs ----
def _build_courses_seed() -> list[dict]:
    """Build course entries from the BASc(SDS) and BSc(IM) programmes."""
    courses = [
        # BASc(SDS) - Introductory
        {"course_id": "BSDS3001", "course_name": "Social data science foundations", "credits": 6, "programme": "BASc(SDS)", "category": "Introductory", "assessment": "100% coursework"},
        {"course_id": "BSDS3002", "course_name": "Social computing: methods and applications", "credits": 6, "programme": "BASc(SDS)", "category": "Introductory", "assessment": "100% coursework"},
        {"course_id": "BSDS3003", "course_name": "Data processing and visualization", "credits": 6, "programme": "BASc(SDS)", "category": "Introductory", "assessment": "100% coursework"},
        {"course_id": "BSDS3004", "course_name": "Introduction to statistics", "credits": 6, "programme": "BASc(SDS)", "category": "Introductory", "assessment": "100% coursework"},
        # BASc(SDS) - Advanced Compulsory
        {"course_id": "BSDS3005", "course_name": "Advanced statistical modeling for social applications", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Compulsory", "assessment": "100% coursework"},
        {"course_id": "BSIM4018", "course_name": "Data warehousing and data mining", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Compulsory/Elective", "assessment": "100% coursework"},
        {"course_id": "SDST2604", "course_name": "Introduction to R/Python programming and elementary data analysis", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Compulsory", "assessment": "100% coursework"},
        # BASc(SDS) - Advanced Elective (Education)
        {"course_id": "BSIM3017", "course_name": "Database systems", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Elective/Core", "assessment": "70% coursework, 30% examination"},
        {"course_id": "BSIM3021", "course_name": "Web development, users and management", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "BSIM3025", "course_name": "Multimedia and human-computer interaction", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "BSIM4011", "course_name": "Project management", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Elective/Core", "assessment": "100% coursework"},
        {"course_id": "BSIM4019", "course_name": "Electronic commerce", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "BSIM4020", "course_name": "Information society issues and policy", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Elective/Core", "assessment": "100% coursework"},
        {"course_id": "BSIM4024", "course_name": "Fundamentals of object-oriented programming", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "BSIM4027", "course_name": "Selected topics in information management", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "BSIM4028", "course_name": "Principles and practice of data visualization", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "MLIM6319", "course_name": "Information behavior", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "MLIM7350", "course_name": "Data curation", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        # BASc(SDS) - Advanced Elective (Social Sciences)
        {"course_id": "GEOG1020", "course_name": "Modern maps in the age of big data", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "60% coursework, 40% examination"},
        {"course_id": "GEOG2090", "course_name": "Introduction to geographic information systems", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "60% coursework, 40% examination"},
        {"course_id": "POLI3039", "course_name": "Public policy analysis", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "POLI3131", "course_name": "In search of good policy: an introduction to policy evaluation", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "PSYC2071", "course_name": "Judgements and decision making", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "SOWK2131", "course_name": "Behavioural economics for social change", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        # BASc(SDS) - Advanced Elective (Science)
        {"course_id": "SDST3612", "course_name": "Statistical machine learning", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "SDST3613", "course_name": "Marketing analytics", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "50% coursework, 50% examination"},
        {"course_id": "SDST3622", "course_name": "Data visualization", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "SDST4011", "course_name": "Natural language processing", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        {"course_id": "SDST4609", "course_name": "Big data analytics", "credits": 6, "programme": "BASc(SDS)", "category": "Advanced Elective", "assessment": "100% coursework"},
        # BASc(SDS) - Capstone
        {"course_id": "BSDS3999", "course_name": "Internship", "credits": 6, "programme": "BASc(SDS)", "category": "Capstone", "assessment": "100% coursework"},
        {"course_id": "BSDS4999", "course_name": "Project", "credits": 6, "programme": "BASc(SDS)", "category": "Capstone", "assessment": "100% coursework"},
        # BSc(IM) - Core
        {"course_id": "BSIM3001", "course_name": "Information management foundations", "credits": 6, "programme": "BSc(IM)", "category": "Core", "assessment": "100% coursework"},
        {"course_id": "BSIM3004", "course_name": "Information retrieval", "credits": 6, "programme": "BSc(IM)", "category": "Core", "assessment": "100% coursework"},
        {"course_id": "BSIM3023", "course_name": "Information organisation and content management", "credits": 6, "programme": "BSc(IM)", "category": "Core", "assessment": "100% coursework"},
        {"course_id": "BSIM3998", "course_name": "Professional practices in information management", "credits": 6, "programme": "BSc(IM)", "category": "Core", "assessment": "100% coursework"},
        {"course_id": "BSIM3999", "course_name": "Internship", "credits": 6, "programme": "BSc(IM)", "category": "Core", "assessment": "100% coursework"},
        {"course_id": "BSIM4026", "course_name": "Introduction to statistics and quantitative data analysis", "credits": 6, "programme": "BSc(IM)", "category": "Core", "assessment": "100% coursework"},
        {"course_id": "BSIM4999", "course_name": "Project", "credits": 6, "programme": "BSc(IM)", "category": "Capstone", "assessment": "100% coursework"},
        # BSc(IM) - Elective (only unique ones not already listed)
        {"course_id": "BSIM3014", "course_name": "User-based systems analysis", "credits": 6, "programme": "BSc(IM)", "category": "Elective", "assessment": "100% coursework"},
        # English in the Discipline (shared)
        {"course_id": "CAES9420", "course_name": "Academic English for information management and social data science students", "credits": 6, "programme": "BASc(SDS)/BSc(IM)", "category": "English", "assessment": "100% coursework"},
    ]
    return courses


def _build_course_skill_map() -> list[dict]:
    """Map courses to skills they develop."""
    return [
        # Python / R / Programming
        {"course_id": "SDST2604", "skill_id": "HKU.SKILL.PYTHON.v1", "relevance": "primary"},
        {"course_id": "SDST2604", "skill_id": "HKU.SKILL.R.v1", "relevance": "primary"},
        {"course_id": "BSIM4024", "skill_id": "HKU.SKILL.PYTHON.v1", "relevance": "secondary"},
        # Statistics
        {"course_id": "BSDS3004", "skill_id": "HKU.SKILL.STATISTICS.v1", "relevance": "primary"},
        {"course_id": "BSDS3005", "skill_id": "HKU.SKILL.STATISTICS.v1", "relevance": "primary"},
        {"course_id": "BSDS3005", "skill_id": "HKU.SKILL.ML.v1", "relevance": "secondary"},
        {"course_id": "BSIM4026", "skill_id": "HKU.SKILL.STATISTICS.v1", "relevance": "primary"},
        # Data Analysis
        {"course_id": "BSDS3003", "skill_id": "HKU.SKILL.DATA_ANALYSIS.v1", "relevance": "primary"},
        {"course_id": "BSDS3003", "skill_id": "HKU.SKILL.DATA_VIS.v1", "relevance": "primary"},
        {"course_id": "BSDS3001", "skill_id": "HKU.SKILL.DATA_ANALYSIS.v1", "relevance": "secondary"},
        {"course_id": "BSDS3001", "skill_id": "HKU.SKILL.RESEARCH.v1", "relevance": "secondary"},
        # Data Visualization
        {"course_id": "BSIM4028", "skill_id": "HKU.SKILL.DATA_VIS.v1", "relevance": "primary"},
        {"course_id": "SDST3622", "skill_id": "HKU.SKILL.DATA_VIS.v1", "relevance": "primary"},
        {"course_id": "SDST3622", "skill_id": "HKU.SKILL.R.v1", "relevance": "secondary"},
        # SQL & Databases
        {"course_id": "BSIM3017", "skill_id": "HKU.SKILL.SQL.v1", "relevance": "primary"},
        {"course_id": "BSIM4018", "skill_id": "HKU.SKILL.SQL.v1", "relevance": "secondary"},
        {"course_id": "BSIM4018", "skill_id": "HKU.SKILL.DATA_ANALYSIS.v1", "relevance": "primary"},
        {"course_id": "BSIM4018", "skill_id": "HKU.SKILL.ML.v1", "relevance": "secondary"},
        # Machine Learning / NLP
        {"course_id": "SDST3612", "skill_id": "HKU.SKILL.ML.v1", "relevance": "primary"},
        {"course_id": "SDST3612", "skill_id": "HKU.SKILL.STATISTICS.v1", "relevance": "secondary"},
        {"course_id": "SDST4011", "skill_id": "HKU.SKILL.NLP.v1", "relevance": "primary"},
        {"course_id": "SDST4011", "skill_id": "HKU.SKILL.ML.v1", "relevance": "secondary"},
        {"course_id": "SDST4609", "skill_id": "HKU.SKILL.DATA_ANALYSIS.v1", "relevance": "primary"},
        {"course_id": "SDST4609", "skill_id": "HKU.SKILL.ML.v1", "relevance": "secondary"},
        # GIS
        {"course_id": "GEOG2090", "skill_id": "HKU.SKILL.GIS.v1", "relevance": "primary"},
        {"course_id": "GEOG1020", "skill_id": "HKU.SKILL.GIS.v1", "relevance": "secondary"},
        {"course_id": "GEOG1020", "skill_id": "HKU.SKILL.DATA_VIS.v1", "relevance": "secondary"},
        # Project Management
        {"course_id": "BSIM4011", "skill_id": "HKU.SKILL.PROJECT_MGMT.v1", "relevance": "primary"},
        {"course_id": "BSIM4011", "skill_id": "HKU.SKILL.COMMUNICATION.v1", "relevance": "secondary"},
        # Information Retrieval / Management
        {"course_id": "BSIM3004", "skill_id": "HKU.SKILL.IR.v1", "relevance": "primary"},
        {"course_id": "BSIM3001_IM", "skill_id": "HKU.SKILL.IR.v1", "relevance": "primary"},
        {"course_id": "BSIM3023", "skill_id": "HKU.SKILL.IR.v1", "relevance": "primary"},
        {"course_id": "MLIM7350", "skill_id": "HKU.SKILL.IR.v1", "relevance": "secondary"},
        {"course_id": "MLIM7350", "skill_id": "HKU.SKILL.DATA_ANALYSIS.v1", "relevance": "secondary"},
        # Web Development
        {"course_id": "BSIM3021", "skill_id": "HKU.SKILL.WEB_DEV.v1", "relevance": "primary"},
        # Social Computing
        {"course_id": "BSDS3002", "skill_id": "HKU.SKILL.DATA_ANALYSIS.v1", "relevance": "primary"},
        {"course_id": "BSDS3002", "skill_id": "HKU.SKILL.NLP.v1", "relevance": "secondary"},
        # Communication / Research
        {"course_id": "CAES9420", "skill_id": "HKU.SKILL.COMMUNICATION.v1", "relevance": "primary"},
        {"course_id": "CAES9420", "skill_id": "HKU.SKILL.RESEARCH.v1", "relevance": "secondary"},
        {"course_id": "BSDS4999", "skill_id": "HKU.SKILL.RESEARCH.v1", "relevance": "primary"},
        {"course_id": "BSIM4999", "skill_id": "HKU.SKILL.RESEARCH.v1", "relevance": "primary"},
        {"course_id": "BSDS3999", "skill_id": "HKU.SKILL.TEAMWORK.v1", "relevance": "secondary"},
        {"course_id": "BSIM3999", "skill_id": "HKU.SKILL.TEAMWORK.v1", "relevance": "secondary"},
        # Marketing Analytics
        {"course_id": "SDST3613", "skill_id": "HKU.SKILL.DATA_ANALYSIS.v1", "relevance": "primary"},
        {"course_id": "SDST3613", "skill_id": "HKU.SKILL.STATISTICS.v1", "relevance": "secondary"},
        # Policy
        {"course_id": "POLI3039", "skill_id": "HKU.SKILL.CRITICAL_THINKING.v1", "relevance": "primary"},
        {"course_id": "POLI3039", "skill_id": "HKU.SKILL.DATA_ANALYSIS.v1", "relevance": "secondary"},
        {"course_id": "POLI3131", "skill_id": "HKU.SKILL.STATISTICS.v1", "relevance": "primary"},
        {"course_id": "POLI3131", "skill_id": "HKU.SKILL.CRITICAL_THINKING.v1", "relevance": "secondary"},
        # User Systems / HCI
        {"course_id": "BSIM3014", "skill_id": "HKU.SKILL.CRITICAL_THINKING.v1", "relevance": "secondary"},
        {"course_id": "BSIM3025", "skill_id": "HKU.SKILL.WEB_DEV.v1", "relevance": "secondary"},
        {"course_id": "BSIM3025", "skill_id": "HKU.SKILL.CRITICAL_THINKING.v1", "relevance": "secondary"},
    ]


if __name__ == "__main__":
    main()
