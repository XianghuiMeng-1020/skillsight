"""
BFF – Staff Tier (Instructor / TA)
Routes: /bff/staff/*

Access rules:
  - Bearer token required (require_auth)
  - Role must be 'staff' or 'admin'
  - ABAC: teaching_relation check for course-scoped endpoints
  - NEVER return individual student data (subject_id, chunk_text, snippets, etc.)
  - Aggregate stats + review ticket metadata only

Protocol 1 (RBAC+ABAC) + Protocol 4 (review workflow) + Protocol 8 (audit).
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.audit import log_audit
from backend.app.change_log_events import write_change_event
from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.security import Identity, issue_token, require_auth, _is_dev_login_allowed
from backend.app.security.access_control import (
    AccessContext,
    PERSONAL_DATA_DENYLIST,
    get_staff_courses,
    require_access,
    sanitise_response,
)

router = APIRouter(prefix="/bff/staff", tags=["bff-staff"])

_STAFF_PURPOSE = "teaching_support"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _assert_staff(ident: Identity) -> None:
    if ident.role not in ("staff", "admin"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "role_insufficient",
                "message": "Staff or admin role required.",
                "next_step": "Log in with a staff account.",
            },
        )


# ─── Auth ─────────────────────────────────────────────────────────────────────

class StaffDevLoginReq(BaseModel):
    subject_id: str
    role: str = "staff"
    faculty_id: Optional[str] = None
    programme_id: Optional[str] = None
    course_ids: Optional[List[str]] = None
    term_id: Optional[str] = None
    ttl_s: int = 3600


@router.post("/auth/dev_login")
def bff_staff_dev_login(payload: StaffDevLoginReq):
    """Issue a staff token with ABAC context claims (dev only)."""
    if not _is_dev_login_allowed():
        raise HTTPException(status_code=403, detail="dev_login disabled in production")
    if payload.role not in ("staff", "admin"):
        raise HTTPException(status_code=422, detail="role must be 'staff' or 'admin'")
    token = issue_token(
        payload.subject_id,
        payload.role,
        payload.ttl_s,
        faculty_id=payload.faculty_id,
        programme_id=payload.programme_id,
        course_ids=payload.course_ids,
        term_id=payload.term_id,
    )
    log_audit(
        engine,
        subject_id=payload.subject_id,
        action="bff.staff.auth.dev_login",
        object_type="auth",
        status="ok",
        detail={"role": payload.role},
    )
    return {
        "token": token,
        "subject_id": payload.subject_id,
        "role": payload.role,
        "context": {
            "faculty_id": payload.faculty_id,
            "programme_id": payload.programme_id,
            "course_ids": payload.course_ids,
            "term_id": payload.term_id,
        },
    }


# ─── Course list ──────────────────────────────────────────────────────────────

@router.get("/courses")
def bff_staff_courses(
    x_purpose: Optional[str] = Header(default=_STAFF_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Return courses where this staff member has a teaching relation.
    Admin sees all courses.
    """
    _assert_staff(ident)
    ctx = AccessContext(purpose=x_purpose or _STAFF_PURPOSE)
    require_access(ident, "bff.staff.courses", ctx, db)

    if ident.role == "admin":
        rows = db.execute(
            text("""
                SELECT c.course_id, c.title AS course_name, c.description,
                       c.programme_id, c.faculty_id, c.term_id
                FROM courses c ORDER BY c.title LIMIT 100
            """)
        ).mappings().all()
    else:
        course_ids = get_staff_courses(db, ident.subject_id)
        if not course_ids:
            return {"courses": [], "note": "No teaching relations found for your account."}
        rows = db.execute(
            text("""
                SELECT c.course_id, c.title AS course_name, c.description,
                       c.programme_id, c.faculty_id, c.term_id
                FROM courses c
                WHERE c.course_id = ANY(:ids)
                ORDER BY c.title
            """),
            {"ids": course_ids},
        ).mappings().all()

    courses = []
    for r in rows:
        # Count skills mapped to this course (aggregate only)
        skill_count = db.execute(
            text("SELECT COUNT(*) FROM course_skill_map WHERE course_id = :cid"),
            {"cid": r["course_id"]},
        ).scalar() or 0
        ticket_count = db.execute(
            text("SELECT COUNT(*) FROM review_tickets WHERE scope_course_id = :cid AND status = 'open'"),
            {"cid": r["course_id"]},
        ).scalar() or 0
        courses.append({
            "course_id": r["course_id"],
            "course_name": r["course_name"],
            "description": r.get("description"),
            "programme_id": r.get("programme_id"),
            "term_id": r.get("term_id"),
            "mapped_skills_count": int(skill_count),
            "open_review_tickets": int(ticket_count),
        })

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.staff.courses", object_type="courses", status="ok")
    return {"courses": courses, "count": len(courses)}


