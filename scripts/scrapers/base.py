#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests


DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class JobPosting:
    source_site: str
    source_id: str
    title: str
    company: str
    location: str
    salary: str
    employment_type: str
    posted_at: str
    url: str
    description: str
    raw_payload: Dict[str, object]

    def dedup_key(self) -> str:
        blob = f"{self.source_site}|{self.source_id}|{self.title}|{self.company}|{self.location}"
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, object]:
        out = asdict(self)
        out["ingested_at"] = datetime.now(timezone.utc).isoformat()
        out["dedup_key"] = self.dedup_key()
        return out


class ScraperBase:
    source_site = "unknown"
    base_url = ""
    min_delay_s = 1.5
    max_delay_s = 3.5

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_UA, "Accept-Language": "en-US,en;q=0.9"})
        self._robots = RobotFileParser()
        self._robots_loaded = False
        self._seen: set[str] = set()

    def sleep(self) -> None:
        time.sleep(random.uniform(self.min_delay_s, self.max_delay_s))

    def _load_robots(self) -> None:
        if self._robots_loaded:
            return
        parsed = urlparse(self.base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        self._robots.set_url(robots_url)
        try:
            self._robots.read()
        except Exception:
            pass
        self._robots_loaded = True

    def can_fetch(self, path_or_url: str) -> bool:
        self._load_robots()
        parsed = urlparse(path_or_url)
        path = parsed.path if parsed.scheme else path_or_url
        try:
            return self._robots.can_fetch(DEFAULT_UA, path)
        except Exception:
            return True

    def dedup(self, jobs: Iterable[JobPosting]) -> List[JobPosting]:
        out: List[JobPosting] = []
        for job in jobs:
            key = job.dedup_key()
            if key in self._seen:
                continue
            self._seen.add(key)
            out.append(job)
        return out

    @staticmethod
    def normalize_text(text: str, limit: int = 4000) -> str:
        compact = re.sub(r"\s+", " ", (text or "")).strip()
        return compact[:limit]

    @staticmethod
    def dump_json(path: Path, jobs: List[JobPosting]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [j.to_dict() for j in jobs]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
