#!/usr/bin/env python3
"""
Import mainland China job postings (Boss直聘) into SkillSight.

Fetches real job data from Boss直聘 using the scraper in
scripts/scrapers/boss_zhipin.py and imports via POST /job-postings/import.

Usage:
    # Import to production (with admin token)
    python3 scripts/import_mainland_jobs.py \
        --backend-url https://skillsight-api.onrender.com \
        --token YOUR_ADMIN_TOKEN

    # Dry-run: print JSON only, no upload
    python3 scripts/import_mainland_jobs.py --dry-run

    # Seed only (skip live API scraping)
    python3 scripts/import_mainland_jobs.py --dry-run --no-api

    # Save snapshot for review
    python3 scripts/import_mainland_jobs.py --dry-run \
        --out data/job_postings/mainland_jobs_snapshot.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.scrapers.boss_zhipin import scrape_mainland_jobs

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKEND = "http://localhost:8000"


def _get_token(token_arg: str | None) -> str:
    if token_arg:
        return token_arg
    env = os.environ.get("SKILLSIGHT_ADMIN_TOKEN", "")
    if env:
        return env
    raise SystemExit(
        "No token provided. Use --token or set SKILLSIGHT_ADMIN_TOKEN env var."
    )


def _import(backend_url: str, token: str, jobs: list[dict]) -> dict:
    """POST jobs to /job-postings/import in batches of 100."""
    url = backend_url.rstrip("/") + "/job-postings/import"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    inserted_total = 0
    updated_total = 0

    for i in range(0, len(jobs), 100):
        batch = jobs[i : i + 100]
        r = requests.post(url, json=batch, headers=headers, timeout=60)
        if r.status_code not in (200, 201):
            print(f"  [!] Batch {i//100 + 1} failed: HTTP {r.status_code} — {r.text[:200]}")
            continue
        data = r.json()
        inserted_total += data.get("inserted", 0)
        updated_total += data.get("updated", 0)
        print(f"  Batch {i//100 + 1}: +{data.get('inserted', 0)} inserted, ~{data.get('updated', 0)} updated")
        time.sleep(0.5)

    return {"inserted": inserted_total, "updated": updated_total}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Boss直聘 mainland jobs into SkillSight")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND, help="SkillSight API base URL")
    parser.add_argument("--token", default=None, help="Admin JWT token")
    parser.add_argument("--dry-run", action="store_true", help="Print payload and exit, do not upload")
    parser.add_argument("--no-api", action="store_true", help="Skip live API scraping, use seed only")
    parser.add_argument("--out", default="", help="Also save snapshot to this file path")
    args = parser.parse_args()

    snapshot_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    print(f"[{snapshot_ts}] Scraping mainland China jobs (Boss直聘)…")
    jobs = scrape_mainland_jobs(use_api=not args.no_api, fallback_to_seed=True)
    print(f"  Collected {len(jobs)} job postings")

    if args.out:
        out_path = REPO_ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  Saved snapshot → {out_path}")

    if args.dry_run:
        print(json.dumps(jobs[:3], ensure_ascii=False, indent=2))
        print(f"  … (showing first 3 of {len(jobs)} total)")
        print("[dry-run] Done — no data uploaded.")
        return

    token = _get_token(args.token)
    print(f"  Importing to {args.backend_url} …")
    result = _import(args.backend_url, token, jobs)
    print(f"Done. Total: +{result['inserted']} inserted, ~{result['updated']} updated.")


if __name__ == "__main__":
    main()
