#!/usr/bin/env python3
"""
LinkedIn 单一来源职位拉取 — 仅在被允许且仅公开、仅两项目相关时使用。
数据来源仅 LinkedIn，不混合其他渠道。详见 docs/linkedin_crawl_policy.md。

Usage:
  export LINKEDIN_CRAWL_ALLOWED=1
  python3 scripts/fetch_linkedin_jobs.py --programme basc_sds
  python3 scripts/fetch_linkedin_jobs.py --programme bsc_im

Output: roles_import_basc_sds_linkedin.json + .csv, roles_import_bsc_im_linkedin.json + .csv
"""
from __future__ import annotations

import argparse
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

LINKEDIN_JOBS_GUEST_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

BROWSER_UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

MIN_DELAY = 3.0
MAX_DELAY = 6.0
QUERY_GAP_MIN = 5.0
QUERY_GAP_MAX = 10.0

PROGRAMME_QUERIES = {
    "basc_sds": [
        "Social Data Scientist",
        "Data Analyst",
        "Policy Analyst",
        "Research Analyst",
        "Data Science Intern",
        "Statistical Analyst",
        "GIS Analyst",
        "Marketing Analyst",
    ],
    "bsc_im": [
        "Information Management",
        "Information Analyst",
        "Database Administrator",
        "Business Analyst",
        "IT Project Manager",
        "Knowledge Management",
        "Information Systems Analyst",
        "Data Analyst",
    ],
}

KEYWORD_TO_SKILL_ID = {
    "python": "HKU.SSKILL.000001.v1",
    "r programming": "HKU.SKILL.R.v1",
    "sql": "HKU.SKILL.SQL.v1",
    "database": "HKU.SKILL.SQL.v1",
    "statistics": "HKU.SKILL.STATISTICS.v1",
    "statistical": "HKU.SKILL.STATISTICS.v1",
    "data visualization": "HKU.SKILL.DATA_VIS.v1",
    "tableau": "HKU.SKILL.DATA_VIS.v1",
    "power bi": "HKU.SKILL.DATA_VIS.v1",
    "machine learning": "HKU.SKILL.ML.v1",
    "deep learning": "HKU.SKILL.ML.v1",
    "project management": "HKU.SKILL.PROJECT_MGMT.v1",
    "data analysis": "HKU.SKILL.DATA_ANALYSIS.v1",
    "data analytics": "HKU.SKILL.DATA_ANALYSIS.v1",
    "nlp": "HKU.SKILL.NLP.v1",
    "natural language": "HKU.SKILL.NLP.v1",
    "information retrieval": "HKU.SKILL.IR.v1",
}
DEFAULT_SKILL_LEVEL = "2"


def _check_allowed() -> bool:
    if os.getenv("LINKEDIN_CRAWL_ALLOWED") != "1":
        print(
            "LinkedIn 爬取须在获得允许后使用。请先阅读 docs/linkedin_crawl_policy.md，"
            "设置 LINKEDIN_CRAWL_ALLOWED=1 后再运行。",
            file=sys.stderr,
        )
        return False
    return True


def _rand_delay(lo: float = MIN_DELAY, hi: float = MAX_DELAY) -> None:
    d = random.uniform(lo, hi)
    time.sleep(d)


def _get_session():
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(BROWSER_UAS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })
    return s


