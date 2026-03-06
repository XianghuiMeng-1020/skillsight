"""
BFF – Admin Tier (Faculty/IT Admin)
Routes: /bff/admin/*

Access rules:
  - Bearer token required
  - Role must be 'admin' for ALL endpoints
  - Full audit/monitoring access
  - Onboarding: faculty/programme/course/term
  - User RBAC/ABAC management
  - Skill and role library management (proxied via this BFF)

Protocol 1 (RBAC+ABAC) + Protocol 8 (audit).
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.audit import log_audit
from backend.app.change_log_events import list_change_log_admin
from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.security import Identity, issue_token, require_auth, _is_dev_login_allowed
from backend.app.security.access_control import AccessContext, require_access

router = APIRouter(prefix="/bff/admin", tags=["bff-admin"])

_ADMIN_PURPOSE = "system_audit"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _assert_admin(ident: Identity) -> None:
    if ident.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "role_insufficient",
                "message": "Admin role required for this endpoint.",
                "next_step": "Log in with an admin account.",
            },
        )


# ─── Auth ─────────────────────────────────────────────────────────────────────

class AdminDevLoginReq(BaseModel):
    subject_id: str
    role: str = "admin"
    faculty_id: Optional[str] = None
    ttl_s: int = 3600


@router.post("/auth/dev_login")
def bff_admin_dev_login(payload: AdminDevLoginReq):
    """Issue admin token with faculty context (dev only)."""
    if not _is_dev_login_allowed():
        raise HTTPException(status_code=403, detail="dev_login disabled in production")
    if payload.role != "admin":
        raise HTTPException(status_code=422, detail="role must be 'admin'")
    token = issue_token(
        payload.subject_id,
        payload.role,
        payload.ttl_s,
        faculty_id=payload.faculty_id,
    )
    log_audit(engine, subject_id=payload.subject_id,
              action="bff.admin.auth.dev_login",
              object_type="auth", status="ok",
              detail={"role": payload.role})
    return {
        "token": token,
        "subject_id": payload.subject_id,
        "role": payload.role,
        "context": {"faculty_id": payload.faculty_id},
    }


# ─── Jobs (admin) ─────────────────────────────────────────────────────────────

@router.get("/jobs")
def bff_admin_jobs(
    status: Optional[str] = None,
    doc_id: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List background jobs with optional filters. Admin only."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.jobs", AccessContext(purpose=_ADMIN_PURPOSE), db)
    sql = "SELECT job_id, doc_id, job_type, status, attempts, last_error, created_at, updated_at FROM jobs WHERE 1=1"
    params: Dict[str, Any] = {"limit": min(limit, 500)}
    if status and status.strip():
        sql += " AND status = :status"
        params["status"] = status.strip()
    if doc_id and doc_id.strip():
        sql += " AND doc_id::text = :doc_id"
        params["doc_id"] = doc_id.strip()
    sql += " ORDER BY created_at DESC LIMIT :limit"
    rows = db.execute(text(sql), params).mappings().all()
    items = []
    for r in rows:
        items.append({
            "job_id": str(r["job_id"]),
            "doc_id": str(r["doc_id"]) if r.get("doc_id") else None,
            "job_type": r.get("job_type") or "embed",
            "status": r["status"],
            "attempts": int(r.get("attempts") or 0),
            "last_error": r.get("last_error"),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
        })
    return {"items": items, "count": len(items)}


@router.post("/jobs/{job_id}/retry")
def bff_admin_jobs_retry(
    job_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Reset job to pending and enqueue for retry. Admin only."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.jobs.retry", AccessContext(purpose=_ADMIN_PURPOSE), db)
    from backend.app.queue import enqueue_process_doc
    row = db.execute(
        text("SELECT job_id, doc_id FROM jobs WHERE job_id::text = :jid"),
        {"jid": job_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    doc_id = str(row["doc_id"])
    db.execute(
        text("UPDATE jobs SET status = 'pending', last_error = NULL, updated_at = :now WHERE job_id::text = :jid"),
        {"now": _now_utc(), "jid": job_id},
    )
    db.commit()
    rq_job_id = enqueue_process_doc(doc_id, job_id)
    return {
        "ok": True,
        "job_id": job_id,
        "doc_id": doc_id,
        "status": "pending",
        "rq_job_id": rq_job_id,
        "message": "Job reset and enqueued for retry" if rq_job_id else "Job reset but queue unavailable",
    }


# ─── Course–Skill Map (admin) ─────────────────────────────────────────────────

@router.get("/course-skill-map")
def bff_admin_course_skill_map(
    status: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List course_skill_map rows with optional status filter. Admin only."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.course_skill_map", AccessContext(purpose=_ADMIN_PURPOSE), db)
    sql = "SELECT map_id, course_id, skill_id, intended_level, evidence_type, status, note, created_at FROM course_skill_map WHERE 1=1"
    params: Dict[str, Any] = {"limit": min(limit, 500)}
    if status and status.strip():
        sql += " AND status = :status"
        params["status"] = status.strip()
    sql += " ORDER BY created_at DESC LIMIT :limit"
    rows = db.execute(text(sql), params).mappings().all()
    items = []
    for r in rows:
        items.append({
            "map_id": str(r["map_id"]),
            "course_id": r.get("course_id"),
            "skill_id": r.get("skill_id"),
            "intended_level": r.get("intended_level"),
            "evidence_type": r.get("evidence_type"),
            "status": r.get("status") or "pending",
            "note": r.get("note"),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })
    return {"items": items, "count": len(items)}


class CourseSkillMapActionReq(BaseModel):
    note: Optional[str] = None


@router.post("/course-skill-map/{map_id}/approve")
def bff_admin_course_skill_map_approve(
    map_id: str,
    payload: CourseSkillMapActionReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Approve a course-skill mapping. Admin only."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.course_skill_map.approve", AccessContext(purpose=_ADMIN_PURPOSE), db)
    n = db.execute(
        text("UPDATE course_skill_map SET status = 'approved', note = COALESCE(:note, note), updated_at = :now WHERE map_id::text = :mid"),
        {"note": payload.note, "now": _now_utc(), "mid": map_id},
    ).rowcount
    db.commit()
    if n == 0:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"ok": True, "map_id": map_id, "status": "approved"}


@router.post("/course-skill-map/{map_id}/reject")
def bff_admin_course_skill_map_reject(
    map_id: str,
    payload: CourseSkillMapActionReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Reject a course-skill mapping. Admin only."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.course_skill_map.reject", AccessContext(purpose=_ADMIN_PURPOSE), db)
    n = db.execute(
        text("UPDATE course_skill_map SET status = 'rejected', note = COALESCE(:note, note), updated_at = :now WHERE map_id::text = :mid"),
        {"note": payload.note, "now": _now_utc(), "mid": map_id},
    ).rowcount
    db.commit()
    if n == 0:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"ok": True, "map_id": map_id, "status": "rejected"}


# ─── Skill aliases / conflicts (admin) ───────────────────────────────────────

@router.get("/skill-aliases/conflicts")
def bff_admin_skill_aliases_conflicts(
    limit: int = 200,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List alias conflicts: aliases that map to more than one skill. Admin only."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.skill_aliases", AccessContext(purpose=_ADMIN_PURPOSE), db)
    rows = db.execute(
        text("""
            SELECT alias, COUNT(DISTINCT skill_id) AS n_skills,
                   array_agg(DISTINCT skill_id) AS skill_ids
            FROM skill_aliases
            WHERE status = 'active'
            GROUP BY alias
            HAVING COUNT(DISTINCT skill_id) > 1
            ORDER BY n_skills DESC
            LIMIT :lim
        """),
        {"lim": min(limit, 500)},
    ).mappings().all()
    items = []
    for r in rows:
        skill_ids = r.get("skill_ids") or []
        if hasattr(skill_ids, "tolist"):
            skill_ids = skill_ids.tolist()
        items.append({
            "alias": r["alias"],
            "n_skills": int(r.get("n_skills") or 0),
            "skill_ids": list(skill_ids),
        })
    return {"items": items, "count": len(items)}


@router.get("/skill-aliases/resolve")
def bff_admin_skill_aliases_resolve(
    alias: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Resolve an alias to canonical skill(s). Admin only."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.skill_aliases", AccessContext(purpose=_ADMIN_PURPOSE), db)
    rows = db.execute(
        text("""
            SELECT skill_id, alias, status FROM skill_aliases
            WHERE alias = :alias AND status = 'active'
            ORDER BY skill_id
        """),
        {"alias": alias.strip()},
    ).mappings().all()
    if not rows:
        return {"alias": alias, "found": False, "skills": []}
    skills = [{"skill_id": r["skill_id"], "alias": r["alias"], "status": r["status"]} for r in rows]
    return {"alias": alias, "found": True, "skills": skills, "canonical_skill_id": skills[0]["skill_id"] if len(skills) == 1 else None}


@router.get("/skill-aliases/conflicts/report")
def bff_admin_skill_aliases_conflicts_report(
    format: Optional[str] = None,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Download conflicts as CSV. Admin only."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.skill_aliases", AccessContext(purpose=_ADMIN_PURPOSE), db)
    rows = db.execute(
        text("""
            SELECT alias, COUNT(DISTINCT skill_id) AS n_skills,
                   array_agg(DISTINCT skill_id) AS skill_ids
            FROM skill_aliases WHERE status = 'active'
            GROUP BY alias HAVING COUNT(DISTINCT skill_id) > 1
            ORDER BY n_skills DESC
        """)
    ).mappings().all()
    if (format or "").strip().lower() == "csv":
        import io
        buf = io.StringIO()
        buf.write("alias,n_skills,skill_ids\n")
        for r in rows:
            skill_ids = r.get("skill_ids") or []
            if hasattr(skill_ids, "tolist"):
                skill_ids = skill_ids.tolist()
            buf.write(f"{r['alias']!r},{r.get('n_skills') or 0},{','.join(map(str, skill_ids))}\n")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=buf.getvalue(), media_type="text/csv")
    return {"items": [{"alias": r["alias"], "n_skills": int(r.get("n_skills") or 0), "skill_ids": list(r.get("skill_ids") or [])} for r in rows], "count": len(rows)}


# ─── Onboarding ───────────────────────────────────────────────────────────────

class FacultyReq(BaseModel):
    faculty_id: str
    name: str


@router.post("/onboarding/faculty")
def bff_admin_create_faculty(
    payload: FacultyReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Create a faculty entity."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.onboarding", AccessContext(purpose="onboarding"), db)

    db.execute(
        text("INSERT INTO faculties (faculty_id, name, created_at) VALUES (:fid, :name, :now) ON CONFLICT (faculty_id) DO UPDATE SET name = EXCLUDED.name"),
        {"fid": payload.faculty_id, "name": payload.name, "now": _now_utc()},
    )
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.onboarding.faculty",
              object_type="faculty", object_id=payload.faculty_id, status="ok")
    return {"ok": True, "faculty_id": payload.faculty_id, "name": payload.name}


class ProgrammeReq(BaseModel):
    programme_id: str
    name: str
    faculty_id: str


@router.post("/onboarding/programme")
def bff_admin_create_programme(
    payload: ProgrammeReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Create a programme linked to a faculty."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.onboarding", AccessContext(purpose="onboarding"), db)

    db.execute(
        text("""
            INSERT INTO programmes (programme_id, name, faculty_id, created_at)
            VALUES (:pid, :name, :fid, :now)
            ON CONFLICT (programme_id) DO UPDATE SET name = EXCLUDED.name, faculty_id = EXCLUDED.faculty_id
        """),
        {"pid": payload.programme_id, "name": payload.name, "fid": payload.faculty_id, "now": _now_utc()},
    )
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.onboarding.programme",
              object_type="programme", object_id=payload.programme_id, status="ok")
    return {"ok": True, "programme_id": payload.programme_id, "name": payload.name}


class CourseOnboardReq(BaseModel):
    course_id: str
    course_name: str
    description: Optional[str] = None
    programme_id: Optional[str] = None
    faculty_id: Optional[str] = None
    term_id: Optional[str] = None


@router.post("/onboarding/course")
def bff_admin_create_course(
    payload: CourseOnboardReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Create or update a course."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.onboarding", AccessContext(purpose="onboarding"), db)

    db.execute(
        text("""
            INSERT INTO courses (course_id, course_code, title, description, programme_id, faculty_id, term_id)
            VALUES (:cid, :ccode, :title, :desc, :pid, :fid, :tid)
            ON CONFLICT (course_id) DO UPDATE
            SET course_code = EXCLUDED.course_code,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                programme_id = EXCLUDED.programme_id,
                faculty_id = EXCLUDED.faculty_id,
                term_id = EXCLUDED.term_id
        """),
        {
            "cid": payload.course_id, "ccode": payload.course_id, "title": payload.course_name,
            "desc": payload.description, "pid": payload.programme_id,
            "fid": payload.faculty_id, "tid": payload.term_id,
        },
    )
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.onboarding.course",
              object_type="course", object_id=payload.course_id, status="ok")
    return {"ok": True, "course_id": payload.course_id, "course_name": payload.course_name}


class TermReq(BaseModel):
    term_id: str
    label: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.post("/onboarding/term")
def bff_admin_create_term(
    payload: TermReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Create a term."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.onboarding", AccessContext(purpose="onboarding"), db)

    db.execute(
        text("""
            INSERT INTO terms (term_id, label, start_date, end_date, created_at)
            VALUES (:tid, :label, :sd, :ed, :now)
            ON CONFLICT (term_id) DO UPDATE SET label = EXCLUDED.label
        """),
        {"tid": payload.term_id, "label": payload.label,
         "sd": payload.start_date, "ed": payload.end_date, "now": _now_utc()},
    )
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.onboarding.term",
              object_type="term", object_id=payload.term_id, status="ok")
    return {"ok": True, "term_id": payload.term_id, "label": payload.label}


# ─── User Role / Context Management ──────────────────────────────────────────

class AssignRoleReq(BaseModel):
    user_id: str
    role: str  # student|staff|programme_leader|admin|career_coach


@router.post("/users/assign_role")
def bff_admin_assign_role(
    payload: AssignRoleReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Assign an RBAC role to a user."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.users.assign_role", AccessContext(purpose="onboarding"), db)

    allowed_roles = {"student", "staff", "programme_leader", "admin", "career_coach"}
    if payload.role not in allowed_roles:
        raise HTTPException(status_code=422,
                            detail=f"role must be one of: {sorted(allowed_roles)}")

    db.execute(
        text("""
            INSERT INTO user_roles_context (id, user_id, role, granted_by, created_at)
            VALUES (gen_random_uuid(), :uid, :role, :grantor, :now)
        """),
        {"uid": payload.user_id, "role": payload.role,
         "grantor": ident.subject_id, "now": _now_utc()},
    )
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.users.assign_role",
              object_type="user", object_id=payload.user_id, status="ok",
              detail={"role": payload.role})
    return {"ok": True, "user_id": payload.user_id, "role": payload.role}


class AssignContextReq(BaseModel):
    user_id: str
    role: str
    faculty_id: Optional[str] = None
    programme_id: Optional[str] = None
    course_id: Optional[str] = None
    term_id: Optional[str] = None


@router.post("/users/assign_context")
def bff_admin_assign_context(
    payload: AssignContextReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Assign ABAC context (faculty/programme/course/term) to a user."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.users.assign_context", AccessContext(purpose="onboarding"), db)

    db.execute(
        text("""
            INSERT INTO user_roles_context
              (id, user_id, role, faculty_id, programme_id, course_id, term_id, granted_by, created_at)
            VALUES
              (gen_random_uuid(), :uid, :role, :fid, :pid, :cid, :tid, :grantor, :now)
        """),
        {
            "uid": payload.user_id, "role": payload.role,
            "fid": payload.faculty_id, "pid": payload.programme_id,
            "cid": payload.course_id, "tid": payload.term_id,
            "grantor": ident.subject_id, "now": _now_utc(),
        },
    )
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.users.assign_context",
              object_type="user", object_id=payload.user_id, status="ok",
              detail={
                  "faculty_id": payload.faculty_id,
                  "programme_id": payload.programme_id,
                  "course_id": payload.course_id,
                  "term_id": payload.term_id,
              })
    return {"ok": True, "user_id": payload.user_id, "context_bound": True}


# ─── Teaching Relations ───────────────────────────────────────────────────────

class TeachingRelationReq(BaseModel):
    user_id: str
    course_id: str
    term_id: Optional[str] = None
    role: str = "instructor"


@router.post("/users/teaching_relation")
def bff_admin_teaching_relation(
    payload: TeachingRelationReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Assign a teaching relation (for staff ABAC checks)."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.users.assign_context", AccessContext(purpose="onboarding"), db)

    db.execute(
        text("""
            INSERT INTO teaching_relations (user_id, course_id, term_id, role, created_at)
            VALUES (:uid, :cid, :tid, :role, :now)
            ON CONFLICT (user_id, course_id, term_id) DO UPDATE SET role = EXCLUDED.role
        """),
        {"uid": payload.user_id, "cid": payload.course_id,
         "tid": payload.term_id, "role": payload.role, "now": _now_utc()},
    )
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.users.teaching_relation",
              object_type="user", object_id=payload.user_id, status="ok",
              detail={"course_id": payload.course_id, "term_id": payload.term_id})
    return {"ok": True, "user_id": payload.user_id, "course_id": payload.course_id}


# ─── Skills & Roles management ────────────────────────────────────────────────

@router.get("/skills")
def bff_admin_list_skills(
    limit: int = 100,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List all skill definitions (admin can see everything)."""
    _assert_admin(ident)
    rows = db.execute(
        text("SELECT skill_id, canonical_name, definition FROM skills ORDER BY canonical_name LIMIT :lim"),
        {"lim": min(limit, 500)},
    ).mappings().all()
    return {"count": len(rows), "skills": [dict(r) for r in rows]}


