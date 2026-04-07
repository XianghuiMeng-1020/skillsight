#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from scripts.scrapers import CtGoodJobsScraper, GovHkScraper, JobsDbScraper


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_all(pages: int) -> Dict[str, List[dict]]:
    jobsdb = [j.to_dict() for j in JobsDbScraper().scrape("data analyst", pages)]
    ct = [j.to_dict() for j in CtGoodJobsScraper().scrape("business analyst", pages)]
    gov = [j.to_dict() for j in GovHkScraper().scrape(pages)]
    return {"jobsdb": jobsdb, "ctgoodjobs": ct, "gov_hk": gov}


def _write_snapshot(payload: Dict[str, List[dict]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"hk_jobs_snapshot_{stamp}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _refresh_roles() -> int:
    cmd = ["python3", str(REPO_ROOT / "scripts" / "refresh_roles_and_skills.py")]
    env = {**os.environ}
    return subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, check=False).returncode


def main() -> None:
    ap = argparse.ArgumentParser(description="Run HK public job scraping + optional role refresh")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "data" / "job_postings")
    ap.add_argument("--refresh-roles", action="store_true")
    args = ap.parse_args()

    payload = _run_all(args.pages)
    out = _write_snapshot(payload, args.out_dir)
    print(f"Wrote snapshot to {out}")
    if args.refresh_roles:
        rc = _refresh_roles()
        print(f"refresh_roles_and_skills exit={rc}")


if __name__ == "__main__":
    main()
