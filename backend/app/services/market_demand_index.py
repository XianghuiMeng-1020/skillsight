from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session


def compute_market_demand_index(db: Session) -> Dict[str, float]:
    """Compute a normalised demand index (0..1) per skill.

    Prefers live job-posting signals when available; falls back to the
    role_skill_requirements table.  Returns a plain {skill_id: score} dict
    that callers can pass directly to ``score_role``.
    """
    # Try live job-posting signals first.
    try:
        posting_count = db.execute(
            text("SELECT COUNT(*) FROM job_postings WHERE status = 'active'")
        ).scalar() or 0
    except Exception:
        posting_count = 0

    if int(posting_count) > 0:
        rows = db.execute(
            text(
                """
                SELECT MIN(s.skill_id) AS skill_id,
                       COUNT(DISTINCT jp.posting_id) AS cnt
                FROM skills s
                JOIN job_postings jp
                  ON jp.status = 'active'
                 AND (
                   jp.title ILIKE ('%%' || s.canonical_name || '%%')
                   OR jp.description ILIKE ('%%' || s.canonical_name || '%%')
                 )
                GROUP BY LOWER(s.canonical_name)
                """
            )
        ).mappings().all()
    else:
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


def get_demand_index_meta(db: Session) -> Dict[str, Any]:
    """Return metadata about the demand index for display in the UI."""
    try:
        posting_count = db.execute(
            text("SELECT COUNT(*) FROM job_postings WHERE status = 'active'")
        ).scalar() or 0
        last_snapshot = db.execute(
            text("SELECT MAX(snapshot_at) FROM job_postings WHERE status = 'active'")
        ).scalar()
    except Exception:
        posting_count = 0
        last_snapshot = None

    now = datetime.now(timezone.utc)
    if last_snapshot is not None:
        if hasattr(last_snapshot, "tzinfo") and last_snapshot.tzinfo is None:
            last_snapshot = last_snapshot.replace(tzinfo=timezone.utc)
        age_days: Optional[int] = (now - last_snapshot).days
        last_updated: Optional[str] = last_snapshot.strftime("%Y-%m")
    else:
        age_days = None
        last_updated = None

    source = "job_postings" if int(posting_count) > 0 else "role_requirements"
    return {
        "source": source,
        "total_active_postings": int(posting_count),
        "last_updated": last_updated,
        "data_age_days": age_days,
        "is_stale": (age_days is not None and age_days > 30),
        "computed_at": now.isoformat(),
    }
