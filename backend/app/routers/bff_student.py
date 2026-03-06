"""
BFF (Backend for Frontend) – Student Tier
Routes: /bff/student/*

All student requests must:
  1. Be authenticated (require_auth)
  2. Declare consent purpose + scope at upload time
  3. Have active consent before embed / search / assess
  4. Carry request_id through the audit trail
  5. Return structured refusal hints when evidence is insufficient
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.audit import log_audit
from backend.app.refusal import make_refusal, normalize_legacy_refusal, refusal_dict
from backend.app.change_log_events import (
    get_prev_role_readiness_snapshot,
    get_prev_skill_snapshot,
    list_change_log_student,
    write_change_event,
    write_role_readiness_snapshot,
    write_skill_snapshot,
    _build_evidence_pointer,
)
from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.security import Identity, issue_token, require_auth

router = APIRouter(prefix="/bff/student", tags=["bff-student"])

ALLOWED_PURPOSES = ["skill_assessment", "role_alignment", "portfolio"]
ALLOWED_SCOPES = ["full", "excerpt", "summary"]

_BASE = os.getenv("BFF_BACKEND_URL") or f"http://127.0.0.1:{os.getenv('PORT', '8001')}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _check_consent(db: Session, doc_id: str, subject_id: str) -> None:
    """Raise 403 with structured refusal hint if no active consent."""
    row = db.execute(
        text("""
            SELECT status FROM consents
            WHERE doc_id = :doc_id AND user_id = :sub
            ORDER BY created_at DESC LIMIT 1
        """),
        {"doc_id": doc_id, "sub": subject_id},
    ).mappings().first()
    if not row:
        raise HTTPException(
            status_code=403,
            detail=make_refusal(
                "consent_required",
                "No consent record found for this document.",
                "Upload the document with a valid purpose and scope first.",
            ),
        )
    if row["status"] != "granted":
        raise HTTPException(
            status_code=403,
            detail=make_refusal(
                "consent_revoked",
                f"Consent for this document is '{row['status']}'. Access denied.",
                "Re-upload with consent, or restore it via the consent management page.",
            ),
        )


def _table_columns(db: Session, table_name: str) -> List[str]:
    rows = db.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table_name
    """), {"table_name": table_name}).mappings().all()
    return [str(r["column_name"]) for r in rows]


# ─── Auth ─────────────────────────────────────────────────────────────────────

class DevLoginReq(BaseModel):
    subject_id: str
    role: str = "student"
    ttl_s: int = 3600


@router.post("/auth/dev_login")
async def bff_dev_login(payload: DevLoginReq):
    """BFF proxy to /auth/dev_login (dev / test only)."""
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.post(f"{_BASE}/auth/dev_login", json=payload.model_dump(), timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.json())
    return r.json()


# ─── Document List (consent-scoped) ────────────────────────────────────────────

