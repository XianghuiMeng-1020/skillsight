from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def _fetch_courses_for_skill(db: Session, skill_id: str) -> List[Dict[str, Any]]:
    """Return approved course recommendations for a given skill via course_skill_map."""
    try:
        rows = db.execute(
            text(
                """
                SELECT c.course_id, c.title, c.provider, c.url, c.level,
                       csm.relevance_score
                FROM course_skill_map csm
                JOIN courses c ON c.course_id = csm.course_id
                WHERE csm.skill_id = :sid
                  AND (csm.status = 'approved' OR csm.status IS NULL)
                ORDER BY COALESCE(csm.relevance_score, 0) DESC
                LIMIT 3
                """
            ),
            {"sid": skill_id},
        ).mappings().all()
        return [
            {
                "course_id": str(r["course_id"]),
                "title": str(r["title"] or ""),
                "provider": str(r.get("provider") or ""),
                "url": str(r.get("url") or ""),
                "level": str(r.get("level") or ""),
                "relevance_score": float(r.get("relevance_score") or 0),
            }
            for r in rows
        ]
    except Exception:
        return []


def recommend_learning_path(
    db: Session,
    subject_id: str,
    limit: int = 8,
    target_role_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return prioritised skill gaps with estimated study effort and linked courses.

    Each item includes:
    - skill_id / skill_name: the skill to develop
    - current_level / target_level / gap: proficiency delta
    - estimated_hours: rough study effort estimate
    - milestones: ordered action steps
    - recommended_courses: list of courses from course_skill_map (may be empty)
    """
    # Build base query with optional role filter
    if target_role_id:
        sql = """
            SELECT rsr.skill_id, s.canonical_name, MAX(rsr.target_level) AS target_level,
                   COALESCE(MAX(sp.level), 0) AS current_level
            FROM role_skill_requirements rsr
            LEFT JOIN skills s ON s.skill_id = rsr.skill_id
            LEFT JOIN skill_proficiency sp ON sp.skill_id = rsr.skill_id
            LEFT JOIN consents c ON c.doc_id = sp.doc_id::text AND c.user_id = :sub AND c.status = 'granted'
            WHERE rsr.role_id = :role_id
            GROUP BY rsr.skill_id, s.canonical_name
            ORDER BY (MAX(rsr.target_level) - COALESCE(MAX(sp.level), 0)) DESC
            LIMIT :lim
        """
        params: Dict[str, Any] = {"sub": subject_id, "role_id": target_role_id, "lim": max(1, min(limit, 20))}
    else:
        sql = """
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
        params = {"sub": subject_id, "lim": max(1, min(limit, 20))}

    rows = db.execute(text(sql), params).mappings().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        gap = max(0, int(r["target_level"] or 0) - int(r["current_level"] or 0))
        if gap <= 0:
            continue

        skill_id = str(r["skill_id"])
        skill_name = str(r.get("canonical_name") or skill_id)

        # Fetch linked courses from course_skill_map
        recommended_courses = _fetch_courses_for_skill(db, skill_id)

        # Build milestone steps; include course title if available
        milestones: List[str] = []
        if recommended_courses:
            milestones.append(f"Enroll in: {recommended_courses[0]['title'] or 'a recommended course'}")
        milestones += [
            "Build one portfolio artifact demonstrating this skill",
            "Run an interactive self-assessment to verify progress",
        ]

        out.append(
            {
                "skill_id": skill_id,
                "skill_name": skill_name,
                "current_level": int(r["current_level"] or 0),
                "target_level": int(r["target_level"] or 0),
                "gap": gap,
                "estimated_hours": gap * 12,
                "milestones": milestones,
                "recommended_courses": recommended_courses,
            }
        )
    return out