# ─── Course Skills Summary ────────────────────────────────────────────────────

@router.get("/courses/{course_id}/skills_summary")
def bff_staff_course_skills_summary(
    course_id: str,
    x_purpose: Optional[str] = Header(default=_STAFF_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Aggregated skill coverage for a course.
    Returns counts/percentages – NO individual student data.
    """
    _assert_staff(ident)
    ctx = AccessContext(purpose=x_purpose or _STAFF_PURPOSE, course_id=course_id)
    require_access(ident, "bff.staff.courses.skills_summary", ctx, db)

    # Mapped skills for this course
    skill_rows = db.execute(
        text("""
            SELECT csm.skill_id, s.canonical_name, csm.required_level,
                   csm.decision
            FROM course_skill_map csm
            LEFT JOIN skills s ON s.skill_id = csm.skill_id
            WHERE csm.course_id = :cid
            ORDER BY s.canonical_name
        """),
        {"cid": course_id},
    ).mappings().all()

    skills_summary = []
    for sr in skill_rows:
        sid = sr["skill_id"]
        # Aggregate evidence counts (no personal attribution)
        evidence_count = db.execute(
            text("""
                SELECT COUNT(DISTINCT sa.assessment_id)
                FROM skill_assessments sa
                WHERE sa.skill_id = :sid
            """),
            {"sid": sid},
        ).scalar() or 0
        assessed_count = db.execute(
            text("""
                SELECT COUNT(*) FROM skill_assessments
                WHERE skill_id = :sid AND label IN ('demonstrated', 'mentioned')
            """),
            {"sid": sid},
        ).scalar() or 0

        skills_summary.append({
            "skill_id": sid,
            "canonical_name": sr.get("canonical_name"),
            "required_level": sr.get("required_level"),
            "review_status": sr.get("decision") or "pending",
            "evidence_count": int(evidence_count),
            "demonstrated_count": int(assessed_count),
        })

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.staff.courses.skills_summary",
              object_type="course", object_id=course_id, status="ok")
    return {
        "course_id": course_id,
        "mapped_skills": len(skills_summary),
        "skills": skills_summary,
        "generated_at": _now_utc().isoformat(),
    }


# ─── Review Queue ─────────────────────────────────────────────────────────────

@router.get("/courses/{course_id}/review_queue")
def bff_staff_review_queue(
    course_id: str,
    status: Optional[str] = None,
    x_purpose: Optional[str] = Header(default=_STAFF_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Review tickets for this course.
    Returns ticket metadata only – no original text / chunk snippets.
    """
    _assert_staff(ident)
    ctx = AccessContext(purpose=x_purpose or _STAFF_PURPOSE, course_id=course_id)
    require_access(ident, "bff.staff.courses.review_queue", ctx, db)

    sql = """
        SELECT ticket_id, created_at, status, scope_course_id, scope_term_id,
               skill_id, role_id, uncertainty_reason, routed_to_role,
               evidence_pointers, resolved_at,
               (draft_json->>'draft_label') AS draft_label,
               (draft_json->>'draft_rationale') AS draft_rationale
        FROM review_tickets
        WHERE scope_course_id = :cid
    """
    params: Dict[str, Any] = {"cid": course_id}
    if status:
        sql += " AND status = :st"
        params["st"] = status
    sql += " ORDER BY created_at DESC LIMIT 100"

    rows = db.execute(text(sql), params).mappings().all()

    tickets = []
    for r in rows:
        tickets.append({
            "ticket_id": str(r["ticket_id"]),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "status": r["status"],
            "course_id": r.get("scope_course_id"),
            "term_id": r.get("scope_term_id"),
            "skill_id": r.get("skill_id"),
            "role_id": r.get("role_id"),
            "uncertainty_reason": r.get("uncertainty_reason"),
            "routed_to_role": r.get("routed_to_role"),
            "draft_label": r.get("draft_label"),
            "draft_rationale": r.get("draft_rationale"),
            "evidence_pointers": r.get("evidence_pointers") or [],
            "resolved_at": r["resolved_at"].isoformat() if r.get("resolved_at") else None,
        })

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.staff.courses.review_queue",
              object_type="course", object_id=course_id, status="ok",
              detail={"ticket_count": len(tickets)})
    return {
        "course_id": course_id,
        "count": len(tickets),
        "tickets": tickets,
    }


# ─── Single Review Ticket (for detail page) ─────────────────────────────────────

@router.get("/review/{ticket_id}")
def bff_staff_review_ticket(
    ticket_id: str,
    x_purpose: Optional[str] = Header(default=_STAFF_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Get a single review ticket by id. Staff must have access to the ticket's course."""
    _assert_staff(ident)
    row = db.execute(
        text("""
            SELECT ticket_id, created_at, status, scope_course_id, scope_term_id,
                   skill_id, role_id, uncertainty_reason, routed_to_role,
                   evidence_pointers, resolved_at, resolved_by, resolution,
                   (draft_json->>'draft_label') AS draft_label,
                   (draft_json->>'draft_rationale') AS draft_rationale
            FROM review_tickets
            WHERE ticket_id = :tid
            LIMIT 1
        """),
        {"tid": ticket_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Review ticket not found")
    ctx = AccessContext(
        purpose=x_purpose or _STAFF_PURPOSE,
        course_id=row.get("scope_course_id"),
    )
    require_access(ident, "bff.staff.review.get", ctx, db)
    return {
        "ticket_id": str(row["ticket_id"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "status": row["status"],
        "course_id": row.get("scope_course_id"),
        "term_id": row.get("scope_term_id"),
        "skill_id": row.get("skill_id"),
        "role_id": row.get("role_id"),
        "uncertainty_reason": row.get("uncertainty_reason"),
        "routed_to_role": row.get("routed_to_role"),
        "draft_label": row.get("draft_label"),
        "draft_rationale": row.get("draft_rationale"),
        "evidence_pointers": row.get("evidence_pointers") or [],
        "resolved_at": row["resolved_at"].isoformat() if row.get("resolved_at") else None,
        "resolved_by": row.get("resolved_by"),
        "resolution": row.get("resolution"),
    }


# ─── Resolve Review Ticket ────────────────────────────────────────────────────

class ResolveTicketReq(BaseModel):
    decision: str  # approve | reject | needs_more_evidence
    comment: Optional[str] = None


@router.post("/review/{ticket_id}/resolve")
def bff_staff_resolve_ticket(
    ticket_id: str,
    payload: ResolveTicketReq,
    x_purpose: Optional[str] = Header(default=_STAFF_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Resolve a review ticket. Writes audit trail for traceability.
    Decision must be: approve | reject | needs_more_evidence
    """
    _assert_staff(ident)
    allowed_decisions = {"approve", "reject", "needs_more_evidence"}
    if payload.decision not in allowed_decisions:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_decision",
                    "message": f"Decision must be one of: {sorted(allowed_decisions)}"},
        )

    # Fetch ticket to verify it exists and route check
    ticket = db.execute(
        text("SELECT ticket_id, scope_course_id, status FROM review_tickets WHERE ticket_id = :tid"),
        {"tid": ticket_id},
    ).mappings().first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Review ticket not found.")
    if ticket["status"] == "resolved":
        raise HTTPException(status_code=409,
                            detail="Ticket already resolved.")

    ctx = AccessContext(
        purpose=x_purpose or _STAFF_PURPOSE,
        course_id=ticket.get("scope_course_id"),
    )
    require_access(ident, "bff.staff.review.resolve", ctx, db)

    now = _now_utc()
    new_status = "resolved" if payload.decision in ("approve", "reject") else "open"

    db.execute(
        text("""
            UPDATE review_tickets
            SET status = :st,
                resolved_by = :who,
                resolved_at = :now,
                resolution = (:res)::jsonb
            WHERE ticket_id = :tid
        """),
        {
            "st": new_status,
            "who": ident.subject_id,
            "now": now,
            "res": __import__("json").dumps(
                {"decision": payload.decision, "comment": payload.comment, "resolved_by": ident.subject_id}
            ),
            "tid": ticket_id,
        },
    )
    db.commit()

    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.staff.review.resolve",
        object_type="review_ticket",
        object_id=ticket_id,
        status="ok",
        detail={"decision": payload.decision, "new_status": new_status},
    )

    # P5 Protocol 4: write change_log_events for human_review_resolved
    if new_status == "resolved":
        write_change_event(
            engine,
            scope="staff",
            event_type="human_review_resolved",
            subject_id=ident.subject_id,
            entity_key=ticket_id,
            before_state={"status": "open", "ticket_id": ticket_id},
            after_state={"status": "resolved", "decision": payload.decision, "resolved_by": ident.subject_id, "resolved_at": now.isoformat()},
            diff={"status": "open -> resolved", "decision": payload.decision},
            why={"rule_triggers": ["staff_resolve"], "comment": payload.comment or ""},
            actor_role="staff",
        )

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "decision": payload.decision,
        "status": new_status,
        "resolved_at": now.isoformat(),
    }


# ─── Skill Definitions (read-only registry) ──────────────────────────────────

@router.get("/skills/definitions")
def bff_staff_skill_definitions(
    search: Optional[str] = None,
    limit: int = 50,
    x_purpose: Optional[str] = Header(default=_STAFF_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Official skill definitions (read-only for staff)."""
    _assert_staff(ident)
    ctx = AccessContext(purpose=x_purpose or _STAFF_PURPOSE)
    require_access(ident, "bff.staff.skills.definitions", ctx, db)

    sql = "SELECT skill_id, canonical_name, definition FROM skills"
    params: Dict[str, Any] = {}
    if search:
        sql += " WHERE canonical_name ILIKE :q OR definition ILIKE :q"
        params["q"] = f"%{search}%"
    sql += " ORDER BY canonical_name LIMIT :lim"
    params["lim"] = min(limit, 200)

    rows = db.execute(text(sql), params).mappings().all()
    return {
        "count": len(rows),
        "skills": [{"skill_id": r["skill_id"], "canonical_name": r["canonical_name"],
                    "definition": r.get("definition")} for r in rows],
    }


# ─── Audit Summary (course-scoped) ───────────────────────────────────────────

@router.get("/audit/summary")
def bff_staff_audit_summary(
    course_id: Optional[str] = None,
    limit: int = 50,
    x_purpose: Optional[str] = Header(default=_STAFF_PURPOSE, alias="X-Purpose"),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Aggregated audit summary (action counts by type, last N entries).
    Staff see only entries related to their course scope.
    """
    _assert_staff(ident)
    ctx = AccessContext(purpose=x_purpose or _STAFF_PURPOSE, course_id=course_id)
    require_access(ident, "bff.staff.audit.summary", ctx, db)

    action_counts = db.execute(
        text("""
            SELECT action, status, COUNT(*) AS n
            FROM audit_logs
            WHERE action LIKE 'bff.%'
            GROUP BY action, status
            ORDER BY n DESC LIMIT 30
        """)
    ).mappings().all()

    recent = db.execute(
        text("""
            SELECT action, status, created_at, request_id
            FROM audit_logs
            WHERE action LIKE 'bff.%'
            ORDER BY created_at DESC LIMIT :lim
        """),
        {"lim": min(limit, 100)},
    ).mappings().all()

    return {
        "action_counts": [dict(r) for r in action_counts],
        "recent_entries": [
            {
                "action": r["action"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "request_id": r.get("request_id"),
            }
            for r in recent
        ],
    }


# ─── Health ──────────────────────────────────────────────────────────────────

@router.get("/health")
def bff_staff_health(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Staff BFF health check."""
    _assert_staff(ident)
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    open_tickets = db.execute(
        text("SELECT COUNT(*) FROM review_tickets WHERE status = 'open'")
    ).scalar() or 0

    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "open_review_tickets": int(open_tickets),
        "role": ident.role,
        "subject_id": ident.subject_id,
    }