def _extract_skill_ids(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    lower = text.lower()
    for keyword, skill_id in KEYWORD_TO_SKILL_ID.items():
        if skill_id in seen:
            continue
        if keyword in lower:
            seen.add(skill_id)
            out.append(skill_id)
    return out


def _extract_location(blob: str) -> str:
    m = re.search(r'class="[^"]*job-search-card__location[^"]*"[^>]*>([^<]+)<', blob, re.I | re.S)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    return ""


def _extract_date(blob: str) -> str:
    m = re.search(r'<time[^>]*datetime="([^"]+)"', blob, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<time[^>]*>([^<]+)<', blob, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    return ""


def _parse_guest_html(html: str) -> list[dict]:
    jobs = []
    card_blobs = re.split(r"<li\s", html, flags=re.I)
    for blob in card_blobs:
        if "base-card" not in blob and "job-search-card" not in blob:
            continue
        title = company = snippet = link = location = date_posted = ""

        m = re.search(r'class="[^"]*base-search-card__title[^"]*"[^>]*>([^<]+)<', blob, re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1).strip())
        m = re.search(r'class="[^"]*hidden-nested-link[^"]*"[^>]*>([^<]+)<', blob, re.I | re.S)
        if m:
            company = re.sub(r"\s+", " ", m.group(1).strip())
        if not company:
            m = re.search(r'class="[^"]*job-search-card__subtitle[^"]*"[^>]*>([^<]+)<', blob, re.I | re.S)
            if m:
                company = re.sub(r"\s+", " ", m.group(1).strip())
        m = re.search(r'class="[^"]*base-card__full-link[^"]*"[^>]*href="([^"]+)"', blob, re.I)
        if m:
            link = m.group(1).strip().split("?")[0]
        m = re.search(r'class="[^"]*job-search-card__snippet[^"]*"[^>]*>([^<]+)<', blob, re.I | re.S)
        if m:
            snippet = re.sub(r"\s+", " ", m.group(1).strip())[:500]
        location = _extract_location(blob)
        date_posted = _extract_date(blob)

        if title:
            jobs.append({
                "job_title": title,
                "employer_name": company,
                "location": location,
                "date_posted": date_posted,
                "snippet": snippet,
                "linkedin_url": link,
            })
    return jobs


def fetch_page(session, keywords: str, start: int) -> list[dict]:
    params = {"keywords": keywords, "start": str(start)}
    url = f"{LINKEDIN_JOBS_GUEST_SEARCH}?{urlencode(params)}"
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 429:
            wait = random.uniform(30, 60)
            print(f"  429 rate limited, waiting {wait:.0f}s ...", file=sys.stderr)
            time.sleep(wait)
            r = session.get(url, timeout=20)
        r.raise_for_status()
        return _parse_guest_html(r.text)
    except Exception as e:
        print(f"  request failed keywords={keywords!r} start={start}: {e}", file=sys.stderr)
        return []


def job_to_role(job: dict, programme: str, index: int) -> dict:
    title = (job.get("job_title") or "Unknown Role").strip()[:256]
    company = (job.get("employer_name") or "").strip()
    snippet = (job.get("snippet") or "").strip()[:1500]
    location = (job.get("location") or "").strip()
    desc_parts = []
    if company:
        desc_parts.append(f"Employer: {company}")
    if location:
        desc_parts.append(f"Location: {location}")
    if snippet:
        desc_parts.append(snippet)
    desc = "\n".join(desc_parts) or None

    combined = f"{title} {company} {snippet}"
    skill_ids = _extract_skill_ids(combined)
    if not skill_ids:
        skill_ids = ["HKU.SKILL.DATA_ANALYSIS.v1"]
    skills_required = [
        {"skill_id": sid, "target_level": DEFAULT_SKILL_LEVEL, "required": True, "weight": 1.0}
        for sid in skill_ids[:8]
    ]
    role_id = f"HKU.ROLE.LINKEDIN.{programme.upper()}.{index:04d}.v1"
    return {
        "role_id": role_id,
        "role_title": title,
        "description": desc,
        "version": "v1",
        "skills_required": skills_required,
        "_source": job,
    }


def write_csv(jobs: list[dict], roles: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "role_id", "job_title", "employer", "location", "date_posted",
            "snippet", "linkedin_url", "matched_skill_ids", "search_query",
        ])
        for role in roles:
            src = role.get("_source", {})
            w.writerow([
                role["role_id"],
                src.get("job_title", ""),
                src.get("employer_name", ""),
                src.get("location", ""),
                src.get("date_posted", ""),
                src.get("snippet", ""),
                src.get("linkedin_url", ""),
                "; ".join(s["skill_id"] for s in role["skills_required"]),
                src.get("_query", ""),
            ])


def main() -> None:
    ap = argparse.ArgumentParser(description="LinkedIn 单一来源职位拉取（仅公开、仅两项目）")
    ap.add_argument("--programme", choices=["basc_sds", "bsc_im"], required=True)
    ap.add_argument("--pages-per-query", type=int, default=3, help="每个关键词请求页数（每页~25条），默认 3")
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT)
    args = ap.parse_args()

    if not _check_allowed():
        sys.exit(1)

    prog = args.programme
    queries = PROGRAMME_QUERIES.get(prog, [])
    session = _get_session()

    all_jobs: list[dict] = []
    seen_titles: set[str] = set()
    total_requests = 0

    for qi, q in enumerate(queries):
        print(f"[{qi+1}/{len(queries)}] query={q!r}", file=sys.stderr)
        page_empty = 0
        for page in range(args.pages_per_query):
            start = page * 25
            jobs = fetch_page(session, q, start)
            new_count = 0
            for j in jobs:
                t = (j.get("job_title") or "").strip()
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    j["_query"] = q
                    all_jobs.append(j)
                    new_count += 1
            total_requests += 1
            print(f"  page {page+1}: {len(jobs)} cards, {new_count} new (total unique: {len(all_jobs)})", file=sys.stderr)
            if not jobs:
                page_empty += 1
                if page_empty >= 2:
                    break
            _rand_delay(MIN_DELAY, MAX_DELAY)

        if qi < len(queries) - 1:
            session.headers["User-Agent"] = random.choice(BROWSER_UAS)
            _rand_delay(QUERY_GAP_MIN, QUERY_GAP_MAX)

    roles = [job_to_role(j, prog, i) for i, j in enumerate(all_jobs)]

    json_path = args.out_dir / f"roles_import_{prog}_linkedin.json"
    export_roles = []
    for r in roles:
        clean = {k: v for k, v in r.items() if k != "_source"}
        export_roles.append(clean)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_roles, f, ensure_ascii=False, indent=2)

    csv_path = args.out_dir / f"roles_import_{prog}_linkedin.csv"
    write_csv(all_jobs, roles, csv_path)

    print(f"\nDone: {len(roles)} unique roles from {total_requests} requests", file=sys.stderr)
    print(f"  JSON -> {json_path}")
    print(f"  CSV  -> {csv_path}")


if __name__ == "__main__":
    main()