@router.get("/documents")
def bff_list_documents(
    limit: int = 10,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List documents for this student (with granted consent only)."""
    rows = db.execute(
        text("""
            SELECT d.doc_id, d.filename, d.doc_type, d.created_at
            FROM documents d
            JOIN consents c ON c.doc_id = d.doc_id::text
            WHERE c.user_id = :sub AND c.status = 'granted'
            ORDER BY d.created_at DESC
            LIMIT :lim
        """),
        {"sub": ident.subject_id, "lim": min(limit, 50)},
    ).mappings().all()

    items = [
        {
            "doc_id": r["doc_id"],
            "filename": r["filename"],
            "doc_type": r.get("doc_type"),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]

    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.student.documents.list",
        object_type="documents",
        status="ok",
        detail={"count": len(items)},
    )
    return {"items": items, "count": len(items)}


# ─── Skills (read-only registry via BFF) ───────────────────────────────────────

@router.get("/skills")
async def bff_list_skills(
    limit: int = 10,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Proxy to skill registry (read-only)."""
    internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.get(f"{_BASE}/skills?limit={min(limit, 100)}", headers={"Authorization": f"Bearer {internal_token}"}, timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    data = r.json()
    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.student.skills.list",
        object_type="skills",
        status="ok",
    )
    return data


# ─── Roles (read-only role library via BFF) ────────────────────────────────────

@router.get("/roles")
async def bff_list_roles(
    limit: int = 20,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Proxy to role library (read-only)."""
    internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.get(f"{_BASE}/roles?limit={min(limit, 100)}", headers={"Authorization": f"Bearer {internal_token}"}, timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    data = r.json()
    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.student.roles.list",
        object_type="roles",
        status="ok",
    )
    return data


# ─── Document Upload with consent enforcement ─────────────────────────────────

@router.post("/documents/upload")
async def bff_upload_document(
    file: UploadFile = File(...),
    purpose: str = Form(...),
    scope: str = Form(...),
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Upload a document with mandatory consent purpose + scope.

    - purpose: one of skill_assessment / role_alignment / portfolio
    - scope:   one of full / excerpt / summary

    Returns 422 when purpose or scope are missing / invalid.
    """
    if purpose not in ALLOWED_PURPOSES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_consent_purpose",
                "message": f"Purpose '{purpose}' is not allowed.",
                "allowed_purposes": ALLOWED_PURPOSES,
                "next_step": "Select a valid purpose before uploading.",
            },
        )
    if scope not in ALLOWED_SCOPES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_consent_scope",
                "message": f"Scope '{scope}' is not allowed.",
                "allowed_scopes": ALLOWED_SCOPES,
                "next_step": "Select a valid scope before uploading.",
            },
        )

    file_bytes = await file.read()
    # Forward a short-lived bearer token for internal API call that enforces auth.
    internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.post(
            f"{_BASE}/documents/upload_multimodal"
            f"?user_id={ident.subject_id}&consent=true",
            files={"file": (file.filename, file_bytes, file.content_type or "application/octet-stream")},
            headers={"Authorization": f"Bearer {internal_token}"},
            timeout=120,
        )
    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise HTTPException(status_code=r.status_code, detail=err.get("detail", r.text))

    data = r.json()
    doc_id = data.get("doc_id")

    if doc_id:
        consent_id = str(uuid.uuid4())
        db.execute(
            text("""
                INSERT INTO consents
                  (consent_id, user_id, doc_id, status, created_at)
                VALUES
                  (:cid, :sub, :doc_id, 'granted', :now)
                ON CONFLICT DO NOTHING
            """),
            {
                "cid": consent_id,
                "sub": ident.subject_id,
                "doc_id": doc_id,
                "now": _now_utc(),
            },
        )
        db.commit()
        log_audit(
            engine,
            subject_id=ident.subject_id,
            action="bff.documents.upload",
            object_type="document",
            object_id=doc_id,
            status="ok",
            detail={"purpose": purpose, "scope": scope, "filename": file.filename},
        )

    return {**data, "purpose": purpose, "scope": scope, "consent_status": "granted"}


# ─── Embed ────────────────────────────────────────────────────────────────────

@router.post("/chunks/embed/{doc_id}")
async def bff_embed(
    doc_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Embed chunks for a document. Requires active consent."""
    _check_consent(db, doc_id, ident.subject_id)

    internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.post(
            f"{_BASE}/chunks/embed/{doc_id}",
            headers={"Authorization": f"Bearer {internal_token}"},
            timeout=120,
        )
    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise HTTPException(status_code=r.status_code, detail=err.get("detail", r.text))

    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.chunks.embed",
        object_type="document",
        object_id=doc_id,
        status="ok",
    )
    return r.json()


# ─── Evidence Search ──────────────────────────────────────────────────────────

class EvidenceSearchReq(BaseModel):
    query_text: Optional[str] = None
    skill_id: Optional[str] = None
    doc_id: Optional[str] = None
    k: int = 5
    min_score: float = 0.0


@router.post("/search/evidence_vector")
async def bff_search_evidence(
    payload: EvidenceSearchReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Vector search via retrieval_pipeline. Consent check when doc_id provided.
    Decision 1: refusal from pipeline (threshold) -> items=[], refusal={code, message, next_step}.
    Audit: bff.student.search.evidence_vector (refusal or ok).
    """
    if payload.doc_id:
        _check_consent(db, payload.doc_id, ident.subject_id)

    internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.post(
            f"{_BASE}/search/evidence_vector",
            json=payload.model_dump(),
            headers={"Authorization": f"Bearer {internal_token}"},
            timeout=30,
        )
    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise HTTPException(status_code=r.status_code, detail=err.get("detail", r.text))

    result = r.json()
    items = result.get("items", [])
    refusal = result.get("refusal")

    # When items empty, ensure refusal has canonical {code, message, next_step} (Decision 1 / script gate)
    if not items:
        normalized = normalize_legacy_refusal(refusal) if refusal and isinstance(refusal, dict) else None
        if not normalized:
            result["refusal"] = refusal_dict(
                "no_matching_evidence",
                "No matching evidence found for your query.",
                "Upload more evidence documents, or try a broader search query. "
                "Make sure chunks are embedded before searching.",
            )
        else:
            if not normalized.get("code"):
                normalized["code"] = "evidence_below_threshold_pre"
            result["refusal"] = refusal_dict(
                normalized["code"],
                normalized.get("message") or "No results above threshold.",
                normalized.get("next_step") or "Upload more relevant evidence or refine your query.",
            )

    # Re-read normalized refusal to avoid non-dict `.get()` failures in audit logging
    refusal = result.get("refusal")

    # Audit (refusal still 200 OK per protocol; status reflects outcome)
    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.student.search.evidence_vector",
        object_type="search",
        status="refusal" if (refusal or not items) else "ok",
        detail={
            "items_count": len(items),
            "refusal_code": refusal.get("code") if isinstance(refusal, dict) else None,
        },
    )
    return result


