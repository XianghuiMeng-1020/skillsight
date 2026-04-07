#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List

from scripts.scrapers.base import JobPosting, ScraperBase


class CtGoodJobsScraper(ScraperBase):
    source_site = "ctgoodjobs_hk"
    base_url = "https://www.ctgoodjobs.hk"

    def scrape(self, keyword: str = "business analyst", pages: int = 2) -> List[JobPosting]:
        jobs: List[JobPosting] = []
        for page in range(1, pages + 1):
            path = f"/search/jobs/{keyword.replace(' ', '-')}/?page={page}"
            if not self.can_fetch(path):
                continue
            r = self.session.get(f"{self.base_url}{path}", timeout=20)
            if r.status_code >= 400:
                continue
            cards = re.split(r'class="job-item', r.text, flags=re.I)
            for card in cards:
                title = _first(card, r'title="([^"]+)"')
                link = _first(card, r'href="([^"]+/job/[^"]+)"')
                company = _first(card, r'class="company[^"]*"[^>]*>([^<]+)<')
                location = _first(card, r'class="location[^"]*"[^>]*>([^<]+)<')
                if not title or not link:
                    continue
                jobs.append(
                    JobPosting(
                        source_site=self.source_site,
                        source_id=link.split("/")[-1].split("?")[0],
                        title=self.normalize_text(title, 180),
                        company=self.normalize_text(company, 120),
                        location=self.normalize_text(location, 120),
                        salary="",
                        employment_type="",
                        posted_at="",
                        url=link if link.startswith("http") else f"{self.base_url}{link}",
                        description=self.normalize_text(_strip_html(card), 1800),
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
    ap = argparse.ArgumentParser(description="Scrape public CTgoodjobs listings")
    ap.add_argument("--keyword", default="business analyst")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--output", type=Path, default=Path("ctgoodjobs_jobs.json"))
    args = ap.parse_args()
    jobs = CtGoodJobsScraper().scrape(args.keyword, args.pages)
    args.output.write_text(json.dumps([j.to_dict() for j in jobs], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(jobs)} jobs to {args.output}")


if __name__ == "__main__":
    main()
