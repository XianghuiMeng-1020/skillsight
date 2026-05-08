#!/usr/bin/env python3
"""
Fetch job market data for BASc(SDS) and BSc(IM) programmes.
Uses a job aggregator API (e.g. JSearch on RapidAPI) to get roles;
outputs JSON suitable for POST /roles/import.

Strategy: docs/job_market_intake_strategy.md

Usage:
  # With API key (RapidAPI JSearch): real job listings
  RAPIDAPI_KEY=your_key python3 scripts/fetch_job_market_data.py --programme basc_sds
  RAPIDAPI_KEY=your_key python3 scripts/fetch_job_market_data.py --programme bsc_im
  RAPIDAPI_KEY=your_key python3 scripts/fetch_job_market_data.py --all

  # Without API key: generates demo role titles + placeholder skills for the two programmes
  python3 scripts/fetch_job_market_data.py --programme basc_sds --demo
  python3 scripts/fetch_job_market_data.py --all --demo

Output: roles_import_basc_sds.json, roles_import_bsc_im.json (or roles_import_all.json)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

# -----------------------------------------------------------------------------
# Programme-specific search queries (for aggregator API)
# -----------------------------------------------------------------------------
PROGRAMME_QUERIES = {
    "basc_sds": [
        "Social Data Scientist",
        "Data Analyst statistics",
        "Policy Analyst data",
        "Research Analyst quantitative",
        "Data Science Intern",
        "Statistical Analyst",
        "GIS Analyst",
        "Marketing Analyst data",
    ],
    "bsc_im": [
        "Information Management",
        "Information Analyst",
        "Database Administrator",
        "Business Analyst IT",
        "IT Project Manager",
        "Knowledge Management",
        "Information Systems Analyst",
        "Data Analyst SQL",
    ],
}

# Role titles to emit in demo mode (no API)
DEMO_ROLES = {
    "basc_sds": [
        ("Social Data Scientist", "Analyze social and behavioral data; build models and visualizations for policy and research."),
        ("Data Analyst", "Data cleaning, analysis, and reporting; statistics and visualization."),
        ("Policy Analyst", "Quantitative policy evaluation and data-driven policy advice."),
        ("Research Analyst", "Research design, data collection, and statistical analysis."),
        ("Marketing Analyst", "Marketing data analysis, segmentation, and campaign analytics."),
    ],
    "bsc_im": [
        ("Information Analyst", "Information systems analysis, retrieval, and knowledge organization."),
        ("Database Analyst", "Database design, SQL, and data management."),
        ("IT Project Manager", "Project planning, delivery, and stakeholder communication."),
        ("Business Analyst", "Requirements analysis, process improvement, and data-driven decision support."),
        ("Knowledge Management Specialist", "Knowledge capture, organization, and information architecture."),
    ],
}

# Map job-description keywords to existing or planned skill_id (see docs/job_market_intake_strategy.md)
# Only HKU.SSKILL.000001.v1 exists in seeds; others are placeholders for future skills import.
KEYWORD_TO_SKILL_ID = {
    "python": "HKU.SSKILL.000001.v1",
    "r ": "HKU.SKILL.R.v1",
    "sql": "HKU.SKILL.SQL.v1",
    "database": "HKU.SKILL.SQL.v1",
    "statistics": "HKU.SKILL.STATISTICS.v1",
    "data visualization": "HKU.SKILL.DATA_VIS.v1",
    "machine learning": "HKU.SKILL.ML.v1",
    "project management": "HKU.SKILL.PROJECT_MGMT.v1",
    "data analysis": "HKU.SKILL.DATA_ANALYSIS.v1",
    "nlp": "HKU.SKILL.NLP.v1",
    "information retrieval": "HKU.SKILL.IR.v1",
}

DEFAULT_SKILL_LEVEL = "2"
REPO_ROOT = Path(__file__).resolve().parents[1]


def fetch_jsearch(query: str, api_key: str, num_pages: int = 1) -> list[dict]:
    """
    Fetch jobs from JSearch (RapidAPI).
    JSearch aggregates listings from LinkedIn, Indeed, Glassdoor, etc. — we do NOT crawl LinkedIn directly.
    Returns list of job objects (job_title, job_description, employer_name, ...).
    """
    try:
        import requests
    except ImportError:
        return []
    base_url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    all_jobs = []
    for page in range(num_pages):
        params = {"query": query, "page": str(page + 1), "num_pages": "1"}
        try:
            r = requests.get(base_url, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            # Response: { "status": "OK", "data": [ { job_title, job_description, employer_name, ... } ] }
            if data.get("status") != "OK":
                print(f"JSearch returned status={data.get('status')!r} for query={query!r}", file=sys.stderr)
                break
            jobs = data.get("data") or []
            all_jobs.extend(jobs)
            if not jobs:
                break
        except Exception as e:
            print(f"JSearch request failed for query={query!r}: {e}", file=sys.stderr)
            break
    return all_jobs


def extract_skill_ids_from_text(text: str) -> list[str]:
    """Heuristic: find keyword matches and return corresponding skill_ids (no duplicates, order preserved)."""
    if not text:
        return []
    seen = set()
    out = []
    lower = text.lower()
    for keyword, skill_id in KEYWORD_TO_SKILL_ID.items():
        if skill_id in seen:
            continue
        if keyword in lower:
            seen.add(skill_id)
            out.append(skill_id)
    return out


def job_to_role_payload(job: dict, programme: str, index: int) -> dict:
    """Convert one API job item to RoleIn-like dict (role_id, role_title, description, skills_required)."""
    title = (job.get("job_title") or job.get("title") or "Unknown Role").strip()
    desc = job.get("job_description") or (job.get("job_highlights") or {}).get("Qualifications", [])
    if isinstance(desc, list):
        desc = " ".join(str(x) for x in desc)
    desc = (desc or "").strip()[:2000]
    employer = job.get("employer_name") or ""
    if employer and desc:
        desc = f"[Employer: {employer}]\n\n{desc}"
    elif employer:
        desc = f"[Employer: {employer}]"
    combined = f"{title} {desc}"
    skill_ids = extract_skill_ids_from_text(combined)
    if not skill_ids:
        skill_ids = ["HKU.SKILL.DATA_ANALYSIS.v1"]
    skills_required = [
        {"skill_id": sid, "target_level": DEFAULT_SKILL_LEVEL, "required": True, "weight": 1.0}
        for sid in skill_ids[:8]
    ]
    role_id = f"HKU.ROLE.JOB.{programme.upper()}.{index:04d}.v1"
    return {
        "role_id": role_id,
        "role_title": title[:256],
        "description": desc or None,
        "version": "v1",
        "skills_required": skills_required,
    }


def build_demo_roles(programme: str) -> list[dict]:
    """Build demo role payloads from DEMO_ROLES (no API)."""
    out = []
    for i, (title, desc) in enumerate(DEMO_ROLES.get(programme, [])):
        combined = f"{title} {desc}"
        skill_ids = extract_skill_ids_from_text(combined)
        if not skill_ids:
            skill_ids = ["HKU.SKILL.DATA_ANALYSIS.v1"]
        skills_required = [
            {"skill_id": sid, "target_level": DEFAULT_SKILL_LEVEL, "required": True, "weight": 1.0}
            for sid in skill_ids[:6]
        ]
        role_id = f"HKU.ROLE.JOB.{programme.upper()}.{i:04d}.v1"
        out.append({
            "role_id": role_id,
            "role_title": title,
            "description": desc,
            "version": "v1",
            "skills_required": skills_required,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch job market data for BASc(SDS) and BSc(IM)")
    ap.add_argument("--programme", choices=["basc_sds", "bsc_im"], help="Single programme")
    ap.add_argument("--all", action="store_true", help="Fetch for both programmes")
    ap.add_argument("--demo", action="store_true", help="No API; output demo role list only")
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT, help="Directory to write JSON files")
    ap.add_argument("--pages", type=int, default=2, help="When using API: fetch this many pages per query (default 2)")
    args = ap.parse_args()

    programmes = []
    if args.all:
        programmes = ["basc_sds", "bsc_im"]
    elif args.programme:
        programmes = [args.programme]
    else:
        ap.print_help()
        sys.exit(1)

    api_key = os.getenv("RAPIDAPI_KEY", "").strip()
    if not args.demo and not api_key:
        print("Set RAPIDAPI_KEY for real data, or use --demo for demo output.", file=sys.stderr)
        print("Demo mode: generating placeholder roles only.", file=sys.stderr)
        args.demo = True

    all_payloads = []
    for prog in programmes:
        if args.demo:
            roles = build_demo_roles(prog)
        else:
            roles = []
            seen_titles = set()
            for q in PROGRAMME_QUERIES.get(prog, []):
                jobs = fetch_jsearch(q, api_key, num_pages=args.pages)
                for j in jobs:
                    title = (j.get("job_title") or j.get("title") or "").strip()
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    roles.append(job_to_role_payload(j, prog, len(roles)))
            if not roles:
                print(f"No jobs returned for {prog}; falling back to demo roles.", file=sys.stderr)
                roles = build_demo_roles(prog)
        all_payloads.extend(roles)
        out_file = args.out_dir / f"roles_import_{prog}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(roles, f, ensure_ascii=False, indent=2)
        print(f"Wrote {len(roles)} roles -> {out_file}")

    if args.all and all_payloads:
        out_all = args.out_dir / "roles_import_all.json"
        with open(out_all, "w", encoding="utf-8") as f:
            json.dump(all_payloads, f, ensure_ascii=False, indent=2)
        print(f"Wrote combined {len(all_payloads)} roles -> {out_all}")


if __name__ == "__main__":
    main()
