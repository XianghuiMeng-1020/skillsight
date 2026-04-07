from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session


def recommend_learning_path(db: Session, subject_id: str, limit: int = 8) -> List[Dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT rsr.skill_id, s.canonical_name, MAX(rsr.target_level) AS target_level,
                   COALESCE(MAX(sp.level), 0) AS current_level
            FROM role_skill_requirements rsr
            LEFT JOIN skills s ON s.skill_id = rsr.skill_id
            LEFT JOIN skill_proficiency sp ON sp.skill_id = rsr.skill_id
            LEFT JOIN consents c ON c.doc_id = sp.doc_id::text AND c.user_id = :sub AND c.status = 'granted'
            GROUP BY rsr.skill_id, s.canonical_name
            ORDER BY (MAX(rsr.target_level) - COALESCE(MAX(sp.level), 0)) DESC
            LIMIT :lim
            """
        ),
        {"sub": subject_id, "lim": max(1, min(limit, 20))},
    ).mappings().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        gap = max(0, int(r["target_level"] or 0) - int(r["current_level"] or 0))
        if gap <= 0:
            continue
        out.append(
            {
                "skill_id": str(r["skill_id"]),
                "skill_name": str(r.get("canonical_name") or r["skill_id"]),
                "current_level": int(r["current_level"] or 0),
                "target_level": int(r["target_level"] or 0),
                "gap": gap,
                "estimated_hours": gap * 12,
                "milestones": [
                    "Complete one guided course module",
                    "Build one portfolio artifact",
                    "Run one interactive assessment",
                ],
            }
        )
    return out
