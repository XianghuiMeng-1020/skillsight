"""
Protocol 1: Access Control – RBAC + ABAC Policy Engine
=======================================================

All BFF routes must call `require_access(ident, action, context, db)`.
fail-closed: any missing required context => 403 + structured refusal.

Roles (RBAC):
  student           – own documents only
  staff             – aggregated data for courses they teach
  programme_leader  – cross-course aggregated data for their programme(s)
  admin             – full audit/monitoring, no personal content
  career_coach      – (placeholder, same restrictions as staff)

Actions (what is being accessed):
  bff.staff.*          – staff BFF tier
  bff.programme.*      – programme BFF tier
  bff.admin.*          – admin BFF tier
  bff.student.*        – student BFF tier (handled by existing student logic)

ABAC conditions checked (minimum set per PPT Protocol 1):
  - faculty/programme/course/term scope matching
  - teaching_relation (staff can only see courses they teach)
  - purpose must be present and allowed
  - personal data fields are NEVER returned via staff/programme tier
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.refusal import make_refusal
from backend.app.security import Identity

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROLE_HIERARCHY: Dict[str, int] = {
    "student": 0,
    "career_coach": 1,
    "staff": 2,
    "programme_leader": 3,
    "admin": 4,
}

ALLOWED_PURPOSES_BY_ROLE: Dict[str, List[str]] = {
    "staff": ["teaching_support", "aggregate_programme_analysis"],
    "programme_leader": ["aggregate_programme_analysis"],
    "admin": ["system_audit", "system_monitoring", "onboarding"],
    "student": ["skill_assessment", "role_alignment", "portfolio"],
    "career_coach": ["teaching_support", "aggregate_programme_analysis"],
}

# Denylist: field names that must NEVER appear in staff/programme responses
PERSONAL_DATA_DENYLIST = {
    "subject_id", "user_id", "student_id",
    "chunk_text", "snippet", "stored_path", "storage_uri",
    "embedding", "raw_output",
}

# Actions that require admin role
ADMIN_ONLY_ACTIONS = {
    "bff.admin.audit.search",
    "bff.admin.change_log",
    "bff.admin.metrics",
    "bff.admin.onboarding",
    "bff.admin.users.assign_role",
    "bff.admin.users.assign_context",
    "bff.admin.skills.import",
    "bff.admin.roles.import",
    "bff.admin.resources.import",
    "bff.admin.health",
}

# Actions that require staff or above
STAFF_ACTIONS = {
    "bff.staff.courses",
    "bff.staff.courses.skills_summary",
    "bff.staff.courses.review_queue",
    "bff.staff.review.resolve",
    "bff.staff.skills.definitions",
    "bff.staff.audit.summary",
    "bff.staff.health",
}

# Actions that require programme_leader or above
PROGRAMME_ACTIONS = {
    "bff.programme.programmes",
    "bff.programme.coverage_matrix",
    "bff.programme.trend",
    "bff.programme.audit.summary",
    "bff.programme.health",
}


# ---------------------------------------------------------------------------
# Context dataclass
# ---------------------------------------------------------------------------

@dataclass
class AccessContext:
    """Caller-supplied ABAC context for the current request."""
    purpose: Optional[str] = None
    faculty_id: Optional[str] = None
    programme_id: Optional[str] = None
    course_id: Optional[str] = None
    term_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core policy enforcement
# ---------------------------------------------------------------------------

def require_access(
    ident: Identity,
    action: str,
    context: AccessContext,
    db: Optional[Session] = None,
) -> None:
    """
    Enforce RBAC + ABAC for a given action.

    Raises HTTPException(403) with structured refusal payload on any violation.
    Silently returns on success.

    Parameters
    ----------
    ident   – caller Identity (role, subject_id from verified token)
    action  – dot-notation action string, e.g. "bff.staff.courses.review_queue"
    context – ABAC context supplied by the BFF layer
    db      – SQLAlchemy session (required for teaching_relation checks)
    """
    role = ident.role

    # 1. Purpose check (fail-closed: all actions require a declared purpose)
    if not context.purpose:
        raise HTTPException(
            status_code=403,
            detail=make_refusal(
                "purpose_required",
                "Access denied: no purpose declared for this request.",
                "Include X-Purpose header or purpose parameter.",
            ),
        )

    allowed_purposes = ALLOWED_PURPOSES_BY_ROLE.get(role, [])
    if context.purpose not in allowed_purposes:
        raise HTTPException(
            status_code=403,
            detail=make_refusal(
                "purpose_mismatch",
                f"Purpose '{context.purpose}' is not permitted for role '{role}'.",
                f"Allowed purposes for your role: {allowed_purposes}",
            ),
        )

    # 2. RBAC: admin-only actions
    if action in ADMIN_ONLY_ACTIONS:
        if role != "admin":
            raise HTTPException(
                status_code=403,
                detail=make_refusal("role_insufficient",
                                    f"Action '{action}' requires admin role (you are '{role}')."),
            )
        return  # admin passes all further ABAC checks

    # 3. RBAC: programme-only actions
    if action in PROGRAMME_ACTIONS:
        if ROLE_HIERARCHY.get(role, -1) < ROLE_HIERARCHY["programme_leader"]:
            raise HTTPException(
                status_code=403,
                detail=make_refusal("role_insufficient",
                                    f"Action '{action}' requires programme_leader or admin role."),
            )
        # ABAC: programme_leader must have a programme_id in context or their binding
        if role == "programme_leader" and not context.programme_id and db is not None:
            bindings = _get_context_bindings(db, ident.subject_id)
            if not bindings.get("programme_id"):
                raise HTTPException(
                    status_code=403,
                    detail=make_refusal(
                        "context_missing",
                        "No programme context assigned. Contact your admin.",
                    ),
                )
        return

    # 4. RBAC: staff actions
    if action in STAFF_ACTIONS:
        if ROLE_HIERARCHY.get(role, -1) < ROLE_HIERARCHY["staff"]:
            raise HTTPException(
                status_code=403,
                detail=make_refusal("role_insufficient",
                                    f"Action '{action}' requires staff or admin role."),
            )
        # ABAC: teaching_relation check for course-scoped actions
        if context.course_id and db is not None and role == "staff":
            _require_teaching_relation(db, ident.subject_id, context.course_id, context.term_id)
        return

    # 5. Student actions (check role == student)
    if action.startswith("bff.student."):
        if role != "student":
            raise HTTPException(
                status_code=403,
                detail=make_refusal("role_insufficient",
                                    "Student endpoints require student role."),
            )
        return

    # 6. Unknown action – fail closed
    raise HTTPException(
        status_code=403,
        detail=make_refusal("action_unknown",
                            f"Action '{action}' is not in the access policy."),
    )


# ---------------------------------------------------------------------------
# ABAC helpers
# ---------------------------------------------------------------------------

def _get_context_bindings(db: Session, user_id: str) -> Dict[str, Any]:
    """Return the ABAC context bindings registered for this user."""
    row = db.execute(
        text("""
            SELECT faculty_id, programme_id, course_id, term_id
            FROM user_roles_context
            WHERE user_id = :uid
            ORDER BY created_at DESC LIMIT 1
        """),
        {"uid": user_id},
    ).mappings().first()
    return dict(row) if row else {}


def _require_teaching_relation(
    db: Session, user_id: str, course_id: str, term_id: Optional[str]
) -> None:
    """Raise 403 if user has no teaching relation for this course."""
    params: Dict[str, Any] = {"uid": user_id, "cid": course_id}
    sql = """
        SELECT 1 FROM teaching_relations
        WHERE user_id = :uid AND course_id = :cid
    """
    if term_id:
        sql += " AND (term_id = :tid OR term_id IS NULL)"
        params["tid"] = term_id

    row = db.execute(text(sql + " LIMIT 1"), params).first()
    if not row:
        raise HTTPException(
            status_code=403,
            detail=make_refusal(
                "teaching_relation_missing",
                f"You do not have a teaching relation for course '{course_id}'.",
                "Contact admin to assign teaching context.",
            ),
        )


def get_staff_courses(db: Session, user_id: str) -> List[str]:
    """Return list of course_ids where user has a teaching relation."""
    rows = db.execute(
        text("SELECT DISTINCT course_id FROM teaching_relations WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchall()
    return [r[0] for r in rows]


def get_programme_ids(db: Session, user_id: str) -> List[str]:
    """Return list of programme_ids assigned to this programme_leader."""
    rows = db.execute(
        text("""
            SELECT DISTINCT programme_id FROM user_roles_context
            WHERE user_id = :uid AND role = 'programme_leader' AND programme_id IS NOT NULL
        """),
        {"uid": user_id},
    ).fetchall()
    return [r[0] for r in rows]


def sanitise_response(data: Any) -> Any:
    """
    Strip any personal-data fields from a dict/list before returning.
    Call this on any data sourced from a non-student BFF tier.
    """
    if isinstance(data, dict):
        return {k: sanitise_response(v) for k, v in data.items() if k not in PERSONAL_DATA_DENYLIST}
    if isinstance(data, list):
        return [sanitise_response(item) for item in data]
    return data


def check_no_personal_leak(payload: Any) -> None:
    """
    Assert that no personal-data fields appear in payload.
    Raises AssertionError (for use in tests) if a denylist field is found.
    """
    if isinstance(payload, dict):
        for key in payload:
            assert key not in PERSONAL_DATA_DENYLIST, \
                f"Personal data field '{key}' must not appear in staff/programme response"
            check_no_personal_leak(payload[key])
    elif isinstance(payload, list):
        for item in payload:
            check_no_personal_leak(item)
