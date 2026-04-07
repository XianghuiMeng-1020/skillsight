#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List

from scripts.scrapers.base import JobPosting, ScraperBase


class JobsDbScraper(ScraperBase):
    source_site = "jobsdb_hk"
    base_url = "https://hk.jobsdb.com"

    def scrape(self, keyword: str = "data analyst", pages: int = 2) -> List[JobPosting]:
        jobs: List[JobPosting] = []
        for page in range(1, pages + 1):
            path = f"/jobs-in-hong-kong/{keyword.replace(' ', '-')}-jobs?page={page}"
            if not self.can_fetch(path):
                continue
            url = f"{self.base_url}{path}"
            r = self.session.get(url, timeout=20)
            if r.status_code >= 400:
                continue
            blocks = re.split(r"<article", r.text, flags=re.I)
            for block in blocks:
                title = _first(block, r'h3[^>]*>([^<]+)<')
                company = _first(block, r'data-automation="jobCompany"[^>]*>([^<]+)<')
                link = _first(block, r'href="([^"]+/job/[^"]+)"')
                location = _first(block, r'data-automation="jobLocation"[^>]*>([^<]+)<')
                salary = _first(block, r'data-automation="jobSalary"[^>]*>([^<]+)<')
                if not title or not link:
                    continue
                jobs.append(
                    JobPosting(
                        source_site=self.source_site,
                        source_id=link.split("/")[-1].split("?")[0],
                        title=self.normalize_text(title, 180),
                        company=self.normalize_text(company, 120),
                        location=self.normalize_text(location, 120),
                        salary=self.normalize_text(salary, 120),
                        employment_type="",
                        posted_at="",
                        url=link if link.startswith("http") else f"{self.base_url}{link}",
                        description=self.normalize_text(_strip_html(block), 1800),
                        raw_payload={"keyword": keyword, "page": page},
                    )
                )
            self.sleep()
        return self.dedup(jobs)


def _first(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape public JobsDB listings")
    ap.add_argument("--keyword", default="data analyst")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--output", type=Path, default=Path("jobsdb_jobs.json"))
    args = ap.parse_args()
    jobs = JobsDbScraper().scrape(args.keyword, args.pages)
    args.output.write_text(json.dumps([j.to_dict() for j in jobs], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(jobs)} jobs to {args.output}")


if __name__ == "__main__":
    main()
