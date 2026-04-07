#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests

from scripts.scrapers import CtGoodJobsScraper, GovHkScraper, JobsDbScraper


REPO_ROOT = Path(__file__).resolve().parents[1]
FALLBACK_ROLE_FILES = [
    REPO_ROOT / "roles_import_bsc_im_linkedin.json",
    REPO_ROOT / "roles_import_basc_sds_linkedin.json",
    REPO_ROOT / "roles_enriched_bsc_im_linkedin.json",
    REPO_ROOT / "roles_enriched_basc_sds_linkedin.json",
]


def _run_all(pages: int) -> Dict[str, List[dict]]:
    jobsdb = [j.to_dict() for j in JobsDbScraper().scrape("data analyst", pages)]
    ct = [j.to_dict() for j in CtGoodJobsScraper().scrape("business analyst", pages)]
    gov = [j.to_dict() for j in GovHkScraper().scrape(pages)]
    return {"jobsdb": jobsdb, "ctgoodjobs": ct, "gov_hk": gov}


def _fallback_from_role_files() -> List[dict]:
    items: List[dict] = []
    for path in FALLBACK_ROLE_FILES:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for idx, row in enumerate(data):
            if not isinstance(row, dict):
                continue
            role_id = str(row.get("role_id") or f"{path.stem}-{idx}")
            title = str(row.get("role_title") or "").strip()
            desc = str(row.get("description") or "").strip()
            if not title:
                continue
            location = ""
            company = ""
            for line in desc.splitlines():
                low = line.lower()
                if low.startswith("location:"):
                    location = line.split(":", 1)[1].strip()
                elif low.startswith("employer:") or low.startswith("company:"):
                    company = line.split(":", 1)[1].strip()
            items.append(
                {
                    "source_site": "linkedin_snapshot",
                    "source_id": role_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary": "",
                    "employment_type": "",
                    "posted_at": "",
                    "source_url": f"https://www.linkedin.com/jobs/search/?keywords={title.replace(' ', '%20')}",
                    "description": desc,
                    "status": "active",
                    "raw_payload": row,
                }
            )
    dedup: Dict[str, dict] = {}
    for item in items:
        dedup[f"{item['source_site']}:{item['source_id']}"] = item
    return list(dedup.values())


def _write_snapshot(payload: Dict[str, List[dict]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"hk_jobs_snapshot_{stamp}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _flatten_snapshot(payload: Dict[str, List[dict]]) -> List[dict]:
    out: List[dict] = []
    for source_items in payload.values():
        out.extend(source_items or [])
    return out


def _group_keywords(items: Iterable[dict]) -> Dict[str, int]:
    keywords = defaultdict(int)
    for item in items:
        title = str(item.get("title") or "").lower()
        if "analyst" in title:
            keywords["analyst"] += 1
        if "engineer" in title:
            keywords["engineer"] += 1
        if "python" in title:
            keywords["python"] += 1
        if "data" in title:
            keywords["data"] += 1
    return dict(sorted(keywords.items(), key=lambda x: -x[1]))


def _get_bearer_token(backend_base: str, explicit_token: str, role: str, subject_id: str) -> str:
    if explicit_token.strip():
        return explicit_token.strip()
    res = requests.post(
        f"{backend_base.rstrip('/')}/bff/student/auth/dev_login",
        json={"subject_id": subject_id, "role": role, "ttl_s": 86400},
        timeout=20,
    )
    res.raise_for_status()
    data = res.json()
    token = str(data.get("token") or "")
    if not token:
        raise RuntimeError("Failed to obtain bearer token from /bff/student/auth/dev_login")
    return token


def _import_job_postings(
    backend_base: str,
    payload: Dict[str, List[dict]],
    token: str,
    chunk_size: int = 200,
) -> Dict[str, Any]:
    all_items = _flatten_snapshot(payload)
    if not all_items:
        return {"inserted": 0, "updated": 0, "count": 0}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Purpose": "system_audit",
    }
    total_inserted = 0
    total_updated = 0
    total_count = 0
    for i in range(0, len(all_items), chunk_size):
        batch = all_items[i:i + chunk_size]
        res = requests.post(
            f"{backend_base.rstrip('/')}/job-postings/import",
            headers=headers,
            data=json.dumps(batch, ensure_ascii=False),
            timeout=60,
        )
        res.raise_for_status()
        body = res.json()
        total_inserted += int(body.get("inserted") or 0)
        total_updated += int(body.get("updated") or 0)
        total_count += int(body.get("count") or 0)
    return {"inserted": total_inserted, "updated": total_updated, "count": total_count}


def _refresh_roles() -> int:
    cmd = ["python3", str(REPO_ROOT / "scripts" / "refresh_roles_and_skills.py")]
    env = {**os.environ}
    return subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, check=False).returncode


def main() -> None:
    ap = argparse.ArgumentParser(description="Run HK public job scraping + optional role refresh")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "data" / "job_postings")
    ap.add_argument("--refresh-roles", action="store_true")
    ap.add_argument("--import-api", action="store_true", help="Import scraped postings via POST /job-postings/import")
    ap.add_argument("--backend-url", default=os.getenv("BACKEND_API_URL", "http://127.0.0.1:8001"))
    ap.add_argument("--bearer-token", default=os.getenv("BACKEND_BEARER_TOKEN", ""))
    ap.add_argument("--auth-role", default=os.getenv("SCHEDULER_AUTH_ROLE", "admin"))
    ap.add_argument("--auth-subject-id", default=os.getenv("SCHEDULER_AUTH_SUBJECT_ID", "scheduler_bot"))
    ap.add_argument("--enable-fallback-role-files", action="store_true")
    args = ap.parse_args()

    payload = _run_all(args.pages)
    if sum(len(v) for v in payload.values()) == 0 and args.enable_fallback_role_files:
        payload["linkedin_fallback"] = _fallback_from_role_files()
    out = _write_snapshot(payload, args.out_dir)
    print(f"Wrote snapshot to {out}")
    flat = _flatten_snapshot(payload)
    print(f"Scraped total jobs={len(flat)} keyword_stats={_group_keywords(flat)}")
    if args.import_api:
        token = _get_bearer_token(
            backend_base=args.backend_url,
            explicit_token=args.bearer_token,
            role=args.auth_role,
            subject_id=args.auth_subject_id,
        )
        imported = _import_job_postings(args.backend_url, payload, token)
        print(f"Imported postings -> inserted={imported['inserted']} updated={imported['updated']} count={imported['count']}")
    if args.refresh_roles:
        rc = _refresh_roles()
        print(f"refresh_roles_and_skills exit={rc}")


if __name__ == "__main__":
    main()