# ─── AI Demonstration (P4: persistence + change log) ──────────────────────────

class DemonstrationReq(BaseModel):
    skill_id: str
    doc_id: str
    k: int = 5


@router.post("/ai/demonstration")
async def bff_ai_demonstration(
    payload: DemonstrationReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    BFF proxy to /ai/demonstration with persistence and change log.
    - Requires consent for doc_id
    - Persists result to skill_assessments
    - Writes skill_assessment_snapshot + change_log_event when label/evidence changes
    """
    _check_consent(db, payload.doc_id, ident.subject_id)

    internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.post(
            f"{_BASE}/ai/demonstration",
            json={"skill_id": payload.skill_id, "doc_id": payload.doc_id, "k": payload.k},
            headers={"Authorization": f"Bearer {internal_token}"},
            timeout=120,
        )
    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise HTTPException(status_code=r.status_code, detail=err.get("detail", r.text))

    result = r.json()
    label = result.get("label", "not_enough_information")
    rationale = result.get("rationale", "")
    evidence_ids = result.get("evidence_chunk_ids") or []
    model_info = {"model": result.get("model", "")}

    # Build evidence pointers (snippet <= 300 chars, no chunk_text/stored_path)
    pointers: List[Dict[str, Any]] = []
    for cid in evidence_ids[:10]:
        chunk_row = db.execute(
            text("SELECT chunk_id, doc_id, char_start, char_end, quote_hash, snippet FROM chunks WHERE chunk_id = :cid LIMIT 1"),
            {"cid": cid},
        ).mappings().first()
        if chunk_row:
            pointers.append(_build_evidence_pointer(
                doc_id=str(chunk_row["doc_id"]),
                chunk_id=str(chunk_row["chunk_id"]),
                snippet=(chunk_row.get("snippet") or "")[:300],
                char_start=chunk_row.get("char_start"),
                char_end=chunk_row.get("char_end"),
                quote_hash=chunk_row.get("quote_hash"),
            ))

    request_id = str(uuid.uuid4())

    # Persist to skill_assessments (decision=label, evidence=pointers)
    try:
        ass_id = str(uuid.uuid4())
        db.execute(
            text("""
                INSERT INTO skill_assessments (assessment_id, doc_id, skill_id, decision, evidence, decision_meta, created_at)
                VALUES (:aid, :doc_id, :skill_id, :decision, (:ev)::jsonb, (:meta)::jsonb, :now)
            """),
            {
                "aid": ass_id,
                "doc_id": payload.doc_id,
                "skill_id": payload.skill_id,
                "decision": label,
                "ev": json.dumps([{"chunk_id": p["chunk_id"], "snippet": p.get("snippet", "")[:300]} for p in pointers]),
                "meta": json.dumps({"source": "bff_ai_demonstration", "request_id": request_id, "rationale": rationale}),
                "now": _now_utc(),
            },
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to persist assessment: {e}")

    # Compare with prev BEFORE writing new snapshot
    prev = get_prev_skill_snapshot(engine, ident.subject_id, payload.skill_id)
    prev_label = None
    prev_ptrs = []
    if prev:
        prev_label = prev.get("label")
        prev_ptrs = prev.get("evidence") or []
        if isinstance(prev_ptrs, str):
            try:
                prev_ptrs = json.loads(prev_ptrs)
            except Exception:
                prev_ptrs = []
    ptr_ids = {p.get("chunk_id") for p in pointers}
    prev_ids = {p.get("chunk_id") for p in prev_ptrs if isinstance(p, dict)}
    has_change = prev_label != label or ptr_ids != prev_ids

    # Write snapshot always (audit trail)
    write_skill_snapshot(
        engine, ident.subject_id, payload.skill_id, label,
        rationale=rationale, evidence=pointers, request_id=request_id, model_info=model_info,
    )
    if has_change:
        write_change_event(
            engine,
            scope="student",
            event_type="skill_changed",
            subject_id=ident.subject_id,
            entity_key=payload.skill_id,
            before_state={"label": prev_label, "evidence_chunk_ids": list(prev_ids)},
            after_state={"label": label, "evidence_chunk_ids": list(ptr_ids)},
            diff={"changed_fields": ["label"] if prev_label != label else ["evidence"], "from": prev_label, "to": label},
            why={"evidence_pointers": pointers[:5], "rationale": rationale[:500]},
            request_id=request_id,
            actor_role="student",
        )

    log_audit(engine, subject_id=ident.subject_id, action="bff.ai.demonstration", object_type="skill_assessment",
              object_id=ass_id, status="ok", detail={"skill_id": payload.skill_id, "label": label})
    return {**result, "request_id": request_id}


# ─── Skills Profile ───────────────────────────────────────────────────────────

@router.get("/profile")
async def bff_student_profile(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Compile student skills profile with evidence items.
    Each skill entry includes Why/Evidence chunks from real assessments.
    """
    if user_id and user_id != ident.subject_id:
        raise HTTPException(status_code=403, detail="Cross-user profile access is forbidden")
    subject = ident.subject_id

    skills_rows = db.execute(
        text("SELECT skill_id, canonical_name, definition FROM skills ORDER BY canonical_name LIMIT 20")
    ).mappings().all()

    consent_cols = set(_table_columns(db, "consents"))
    scope_select = "c.scope" if "scope" in consent_cols else "NULL::text AS scope"
    doc_rows = db.execute(
        text(f"""
            SELECT d.doc_id, d.filename, {scope_select}, c.status, d.created_at
            FROM documents d
            JOIN consents c ON c.doc_id = d.doc_id::text
            WHERE c.user_id = :sub AND c.status = 'granted'
            ORDER BY d.created_at DESC LIMIT 10
        """),
        {"sub": subject},
    ).mappings().all()

    skills_profile = []
    for skill in skills_rows:
        skill_id = skill["skill_id"]

        assess_row = db.execute(
            text("""
                SELECT decision, evidence, decision_meta
                FROM skill_assessments sa
                JOIN consents c ON c.doc_id = sa.doc_id::text
                WHERE sa.skill_id = :sid
                  AND c.user_id = :sub
                  AND c.status = 'granted'
                ORDER BY sa.created_at DESC LIMIT 1
            """),
            {"sid": skill_id, "sub": subject},
        ).mappings().first()

        evidence_items = []
        if assess_row:
            raw_ids = []
            ev = assess_row.get("evidence") or []
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except Exception:
                    ev = []
            for e in (ev or []):
                if isinstance(e, dict) and e.get("chunk_id"):
                    raw_ids.append(e["chunk_id"])
                elif isinstance(e, str):
                    raw_ids.append(e)
            for cid in (raw_ids or [])[:3]:
                chunk = db.execute(
                    text("""
                        SELECT chunk_id, snippet, section_path, page_start, doc_id
                        FROM chunks WHERE chunk_id = :cid LIMIT 1
                    """),
                    {"cid": cid},
                ).mappings().first()
                if chunk:
                    evidence_items.append({
                        "chunk_id": chunk["chunk_id"],
                        "snippet": (chunk["snippet"] or "")[:400],
                        "section_path": chunk.get("section_path"),
                        "page_start": chunk.get("page_start"),
                        "doc_id": chunk["doc_id"],
                    })

        if assess_row:
            label = assess_row.get("decision", assess_row.get("label")) or "not_assessed"
            meta = assess_row.get("decision_meta") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            rationale = meta.get("rationale") if isinstance(meta, dict) else None
        else:
            label = "not_assessed"
            rationale = None
        entry: Dict[str, Any] = {
            "skill_id": skill_id,
            "canonical_name": skill["canonical_name"],
            "definition": skill.get("definition"),
            "label": label,
            "rationale": rationale,
            "evidence_items": evidence_items,
        }

        if not evidence_items:
            entry["refusal"] = refusal_dict(
                "not_enough_information",
                f"No evidence found for skill '{skill['canonical_name']}'.",
                "Upload documents that demonstrate this skill, embed chunks, then run an AI assessment.",
            )

        skills_profile.append(entry)

    recent_assessment_events: List[Dict[str, Any]] = []
    try:
        internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
        async with httpx.AsyncClient(trust_env=False) as client:
            r = await client.get(
                f"{_BASE}/interactive/users/{subject}/recent_updates?limit=6",
                headers={"Authorization": f"Bearer {internal_token}"},
                timeout=20,
            )
        if r.status_code == 200:
            payload = r.json()
            recent_assessment_events = payload.get("assessment_events") or payload.get("items") or []
    except Exception:
        recent_assessment_events = []

    return {
        "subject_id": subject,
        "documents_count": len(doc_rows),
        "documents": [dict(d) for d in doc_rows],
        "skills": skills_profile,
        "recent_assessment_events": recent_assessment_events,
        "generated_at": _now_utc().isoformat(),
    }


@router.get("/assessments/recent")
async def bff_recent_assessment_updates(
    limit: int = 10,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Student-facing recent interactive assessments with linked skill updates.
    """
    internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.get(
            f"{_BASE}/interactive/users/{ident.subject_id}/recent_updates?limit={max(1, min(limit, 50))}",
            headers={"Authorization": f"Bearer {internal_token}"},
            timeout=30,
        )
    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise HTTPException(status_code=r.status_code, detail=err.get("detail", r.text))

    data = r.json()
    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.student.assessments.recent",
        object_type="assessment",
        status="ok",
        detail={"count": int(data.get("count", 0))},
    )
    events = data.get("assessment_events") or data.get("items") or []
    return {**data, "assessment_events": events, "items": events}


# ─── Role Alignment ───────────────────────────────────────────────────────────

class RoleAlignmentReq(BaseModel):
    role_id: str
    doc_id: Optional[str] = None


@router.post("/roles/alignment")
async def bff_role_alignment(
    payload: RoleAlignmentReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Role readiness with consent check, persistence (store=True), and P4 change log."""
    doc_id = payload.doc_id
    if not doc_id:
        first_doc = db.execute(
            text("""
                SELECT d.doc_id FROM documents d
                JOIN consents c ON c.doc_id = d.doc_id::text
                WHERE c.user_id = :sub AND c.status = 'granted'
                ORDER BY d.created_at DESC LIMIT 1
            """),
            {"sub": ident.subject_id},
        ).mappings().first()
        doc_id = first_doc["doc_id"] if first_doc else None
    if not doc_id:
        raise HTTPException(
            status_code=400,
            detail=make_refusal(
                "no_document",
                "No consented document found. Upload a document first.",
                "Upload and embed a document.",
                status_code=400,
            ),
        )
    _check_consent(db, doc_id, ident.subject_id)

    internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.post(
            f"{_BASE}/assess/role_readiness",
            json={"role_id": payload.role_id, "doc_id": doc_id, "subject_id": ident.subject_id, "store": True},
            headers={"Authorization": f"Bearer {internal_token}"},
            timeout=60,
        )
    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise HTTPException(status_code=r.status_code, detail=err.get("detail", r.text))

    result = r.json()
    score = float(result.get("score", result.get("readiness_score", 0)))
    if "score" not in result and "readiness_score" in result:
        result["score"] = score
    breakdown = {"status_summary": result.get("status_summary", {}), "items": result.get("items", [])}

    request_id = str(uuid.uuid4())
    prev = get_prev_role_readiness_snapshot(engine, ident.subject_id, payload.role_id)
    prev_score = float(prev["score"]) if prev and prev.get("score") is not None else None
    prev_breakdown = (prev.get("breakdown") or {}) if prev else {}
    score_changed = prev_score is None or abs(score - prev_score) >= 0.01
    breakdown_changed = prev_breakdown != breakdown
    has_change = score_changed or breakdown_changed

    write_role_readiness_snapshot(engine, ident.subject_id, payload.role_id, score, breakdown, request_id=request_id)
    if has_change:
        write_change_event(
            engine,
            scope="student",
            event_type="role_readiness_changed",
            subject_id=ident.subject_id,
            entity_key=payload.role_id,
            before_state={"score": prev_score, "breakdown": prev_breakdown},
            after_state={"score": score, "breakdown": breakdown},
            diff={"changed_fields": ["score"] if score_changed else ["breakdown"], "score_delta": (score - (prev_score or 0))},
            why={"rule_triggers": ["role_readiness_assessment"], "evidence_from_skills": [it.get("skill_id") for it in result.get("items", [])[:5] if isinstance(it, dict) and it.get("skill_id")]},
            request_id=request_id,
            actor_role="student",
        )

    if score < 0.30:
        result["refusal"] = refusal_dict(
            "low_readiness",
            f"Readiness score {score*100:.0f}% is below threshold.",
            "Upload evidence for missing skills, or take interactive assessments.",
        )

    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.assess.role_readiness",
        object_type="role",
        object_id=payload.role_id,
        status="ok",
        detail={"request_id": request_id},
    )
    return result


# ─── Actions / Recommend ─────────────────────────────────────────────────────

class ActionsReq(BaseModel):
    skill_id: str
    doc_id: Optional[str] = None
    role_id: Optional[str] = None


@router.post("/actions/recommend")
async def bff_actions_recommend(
    payload: ActionsReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Action recommendations. Requires consent if doc_id is provided."""
    if payload.doc_id:
        _check_consent(db, payload.doc_id, ident.subject_id)

    body: Dict[str, Any] = {"skill_id": payload.skill_id, "user_id": ident.subject_id}
    if payload.role_id:
        body["role_id"] = payload.role_id

    internal_token = issue_token(ident.subject_id, ident.role, ttl_s=300)
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.post(f"{_BASE}/actions/recommend", json=body, headers={"Authorization": f"Bearer {internal_token}"}, timeout=30)
    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise HTTPException(status_code=r.status_code, detail=err.get("detail", r.text))

    return r.json()


# ─── Consent Management ───────────────────────────────────────────────────────

@router.get("/consents")
def bff_list_consents(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List student's consent records with document metadata."""
    rows = db.execute(
        text("""
            SELECT
                c.consent_id, c.doc_id, c.scope, c.status,
                c.created_at, c.revoked_at, c.revoke_reason,
                d.filename, d.doc_type
            FROM consents c
            LEFT JOIN documents d ON d.doc_id::text = c.doc_id
            WHERE c.user_id = :sub
            ORDER BY c.created_at DESC
            LIMIT 50
        """),
        {"sub": ident.subject_id},
    ).mappings().all()

    items = []
    for row in rows:
        raw_scope = row.get("scope") or ""
        parts = raw_scope.split(":", 1)
        items.append({
            "consent_id": str(row["consent_id"]),
            "doc_id": row["doc_id"],
            "filename": row.get("filename") or row["doc_id"],
            "doc_type": row.get("doc_type"),
            "purpose": parts[0] if parts else "unknown",
            "scope": parts[1] if len(parts) >= 2 else parts[0] if parts else "unknown",
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "revoked_at": row["revoked_at"].isoformat() if row.get("revoked_at") else None,
            "revoke_reason": row.get("revoke_reason"),
        })

    return {"count": len(items), "items": items}


class WithdrawReq(BaseModel):
    doc_id: str
    reason: str = "Student requested withdrawal"


@router.post("/consents/withdraw")
def bff_withdraw_consent(
    payload: WithdrawReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Withdraw consent and cascade-delete all document data."""
    row = db.execute(
        text("""
            SELECT consent_id FROM consents
            WHERE doc_id = :doc_id AND user_id = :sub
            ORDER BY created_at DESC LIMIT 1
        """),
        {"doc_id": payload.doc_id, "sub": ident.subject_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="No consent record found for this document.")

    from backend.app.routers.consents import _cascade_delete_document_data
    deleted = _cascade_delete_document_data(db, payload.doc_id)

    db.execute(
        text("""
            UPDATE consents
            SET status = 'revoked', revoked_at = :now, revoke_reason = :reason
            WHERE doc_id = :doc_id AND user_id = :sub
        """),
        {
            "now": _now_utc(),
            "reason": payload.reason,
            "doc_id": payload.doc_id,
            "sub": ident.subject_id,
        },
    )
    db.commit()

    audit_id = log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.consents.withdraw",
        object_type="document",
        object_id=payload.doc_id,
        status="ok",
        detail={"reason": payload.reason, "deleted_counts": deleted},
    )
    request_id = str(uuid.uuid4())
    write_change_event(
        engine,
        scope="student",
        event_type="consent_withdrawn",
        subject_id=ident.subject_id,
        entity_key=payload.doc_id,
        before_state={"status": "granted"},
        after_state={"status": "revoked"},
        diff={"changed_fields": ["status"], "rule_triggers": ["withdraw"]},
        why={"rule_triggers": ["consent_withdraw"], "scope": "document", "purpose": "cascade_delete"},
        request_id=request_id,
        actor_role="student",
    )
    return {
        "ok": True,
        "doc_id": payload.doc_id,
        "deleted": deleted,
        "audit_id": audit_id,
        "message": "All document data permanently deleted. Minimal audit metadata retained.",
    }


@router.delete("/documents/{doc_id}")
def bff_delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Delete document and all related data (cascade: DB + Qdrant + file)."""
    doc_row = db.execute(
        text("SELECT doc_id FROM documents WHERE doc_id = :doc_id"),
        {"doc_id": doc_id},
    ).mappings().first()

    if not doc_row:
        raise HTTPException(status_code=404, detail="Document not found.")

    from backend.app.routers.consents import _cascade_delete_document_data
    deleted = _cascade_delete_document_data(db, doc_id)

    db.execute(
        text("""
            UPDATE consents SET status = 'revoked', revoked_at = :now,
                revoke_reason = 'Document deleted by student'
            WHERE doc_id = :doc_id
        """),
        {"now": _now_utc(), "doc_id": doc_id},
    )
    db.commit()

    audit_id = log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.documents.delete",
        object_type="document",
        object_id=doc_id,
        status="ok",
        detail={"deleted_counts": deleted},
    )
    request_id = str(uuid.uuid4())
    write_change_event(
        engine,
        scope="student",
        event_type="document_deleted",
        subject_id=ident.subject_id,
        entity_key=doc_id,
        before_state={"exists": True},
        after_state={"exists": False},
        diff={"changed_fields": ["deleted"], "rule_triggers": ["delete"]},
        why={"rule_triggers": ["document_delete"], "scope": "document"},
        request_id=request_id,
        actor_role="student",
    )
    return {
        "ok": True,
        "doc_id": doc_id,
        "deleted": deleted,
        "audit_id": audit_id,
        "message": "Document permanently deleted. Minimal audit metadata retained.",
    }


# ─── Change Log (P4 Protocol 5) ────────────────────────────────────────────────

@router.get("/change_log")
def bff_student_change_log(
    limit: int = 50,
    cursor: Optional[str] = None,
    ident: Identity = Depends(require_auth),
):
    """List explainable change events for this student. Refusal when no consent or no data."""
    out = list_change_log_student(engine, ident.subject_id, limit=limit, cursor=cursor)
    if not out.get("items"):
        return {
            **out,
            "refusal": refusal_dict(
                "no_changes",
                "No change events found for your account.",
                "Upload documents, run skill assessments, or check role readiness to generate events.",
            ),
        }
    return out


# ─── Export Statement ─────────────────────────────────────────────────────────

@router.get("/export/statement")
async def bff_export_statement(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Generate one-page skills statement for download.
    Includes: skill claims + evidence items, sources, timestamps.
    """
    profile = await bff_student_profile(db=db, ident=ident)

    total_evidence = sum(len(s.get("evidence_items", [])) for s in profile.get("skills", []))
    demonstrated = [s for s in profile.get("skills", []) if s.get("label") in ("demonstrated", "mentioned")]

    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.export.statement",
        object_type="profile",
        status="ok",
        detail={"demonstrated_skills": len(demonstrated), "total_evidence": total_evidence},
    )

    return {
        "subject_id": ident.subject_id,
        "generated_at": _now_utc().isoformat(),
        "statement": {
            "total_skills_assessed": len(profile.get("skills", [])),
            "demonstrated_skills": len(demonstrated),
            "total_evidence_items": total_evidence,
            "documents": profile.get("documents", []),
            "skills": profile.get("skills", []),
        },
    }
