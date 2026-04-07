from __future__ import annotations

import re
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session


def market_skill_trends(db: Session, limit: int = 12) -> List[Dict[str, Any]]:
    # Prefer real market signals from scraped job postings.
    # Fallback to role_skill_requirements when postings are not available yet.
    posting_count = db.execute(
        text("SELECT COUNT(*) FROM job_postings WHERE status = 'active'")
    ).scalar() or 0
    if int(posting_count) <= 0:
        rows = db.execute(
            text(
                """
                SELECT rsr.skill_id, s.canonical_name, COUNT(*) AS demand_count
                FROM role_skill_requirements rsr
                LEFT JOIN skills s ON s.skill_id = rsr.skill_id
                GROUP BY rsr.skill_id, s.canonical_name
                ORDER BY demand_count DESC
                LIMIT :lim
                """
            ),
            {"lim": max(1, min(limit, 50))},
        ).mappings().all()
        return [
            {
                "skill_id": str(r["skill_id"]),
                "skill_name": str(r.get("canonical_name") or r["skill_id"]),
                "demand_count": int(r["demand_count"]),
            }
            for r in rows
        ]

    rows = db.execute(
        text(
            """
            SELECT s.skill_id, s.canonical_name, COUNT(jp.posting_id) AS demand_count
            FROM skills s
            JOIN job_postings jp
              ON jp.status = 'active'
             AND (
               jp.title ILIKE ('%%' || s.canonical_name || '%%')
               OR jp.description ILIKE ('%%' || s.canonical_name || '%%')
             )
            GROUP BY s.skill_id, s.canonical_name
            ORDER BY demand_count DESC
            LIMIT :lim
            """
        ),
        {"lim": max(1, min(limit, 50))},
    ).mappings().all()
    return [
        {
            "skill_id": str(r["skill_id"]),
            "skill_name": str(r.get("canonical_name") or r["skill_id"]),
            "demand_count": int(r["demand_count"]),
        }
        for r in rows
    ]


def _extract_salary_numbers(salary_text: str) -> List[int]:
    nums: List[int] = []
    if not salary_text:
        return nums
    for match in re.findall(r"(\d[\d,]{3,})", salary_text):
        try:
            nums.append(int(match.replace(",", "")))
        except ValueError:
            continue
    return nums


def _bucket_role(title: str) -> str:
    lower = (title or "").lower()
    if "business analyst" in lower:
        return "Business Analyst"
    if "analyst" in lower:
        return "Data Analyst"
    if "ai" in lower or "machine learning" in lower or "ml " in lower:
        return "AI Engineer"
    if "software" in lower or "python" in lower or "developer" in lower or "engineer" in lower:
        return "Software Engineer"
    return "General Professional"


def salary_reference(db: Session | None = None) -> Dict[str, Any]:
    if db is None:
        return {
            "currency": "HKD",
            "source": "fallback_static",
            "bands": [
                {"role": "Data Analyst", "range": "22000-35000"},
                {"role": "Business Analyst", "range": "25000-42000"},
                {"role": "AI Engineer", "range": "32000-60000"},
            ],
        }

    rows = db.execute(
        text(
            """
            SELECT title, salary
            FROM job_postings
            WHERE status = 'active' AND salary IS NOT NULL AND salary <> ''
            ORDER BY snapshot_at DESC
            LIMIT 2000
            """
        )
    ).mappings().all()

    buckets: Dict[str, List[int]] = {}
    for row in rows:
        values = _extract_salary_numbers(str(row.get("salary") or ""))
        if not values:
            continue
        role = _bucket_role(str(row.get("title") or ""))
        buckets.setdefault(role, []).extend(values)

    bands: List[Dict[str, str]] = []
    for role, values in buckets.items():
        if not values:
            continue
        low = min(values)
        high = max(values)
        if low > high:
            low, high = high, low
        bands.append({"role": role, "range": f"{low}-{high}"})
    bands.sort(key=lambda b: b["role"])

    if not bands:
        return {
            "currency": "HKD",
            "source": "fallback_static",
            "bands": [
                {"role": "Data Analyst", "range": "22000-35000"},
                {"role": "Business Analyst", "range": "25000-42000"},
                {"role": "AI Engineer", "range": "32000-60000"},
            ],
        }

    return {
        "currency": "HKD",
        "source": "job_postings",
        "bands": bands[:8],
    }
