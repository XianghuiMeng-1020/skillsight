from __future__ import annotations

from typing import Dict

from sqlalchemy import text
from sqlalchemy.orm import Session


def compute_market_demand_index(db: Session) -> Dict[str, float]:
    rows = db.execute(
        text(
            """
            SELECT skill_id, COUNT(*) AS cnt
            FROM role_skill_requirements
            GROUP BY skill_id
            """
        )
    ).mappings().all()
    if not rows:
        return {}
    max_cnt = max(float(r["cnt"]) for r in rows) or 1.0
    out: Dict[str, float] = {}
    for r in rows:
        out[str(r["skill_id"])] = round(float(r["cnt"]) / max_cnt, 4)
    return out
