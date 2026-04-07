from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session


def market_skill_trends(db: Session, limit: int = 12) -> List[Dict[str, Any]]:
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


def salary_reference() -> Dict[str, Any]:
    return {
        "currency": "HKD",
        "bands": [
            {"role": "Data Analyst", "range": "22000-35000"},
            {"role": "Business Analyst", "range": "25000-42000"},
            {"role": "AI Engineer", "range": "32000-60000"},
        ],
    }