class SkillImportItem(BaseModel):
    skill_id: str
    canonical_name: str
    definition: Optional[str] = None


class SkillsImportReq(BaseModel):
    skills: List[SkillImportItem]


@router.post("/skills/import")
def bff_admin_import_skills(
    payload: SkillsImportReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Bulk import skill definitions (admin only)."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.skills.import", AccessContext(purpose="onboarding"), db)

    imported = 0
    for s in payload.skills:
        db.execute(
            text("""
                INSERT INTO skills (skill_id, canonical_name, definition)
                VALUES (:sid, :name, :def)
                ON CONFLICT (skill_id) DO UPDATE
                SET canonical_name = EXCLUDED.canonical_name,
                    definition = EXCLUDED.definition
            """),
            {"sid": s.skill_id, "name": s.canonical_name, "def": s.definition},
        )
        imported += 1
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.skills.import",
              object_type="skills", status="ok",
              detail={"imported_count": imported})
    return {"ok": True, "imported": imported}


@router.get("/roles")
def bff_admin_list_roles(
    limit: int = 100,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List all vetted roles (admin only)."""
    _assert_admin(ident)
    rows = db.execute(
        text("SELECT role_id, role_title, description FROM roles ORDER BY role_title LIMIT :lim"),
        {"lim": min(limit, 500)},
    ).mappings().all()
    return {"count": len(rows), "roles": [dict(r) for r in rows]}


class RoleImportItem(BaseModel):
    role_id: str
    role_title: str
    description: Optional[str] = None
    skills_required: Optional[Dict[str, Any]] = None


class RolesImportReq(BaseModel):
    roles: List[RoleImportItem]


@router.post("/roles/import")
def bff_admin_import_roles(
    payload: RolesImportReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Bulk import role definitions (admin only)."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.roles.import", AccessContext(purpose="onboarding"), db)

    imported = 0
    for r in payload.roles:
        db.execute(
            text("""
                INSERT INTO roles (role_id, role_title, description, skills_required)
                VALUES (:rid, :title, :desc, (:skills)::jsonb)
                ON CONFLICT (role_id) DO UPDATE
                SET role_title = EXCLUDED.role_title,
                    description = EXCLUDED.description,
                    skills_required = EXCLUDED.skills_required
            """),
            {
                "rid": r.role_id,
                "title": r.role_title,
                "desc": r.description,
                "skills": json.dumps(r.skills_required or {}),
            },
        )
        imported += 1
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.roles.import",
              object_type="roles", status="ok",
              detail={"imported_count": imported})
    return {"ok": True, "imported": imported}


# ─── Learning Resources (P5 Decision 5) ───────────────────────────────────────

class ResourceImportItem(BaseModel):
    title: str
    resource_type: str = "course"
    location: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    gap_type: Optional[str] = None
    skill_ids: List[str] = []


class ResourcesImportReq(BaseModel):
    resources: List[ResourceImportItem]


@router.post("/resources/import")
def bff_admin_import_resources(
    payload: ResourcesImportReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """P5: Bulk import learning resources (admin only)."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.resources.import", AccessContext(purpose="onboarding"), db)

    imported = 0
    for r in payload.resources:
        rid = str(uuid.uuid4())
        db.execute(
            text("""
                INSERT INTO learning_resources
                (resource_id, title, resource_type, location, url, description, gap_type)
                VALUES (:rid, :title, :rtype, :loc, :url, :desc, :gap)
            """),
            {
                "rid": rid,
                "title": r.title,
                "rtype": r.resource_type,
                "loc": r.location,
                "url": r.url,
                "desc": r.description,
                "gap": r.gap_type,
            },
        )
        for sid in r.skill_ids:
            db.execute(
                text("""
                    INSERT INTO resource_skill_map (resource_id, skill_id, gap_type)
                    VALUES (:rid, :sid, :gap)
                """),
                {"rid": rid, "sid": sid, "gap": r.gap_type},
            )
        imported += 1
    db.commit()

    log_audit(engine, subject_id=ident.subject_id,
              action="bff.admin.resources.import",
              object_type="learning_resources", status="ok",
              detail={"imported_count": imported})
    return {"ok": True, "imported": imported}


