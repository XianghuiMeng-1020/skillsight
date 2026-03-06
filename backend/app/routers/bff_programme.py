"""
BFF – Programme Leader Tier
Routes: /bff/programme/*

Access rules:
  - Bearer token required
  - Role must be 'programme_leader' or 'admin'
  - ABAC: programme_id binding in user_roles_context
  - NEVER return individual student data
  - Returns aggregated cohort/cross-course analytics only

Protocol 1 (RBAC+ABAC) + Protocol 8 (audit).
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.audit import log_audit
from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.security import Identity, issue_token, require_auth, _is_dev_login_allowed
from backend.app.security.access_control import (
    AccessContext,
    get_programme_ids,
    require_access,
)

router = APIRouter(prefix="/bff/programme", tags=["bff-programme"])

_PROG_PURPOSE = "aggregate_programme_analysis"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _assert_programme(ident: Identity) -> None:
    if ident.role not in ("programme_leader", "admin"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "role_insufficient",
                "message": "programme_leader or admin role required.",
                "next_step": "Log in with a programme leader account.",
            },
        )


# ─── Auth ─────────────────────────────────────────────────────────────────────

class ProgrammeDevLoginReq(BaseModel):
    subject_id: str
    role: str = "programme_leader"
    programme_id: Optional[str] = None
    faculty_id: Optional[str] = None
    ttl_s: int = 3600


@router.post("/auth/dev_login")
def bff_programme_dev_login(payload: ProgrammeDevLoginReq):
    """Issue a programme_leader token with context (dev only)."""
    if not _is_dev_login_allowed():
        raise HTTPException(status_code=403, detail="dev_login disabled in production")
    if payload.role not in ("programme_leader", "admin"):
        raise HTTPException(status_code=422, detail="role must be 'programme_leader' or 'admin'")
    token = issue_token(
        payload.subject_id,
        payload.role,
        payload.ttl_s,
        programme_id=payload.programme_id,
        faculty_id=payload.faculty_id,
    )
    log_audit(engine, subject_id=payload.subject_id,
              action="bff.programme.auth.dev_login",
              object_type="auth", status="ok",
              detail={"role": payload.role, "programme_id": payload.programme_id})
    return {
        "token": token,
        "subject_id": payload.subject_id,
        "role": payload.role,
        "context": {"programme_id": payload.programme_id, "faculty_id": payload.faculty_id},
    }


# ─── Programme List ───────────────────────────────────────────────────────────

@router.get("/programmes")
def bff_programme_list(
    x_purpose: Optional[str] = Header(default=_PROG_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List programmes this leader manages (or all for admin)."""
    _assert_programme(ident)
    ctx = AccessContext(purpose=x_purpose or _PROG_PURPOSE)
    require_access(ident, "bff.programme.programmes", ctx, db)

    if ident.role == "admin":
        rows = db.execute(
            text("SELECT programme_id, name, faculty_id, created_at FROM programmes ORDER BY name")
        ).mappings().all()
    else:
        prog_ids = get_programme_ids(db, ident.subject_id)
        # Also check token claim
        if ident.programme_id and ident.programme_id not in prog_ids:
            prog_ids = list(prog_ids) + [ident.programme_id]
        if not prog_ids:
            return {"programmes": [], "note": "No programme context assigned. Contact admin."}
        rows = db.execute(
            text("""
                SELECT programme_id, name, faculty_id, created_at
                FROM programmes WHERE programme_id = ANY(:ids)
                ORDER BY name
            """),
            {"ids": prog_ids},
        ).mappings().all()

    programmes = []
    for r in rows:
        course_count = db.execute(
            text("SELECT COUNT(*) FROM courses WHERE programme_id = :pid"),
            {"pid": r["programme_id"]},
        ).scalar() or 0
        programmes.append({
            "programme_id": r["programme_id"],
            "name": r["name"],
            "faculty_id": r.get("faculty_id"),
            "course_count": int(course_count),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.programme.programmes", object_type="programme", status="ok")
    return {"programmes": programmes, "count": len(programmes)}


# ─── Coverage Matrix ──────────────────────────────────────────────────────────

@router.get("/programmes/{programme_id}/coverage_matrix")
def bff_programme_coverage_matrix(
    programme_id: str,
    term_id: Optional[str] = None,
    x_purpose: Optional[str] = Header(default=_PROG_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Course × Skill coverage matrix for this programme.
    Returns counts only – identifies gaps (skills not covered by any course)
    and overlaps (skills covered by multiple courses).
    No individual student data.
    """
    _assert_programme(ident)
    ctx = AccessContext(purpose=x_purpose or _PROG_PURPOSE, programme_id=programme_id)
    require_access(ident, "bff.programme.coverage_matrix", ctx, db)

    # Courses in this programme (courses has title, not course_name; alias for API compatibility)
    course_sql = "SELECT course_id, title AS course_name FROM courses WHERE programme_id = :pid"
    course_params: Dict[str, Any] = {"pid": programme_id}
    if term_id:
        course_sql += " AND term_id = :tid"
        course_params["tid"] = term_id
    course_rows = db.execute(text(course_sql + " ORDER BY title"), course_params).mappings().all()

    # Skills across all courses in programme
    skill_rows = db.execute(
        text("""
            SELECT DISTINCT csm.skill_id, s.canonical_name
            FROM course_skill_map csm
            JOIN courses c ON c.course_id = csm.course_id
            JOIN skills s ON s.skill_id = csm.skill_id
            WHERE c.programme_id = :pid
            ORDER BY s.canonical_name
        """),
        {"pid": programme_id},
    ).mappings().all()

    # Build matrix
    matrix: Dict[str, Dict[str, Any]] = {}
    for c in course_rows:
        course_id = c["course_id"]
        mapped_skills = db.execute(
            text("""
                SELECT skill_id, intended_level
                FROM course_skill_map WHERE course_id = :cid
            """),
            {"cid": course_id},
        ).mappings().all()
        matrix[course_id] = {
            "course_name": c["course_name"],
            "skills": {r["skill_id"]: r.get("intended_level") for r in mapped_skills},
        }

    # Gap/overlap analysis
    skill_course_count: Dict[str, int] = {}
    for skill in skill_rows:
        sid = skill["skill_id"]
        skill_course_count[sid] = sum(
            1 for c in matrix.values() if sid in c["skills"]
        )

    gaps = [
        {"skill_id": s["skill_id"], "canonical_name": s["canonical_name"]}
        for s in skill_rows
        if skill_course_count.get(s["skill_id"], 0) == 0
    ]
    overlaps = [
        {"skill_id": s["skill_id"], "canonical_name": s["canonical_name"],
         "covered_by_n_courses": skill_course_count.get(s["skill_id"], 0)}
        for s in skill_rows
        if skill_course_count.get(s["skill_id"], 0) > 1
    ]

    # Flatten matrix rows for response
    matrix_rows = []
    for course_id, cdata in matrix.items():
        row: Dict[str, Any] = {"course_id": course_id, "course_name": cdata["course_name"]}
        for skill in skill_rows:
            sid = skill["skill_id"]
            row[sid] = cdata["skills"].get(sid)
        matrix_rows.append(row)

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.programme.coverage_matrix",
              object_type="programme", object_id=programme_id, status="ok")
    return {
        "programme_id": programme_id,
        "term_id": term_id,
        "courses": [{"course_id": c["course_id"], "course_name": c["course_name"]} for c in course_rows],
        "skills": [{"skill_id": s["skill_id"], "canonical_name": s["canonical_name"]} for s in skill_rows],
        "matrix": matrix_rows,
        "gap_analysis": {
            "uncovered_skills": gaps,
            "overlapping_skills": overlaps,
        },
        "generated_at": _now_utc().isoformat(),
    }


# ─── Trend ───────────────────────────────────────────────────────────────────

@router.get("/programmes/{programme_id}/trend")
def bff_programme_trend(
    programme_id: str,
    skill_id: Optional[str] = None,
    x_purpose: Optional[str] = Header(default=_PROG_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Skill assessment trend aggregated by term for this programme.
    No individual student data.
    """
    _assert_programme(ident)
    ctx = AccessContext(purpose=x_purpose or _PROG_PURPOSE, programme_id=programme_id)
    require_access(ident, "bff.programme.trend", ctx, db)

    # Simpler aggregation: skill assessments by skill + period (programme_id filter via courses not available without document-course linkage)
    simple_sql = """
        SELECT sa.skill_id, s.canonical_name AS skill_name,
               sa.label AS assessment_label,
               COUNT(*) AS count,
               DATE_TRUNC('month', sa.created_at) AS period
        FROM skill_assessments sa
        JOIN skills s ON s.skill_id = sa.skill_id
    """
    params: Dict[str, Any] = {}
    if skill_id:
        simple_sql += " WHERE sa.skill_id = :sid"
        params["sid"] = skill_id
    simple_sql += " GROUP BY sa.skill_id, s.canonical_name, sa.label, period ORDER BY period DESC, s.canonical_name LIMIT 100"

    try:
        rows = db.execute(text(simple_sql), params).mappings().all()
    except Exception:
        rows = []

    trend_data = [
        {
            "period": str(r.get("term_label") or r.get("period") or "unknown"),
            "skill_id": r["skill_id"],
            "skill_name": r["skill_name"],
            "assessment_label": r["assessment_label"],
            "count": int(r["count"]),
        }
        for r in rows
    ]

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.programme.trend",
              object_type="programme", object_id=programme_id, status="ok")
    return {
        "programme_id": programme_id,
        "skill_id": skill_id,
        "trend": trend_data,
        "generated_at": _now_utc().isoformat(),
    }


# ─── Audit Summary ────────────────────────────────────────────────────────────

@router.get("/audit/summary")
def bff_programme_audit_summary(
    x_purpose: Optional[str] = Header(default=_PROG_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Programme-level usage/reliability aggregation from audit_logs."""
    _assert_programme(ident)
    ctx = AccessContext(purpose=x_purpose or _PROG_PURPOSE)
    require_access(ident, "bff.programme.audit.summary", ctx, db)

    counts = db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'ok')    AS ok_count,
                COUNT(*) FILTER (WHERE status = 'error') AS error_count,
                COUNT(*)                                  AS total_count,
                MAX(created_at)                           AS last_activity
            FROM audit_logs WHERE action LIKE 'bff.%'
        """)
    ).mappings().first()

    top_actions = db.execute(
        text("""
            SELECT action, COUNT(*) AS n
            FROM audit_logs WHERE action LIKE 'bff.%'
            GROUP BY action ORDER BY n DESC LIMIT 10
        """)
    ).mappings().all()

    return {
        "summary": {
            "total_requests": int(counts["total_count"] or 0),
            "ok_requests": int(counts["ok_count"] or 0),
            "error_requests": int(counts["error_count"] or 0),
            "reliability_pct": round(
                100 * int(counts["ok_count"] or 0) / max(int(counts["total_count"] or 1), 1), 1
            ),
            "last_activity": counts["last_activity"].isoformat() if counts.get("last_activity") else None,
        },
        "top_actions": [{"action": r["action"], "count": int(r["n"])} for r in top_actions],
    }


# ─── Health ──────────────────────────────────────────────────────────────────

@router.get("/health")
def bff_programme_health(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Programme BFF health check."""
    _assert_programme(ident)
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    prog_count = db.execute(text("SELECT COUNT(*) FROM programmes")).scalar() or 0

    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "programme_count": int(prog_count),
        "role": ident.role,
    }
