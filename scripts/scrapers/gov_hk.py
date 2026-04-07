#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List

from scripts.scrapers.base import JobPosting, ScraperBase


class GovHkScraper(ScraperBase):
    source_site = "gov_hk_cspe"
    base_url = "https://www.csb.gov.hk"

    def scrape(self, pages: int = 2) -> List[JobPosting]:
        jobs: List[JobPosting] = []
        for page in range(1, pages + 1):
            path = f"/english/recruit/7.html?page={page}"
            if not self.can_fetch(path):
                continue
            r = self.session.get(f"{self.base_url}{path}", timeout=20)
            if r.status_code >= 400:
                continue
            rows = re.split(r"<tr", r.text, flags=re.I)
            for row in rows:
                title = _first(row, r'href="([^"]+)"[^>]*>([^<]+)<', group=2)
                link = _first(row, r'href="([^"]+)"', group=1)
                posted = _first(row, r'Closing date[^<]*</td>\s*<td[^>]*>([^<]+)<')
                if not title or not link:
                    continue
                full_url = link if link.startswith("http") else f"{self.base_url}{link}"
                jobs.append(
                    JobPosting(
                        source_site=self.source_site,
                        source_id=full_url.split("/")[-1].split(".")[0],
                        title=self.normalize_text(title, 180),
                        company="HKSAR Government",
                        location="Hong Kong",
                        salary="",
                        employment_type="public_service",
                        posted_at=self.normalize_text(posted, 80),
                        url=full_url,
                        description=self.normalize_text(_strip_html(row), 1600),
                        raw_payload={"page": page},
                    )
                )
            self.sleep()
        return self.dedup(jobs)


def _first(text: str, pattern: str, group: int = 1) -> str:
    m = re.search(pattern, text, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(group)).strip() if m else ""


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape public HK Government jobs")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--output", type=Path, default=Path("gov_hk_jobs.json"))
    args = ap.parse_args()
    jobs = GovHkScraper().scrape(args.pages)
    args.output.write_text(json.dumps([j.to_dict() for j in jobs], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(jobs)} jobs to {args.output}")


if __name__ == "__main__":
    main()