# ─── Audit Search ─────────────────────────────────────────────────────────────

@router.get("/audit/search")
def bff_admin_audit_search(
    action: Optional[str] = None,
    status: Optional[str] = None,
    request_id: Optional[str] = None,
    subject_id_filter: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Search audit logs with filters.
    Admin only. Returns full audit records.
    """
    _assert_admin(ident)
    require_access(ident, "bff.admin.audit.search", AccessContext(purpose=_ADMIN_PURPOSE), db)

    conditions = []
    params: Dict[str, Any] = {"lim": min(limit, 500)}

    if action:
        conditions.append("action ILIKE :action")
        params["action"] = f"%{action}%"
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if request_id:
        conditions.append("request_id = :rid")
        params["rid"] = request_id
    if subject_id_filter:
        conditions.append("subject_id = :sub")
        params["sub"] = subject_id_filter
    if since:
        conditions.append("created_at >= :since")
        params["since"] = since
    if until:
        conditions.append("created_at <= :until")
        params["until"] = until

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT audit_id, request_id, subject_id, action, object_type, object_id,
               status, error, detail, created_at
        FROM audit_logs
        {where}
        ORDER BY created_at DESC
        LIMIT :lim
    """

    rows = db.execute(text(sql), params).mappings().all()
    return {
        "count": len(rows),
        "items": [
            {
                **{k: v for k, v in r.items() if k not in ("detail",)},
                "audit_id": str(r["audit_id"]),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "detail": r.get("detail") or {},
            }
            for r in rows
        ],
    }


# ─── Change Log Search (P4 Protocol 5) ────────────────────────────────────────

@router.get("/change_log/search")
def bff_admin_change_log_search(
    subject_id: Optional[str] = None,
    event_type: Optional[str] = None,
    request_id: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Search change_log_events. Admin only. Denylist applied to staff/programme scopes."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.change_log", AccessContext(purpose=_ADMIN_PURPOSE), db)
    log_audit(engine, subject_id=ident.subject_id, action="bff.admin.change_log.search",
              object_type="change_log", status="ok", detail={"filters": {"subject_id": subject_id, "event_type": event_type}})
    return list_change_log_admin(
        engine,
        subject_id=subject_id,
        event_type=event_type,
        request_id=request_id,
        since=since,
        until=until,
        limit=limit,
        cursor=cursor,
        scope="admin",
    )


# ─── Metrics ─────────────────────────────────────────────────────────────────

@router.get("/metrics/usage")
def bff_admin_metrics_usage(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Usage metrics aggregated from audit_logs."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.metrics", AccessContext(purpose=_ADMIN_PURPOSE), db)

    daily = db.execute(
        text("""
            SELECT
                DATE(created_at) AS day,
                action,
                COUNT(*) AS request_count
            FROM audit_logs
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(created_at), action
            ORDER BY day DESC, request_count DESC
        """)
    ).mappings().all()

    totals = db.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'ok')    AS ok_count,
                COUNT(*) FILTER (WHERE status = 'error') AS error_count,
                COUNT(DISTINCT subject_id)               AS unique_users
            FROM audit_logs
            WHERE created_at >= NOW() - INTERVAL '30 days'
        """)
    ).mappings().first()

    return {
        "period": "last_30_days",
        "totals": {
            "total_requests": int(totals["total"] or 0),
            "ok": int(totals["ok_count"] or 0),
            "errors": int(totals["error_count"] or 0),
            "unique_users": int(totals["unique_users"] or 0),
        },
        "daily_breakdown": [
            {
                "day": str(r["day"]),
                "action": r["action"],
                "count": int(r["request_count"]),
            }
            for r in daily
        ],
    }


@router.get("/metrics/reliability")
def bff_admin_metrics_reliability(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Reliability metrics (error rates per action) from audit_logs."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.metrics", AccessContext(purpose=_ADMIN_PURPOSE), db)

    rows = db.execute(
        text("""
            SELECT
                action,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'ok')    AS ok_count,
                COUNT(*) FILTER (WHERE status = 'error') AS error_count
            FROM audit_logs
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY action
            ORDER BY total DESC
        """)
    ).mappings().all()

    return {
        "period": "last_7_days",
        "reliability_by_action": [
            {
                "action": r["action"],
                "total": int(r["total"]),
                "ok": int(r["ok_count"] or 0),
                "errors": int(r["error_count"] or 0),
                "error_rate_pct": round(
                    100 * int(r["error_count"] or 0) / max(int(r["total"]), 1), 1
                ),
            }
            for r in rows
        ],
    }


# ─── System Health ────────────────────────────────────────────────────────────

@router.get("/health")
def bff_admin_health(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Full system health for admin monitoring."""
    _assert_admin(ident)
    require_access(ident, "bff.admin.health", AccessContext(purpose=_ADMIN_PURPOSE), db)

    from backend.app.vector_store import qdrant_health
    qdrant = qdrant_health()

    doc_count = db.execute(text("SELECT COUNT(*) FROM documents")).scalar() or 0
    chunk_count = db.execute(text("SELECT COUNT(*) FROM chunks")).scalar() or 0
    consent_count = db.execute(
        text("SELECT COUNT(*) FROM consents WHERE status = 'granted'")
    ).scalar() or 0
    open_tickets = db.execute(
        text("SELECT COUNT(*) FROM review_tickets WHERE status = 'open'")
    ).scalar() or 0
    total_users = db.execute(
        text("SELECT COUNT(DISTINCT user_id) FROM user_roles_context")
    ).scalar() or 0

    return {
        "status": "ok",
        "db": "ok",
        "qdrant": qdrant,
        "stats": {
            "documents": int(doc_count),
            "chunks": int(chunk_count),
            "active_consents": int(consent_count),
            "open_review_tickets": int(open_tickets),
            "registered_users": int(total_users),
        },
        "checked_at": _now_utc().isoformat(),
    }


# ─── Legacy endpoints (backward compat) ──────────────────────────────────────

@router.get("/audit/recent")
def bff_admin_audit_recent(
    limit: int = 50,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Recent audit logs (alias for /audit/search with no filters)."""
    return bff_admin_audit_search(limit=limit, db=db, ident=ident)


@router.get("/consents/overview")
def bff_admin_consents_overview(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Consent status overview."""
    _assert_admin(ident)
    rows = db.execute(
        text("SELECT status, COUNT(*) AS n FROM consents GROUP BY status ORDER BY status")
    ).mappings().all()
    return {"consents_by_status": [{"status": r["status"], "count": int(r["n"])} for r in rows]}


@router.get("/system/health")
def bff_admin_system_health(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Alias for /health."""
    return bff_admin_health(db=db, ident=ident)
