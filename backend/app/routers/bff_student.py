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
import hashlib
import hmac
import json
import logging
import os
import uuid
import base64
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
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
from backend.app.security import Identity, issue_token, require_auth, _is_dev_login_allowed

router = APIRouter(prefix="/bff/student", tags=["bff-student"])
_log = logging.getLogger(__name__)

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
def bff_dev_login(payload: DevLoginReq):
    """Direct token issuance (no internal HTTP call)."""
    if not _is_dev_login_allowed():
        raise HTTPException(status_code=403, detail="dev_login disabled in production")
    token = issue_token(payload.subject_id, payload.role, ttl_s=int(payload.ttl_s))
    return {"token": token, "subject_id": payload.subject_id, "role": payload.role}


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
def bff_list_skills(
    limit: int = 10,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Direct DB query to skill registry (no internal HTTP call)."""
    from backend.app.routers.skills import list_or_search
    data = list_or_search(q=None, limit=min(limit, 100), db=db)
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
def bff_list_roles(
    limit: int = 20,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Direct DB query to role library (no internal HTTP call)."""
    from backend.app.routers.roles import list_roles
    data = list_roles(limit=min(limit, 100), db=db)
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

    from backend.app.routers.documents import upload_multimodal_document
    file.file.seek(0)
    data = await upload_multimodal_document(
        file=file,
        doc_type="demo",
        user_id=ident.subject_id,
        consent=True,
        db=db,
        ident=ident,
    )
    doc_id = data.get("doc_id")

    if doc_id:
        consent_id = str(uuid.uuid4())
        db.execute(
            text("""
                INSERT INTO consents
                  (consent_id, user_id, doc_id, status, created_at)
                SELECT
                  :cid, :sub, :doc_id, 'granted', :now
                WHERE NOT EXISTS (
                  SELECT 1 FROM consents
                  WHERE user_id = :sub AND doc_id = :doc_id AND status = 'granted'
                )
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
        try:
            doc_count = db.execute(
                text("SELECT COUNT(*) FROM consents WHERE user_id = :uid AND status = 'granted'"),
                {"uid": ident.subject_id},
            ).scalar() or 0
            _update_achievement_progress(db, ident.subject_id, "document_master", int(doc_count))
        except Exception as e:
            _log.warning("achievement update after upload failed: %s", e)

    return {**data, "purpose": purpose, "scope": scope, "consent_status": "granted"}


# ─── Embed ────────────────────────────────────────────────────────────────────

@router.post("/chunks/embed/{doc_id}")
async def bff_embed(
    doc_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Embed chunks for a document directly (no internal HTTP call)."""
    _check_consent(db, doc_id, ident.subject_id)

    try:
        from backend.app.routers.chunks import embed_document_chunks
        result = embed_document_chunks(doc_id, db, ident)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.chunks.embed",
        object_type="document",
        object_id=doc_id,
        status="ok",
    )
    return result


# ─── Auto-assess after upload (Gap 13) ─────────────────────────────────────────

AUTO_ASSESS_SKILL_LIMIT = int(os.getenv("AUTO_ASSESS_SKILL_LIMIT", "50"))


def _run_auto_assess_for_doc(
    db: Session,
    doc_id: str,
    ident: Identity,
) -> Dict[str, Any]:
    """
    Run demonstration + proficiency for a fixed set of skills for one document.
    Persists to skill_assessments and skill_proficiency. Used after embed completes.
    """
    from backend.app.routers.ai import (
        ai_demonstration,
        ai_proficiency,
        DemonstrationRequest,
        ProficiencyRequest,
    )

    skills_rows = db.execute(
        text("SELECT skill_id FROM skills ORDER BY canonical_name LIMIT :lim"),
        {"lim": AUTO_ASSESS_SKILL_LIMIT},
    ).mappings().all()
    skill_ids = [str(r["skill_id"]) for r in skills_rows]
    if not skill_ids:
        return {"skills_processed": 0, "message": "No skills in registry."}

    processed = 0
    failed = 0
    for skill_id in skill_ids:
        try:
            # Demonstration (Decision 2)
            dem_req = DemonstrationRequest(skill_id=skill_id, doc_id=doc_id, k=8, min_score=0.15)
            dem_result = ai_demonstration(req=dem_req, db=db, ident=ident)
            label = dem_result.get("label", "not_enough_information")
            rationale = dem_result.get("rationale", "")
            evidence_ids = dem_result.get("evidence_chunk_ids") or []

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

            ass_id = str(uuid.uuid4())
            db.execute(
                text("""
                    INSERT INTO skill_assessments (assessment_id, doc_id, skill_id, decision, evidence, decision_meta, created_at)
                    VALUES (:aid, :doc_id, :skill_id, :decision, (:ev)::jsonb, (:meta)::jsonb, :now)
                """),
                {
                    "aid": ass_id,
                    "doc_id": doc_id,
                    "skill_id": skill_id,
                    "decision": label,
                    "ev": json.dumps([{"chunk_id": p["chunk_id"], "snippet": p.get("snippet", "")[:300]} for p in pointers]),
                    "meta": json.dumps({"source": "auto_assess", "rationale": rationale}),
                    "now": _now_utc(),
                },
            )
            db.commit()

            # Proficiency (Decision 3)
            prof_req = ProficiencyRequest(skill_id=skill_id, doc_id=doc_id, k=8, min_score=0.15)
            prof_result = ai_proficiency(req=prof_req, db=db, ident=ident)
            level = int(prof_result.get("level", 0))
            prof_label = prof_result.get("label", "novice")
            why = (prof_result.get("why") or "")[:2000]
            ev_ids = prof_result.get("evidence_chunk_ids") or []
            best_evidence = {"chunk_id": ev_ids[0], "snippet": ""} if ev_ids else {}

            prof_id = str(uuid.uuid4())
            db.execute(
                text("""
                    INSERT INTO skill_proficiency (prof_id, doc_id, skill_id, level, label, rationale, best_evidence, signals, meta, created_at)
                    VALUES (:pid, :doc_id, :skill_id, :level, :label, :rationale, CAST(:best_evidence AS JSONB), '{}'::jsonb, CAST(:meta AS JSONB), :now)
                """),
                {
                    "pid": prof_id,
                    "doc_id": doc_id,
                    "skill_id": skill_id,
                    "level": level,
                    "label": prof_label,
                    "rationale": why,
                    "best_evidence": json.dumps(best_evidence),
                    "meta": json.dumps({"source": "auto_assess"}),
                    "now": _now_utc(),
                },
            )
            db.commit()
            processed += 1
        except Exception as e:
            _log.warning("auto_assess skill %s for doc %s failed: %s", skill_id, doc_id, e)
            db.rollback()
            failed += 1
            continue

    return {"skills_processed": processed, "skills_failed": failed, "skill_ids": skill_ids[:processed]}


def _auto_assess_background(doc_id: str, subject_id: str, role: str):
    """Run embed + auto-assess in a background thread with its own DB session."""
    import threading
    from backend.app.db.session import SessionLocal

    def _run():
        _log.info("auto-assess background: starting for doc %s", doc_id)
        bg_db = SessionLocal()
        try:
            bg_ident = Identity(subject_id=subject_id, role=role, source="bearer")

            embed_ok = False
            try:
                from backend.app.routers.chunks import embed_document_chunks
                embed_document_chunks(doc_id, bg_db, bg_ident)
                embed_ok = True
                _log.info("auto-assess background: embedded chunks for doc %s", doc_id)
            except Exception as exc:
                _log.warning("auto-assess background: embed failed for doc %s: %s — continuing with DB chunks fallback", doc_id, exc)

            result = _run_auto_assess_for_doc(bg_db, doc_id, bg_ident)
            log_audit(
                engine,
                subject_id=subject_id,
                action="bff.student.documents.auto_assess",
                object_type="document",
                object_id=doc_id,
                status="ok",
                detail=result,
            )
            _log.info("auto-assess background: completed for doc %s — %s", doc_id, result)
        except Exception as exc:
            _log.error("auto-assess background: failed for doc %s: %s", doc_id, exc)
        finally:
            bg_db.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()


@router.post("/documents/{doc_id}/auto-assess")
def bff_documents_auto_assess(
    doc_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Kick off embed + demonstration + proficiency for all skills on this document.
    HTTP 202 Accepted; processing continues in a background thread.
    """
    _check_consent(db, doc_id, ident.subject_id)
    _auto_assess_background(doc_id, ident.subject_id, ident.role)
    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "doc_id": doc_id,
            "message": "Auto-assess started in background. Refresh the Skills page in ~1–2 minutes.",
        },
    )


# ─── Evidence Search ──────────────────────────────────────────────────────────

class EvidenceSearchReq(BaseModel):
    query_text: Optional[str] = None
    skill_id: Optional[str] = None
    doc_id: Optional[str] = None
    k: int = 5
    min_score: float = 0.0


@router.post("/search/evidence_vector")
def bff_search_evidence(
    payload: EvidenceSearchReq,
    request: Request,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Direct call to search_evidence_vector (no internal HTTP). Consent check when doc_id provided.
    Decision 1: refusal from pipeline (threshold) -> items=[], refusal={code, message, next_step}.
    Audit: bff.student.search.evidence_vector (refusal or ok).
    """
    if payload.doc_id:
        _check_consent(db, payload.doc_id, ident.subject_id)

    from backend.app.routers.search import search_evidence_vector, EvidenceSearchRequest
    req = EvidenceSearchRequest(
        query_text=payload.query_text,
        skill_id=payload.skill_id,
        doc_id=payload.doc_id,
        k=payload.k,
        min_score=payload.min_score,
    )
    result = search_evidence_vector(req=req, request=request, db=db, ident=ident)
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
def bff_ai_demonstration(
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

    from backend.app.routers.ai import ai_demonstration, DemonstrationRequest
    result = ai_demonstration(
        req=DemonstrationRequest(skill_id=payload.skill_id, doc_id=payload.doc_id, k=payload.k),
        db=db, ident=ident,
    )
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

        prof_row = db.execute(
            text("""
                SELECT sp.level FROM skill_proficiency sp
                JOIN consents c ON c.doc_id = sp.doc_id::text
                  AND c.user_id = :sub AND c.status = 'granted'
                WHERE sp.skill_id = :sid
                ORDER BY sp.created_at DESC LIMIT 1
            """),
            {"sub": subject, "sid": skill_id},
        ).mappings().first()
        level = int(prof_row["level"]) if prof_row and prof_row.get("level") is not None else None

        entry: Dict[str, Any] = {
            "skill_id": skill_id,
            "canonical_name": skill["canonical_name"],
            "definition": skill.get("definition"),
            "label": label,
            "level": level,
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
        rows = db.execute(
            text("""
                SELECT s.session_id, s.assessment_type, s.skill_id, s.status,
                       s.created_at, s.completed_at,
                       a.score  AS attempt_score,
                       a.evaluation AS attempt_evaluation,
                       a.submitted_at
                FROM assessment_sessions s
                LEFT JOIN LATERAL (
                    SELECT score, evaluation, submitted_at
                    FROM assessment_attempts
                    WHERE session_id = s.session_id
                    ORDER BY attempt_number DESC
                    LIMIT 1
                ) a ON true
                WHERE s.user_id = :uid
                ORDER BY s.created_at DESC LIMIT 6
            """),
            {"uid": subject},
        ).mappings().all()
        for r in rows:
            evt = dict(r)
            score = evt.pop("attempt_score", None)
            evaluation = evt.pop("attempt_evaluation", None)
            if isinstance(evaluation, str):
                try:
                    evaluation = json.loads(evaluation)
                except Exception:
                    evaluation = {}
            if not isinstance(evaluation, dict):
                evaluation = {}
            if score is None:
                score = evaluation.get("overall_score", evaluation.get("score", 0))
            evt["score"] = float(score or 0)
            raw_level = evaluation.get("level")
            if isinstance(raw_level, str):
                level_map = {"novice": 0, "developing": 1, "intermediate": 2, "advanced": 3, "expert": 3}
                raw_level = level_map.get(raw_level.lower(), 0)
            elif isinstance(raw_level, (int, float)):
                raw_level = int(raw_level)
            else:
                s = evt["score"]
                raw_level = 3 if s >= 85 else 2 if s >= 70 else 1 if s >= 50 else 0
            evt["level"] = raw_level
            for k in ("created_at", "completed_at", "submitted_at"):
                if evt.get(k) and hasattr(evt[k], "isoformat"):
                    evt[k] = evt[k].isoformat()
            recent_assessment_events.append(evt)
    except Exception as exc:
        _log.warning("assessment events query failed: %s", exc)
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
def bff_recent_assessment_updates(
    limit: int = 10,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Student-facing recent interactive assessments (direct DB query).
    Gracefully returns empty list if assessment tables don't exist yet.
    """
    try:
        safe_limit = max(1, min(limit, 50))
        rows = db.execute(
            text("""
                SELECT s.session_id, s.assessment_type, s.skill_id, s.status,
                       s.created_at, s.completed_at,
                       a.score  AS attempt_score,
                       a.evaluation AS attempt_evaluation,
                       a.submitted_at
                FROM assessment_sessions s
                LEFT JOIN LATERAL (
                    SELECT score, evaluation, submitted_at
                    FROM assessment_attempts
                    WHERE session_id = s.session_id
                    ORDER BY attempt_number DESC
                    LIMIT 1
                ) a ON true
                WHERE s.user_id = :uid
                ORDER BY s.created_at DESC LIMIT :lim
            """),
            {"uid": ident.subject_id, "lim": safe_limit},
        ).mappings().all()

        events = []
        for r in rows:
            evt = dict(r)
            score = evt.pop("attempt_score", None)
            evaluation = evt.pop("attempt_evaluation", None)
            if isinstance(evaluation, str):
                try:
                    evaluation = json.loads(evaluation)
                except Exception:
                    evaluation = {}
            if not isinstance(evaluation, dict):
                evaluation = {}
            if score is None:
                score = evaluation.get("overall_score", evaluation.get("score", 0))
            evt["score"] = float(score or 0)
            raw_level = evaluation.get("level")
            if isinstance(raw_level, str):
                level_map = {"novice": 0, "developing": 1, "intermediate": 2, "advanced": 3, "expert": 3}
                raw_level = level_map.get(raw_level.lower(), 0)
            elif isinstance(raw_level, (int, float)):
                raw_level = int(raw_level)
            else:
                s = evt["score"]
                raw_level = 3 if s >= 85 else 2 if s >= 70 else 1 if s >= 50 else 0
            evt["level"] = raw_level
            for k in ("created_at", "completed_at", "submitted_at"):
                if evt.get(k) and hasattr(evt[k], "isoformat"):
                    evt[k] = evt[k].isoformat()
            events.append(evt)

        log_audit(
            engine,
            subject_id=ident.subject_id,
            action="bff.student.assessments.recent",
            object_type="assessment",
            status="ok",
            detail={"count": len(events)},
        )
        return {"count": len(events), "assessment_events": events, "items": events}
    except Exception as exc:
        _log.warning("recent assessment items query failed: %s", exc)
        return {"count": 0, "assessment_events": [], "items": []}


# ─── Role Alignment ───────────────────────────────────────────────────────────

class RoleAlignmentReq(BaseModel):
    role_id: str
    doc_id: Optional[str] = None


class RoleAlignmentBatchReq(BaseModel):
    role_ids: List[str]
    doc_id: Optional[str] = None


@router.post("/roles/alignment/batch")
async def bff_role_alignment_batch(
    payload: RoleAlignmentBatchReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Lightweight batch readiness: single-pass SQL instead of per-role aggregator.
    Computes readiness from the latest skill_assessments joined with role requirements.
    Designed to complete within Render's 30s timeout.
    """
    role_ids = payload.role_ids[:50] if payload.role_ids else []
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
    if not doc_id or not role_ids:
        return {"items": [], "count": 0}

    try:
        _check_consent(db, doc_id, ident.subject_id)
    except Exception:
        return {"items": [], "count": 0}

    # 1) Get ALL consented doc_ids for this user
    doc_rows = db.execute(
        text("SELECT DISTINCT doc_id FROM consents WHERE user_id = :sub AND status = 'granted'"),
        {"sub": ident.subject_id},
    ).mappings().all()
    consented_doc_ids = [str(r["doc_id"]) for r in doc_rows]
    if not consented_doc_ids:
        return {"items": [], "count": 0}

    # 2) Get best assessment decision + proficiency level per skill (single query)
    from sqlalchemy.sql import bindparam
    assess_sql = text("""
        SELECT DISTINCT ON (sa.skill_id)
            sa.skill_id, sa.decision,
            COALESCE(sp.level, 0) AS level
        FROM skill_assessments sa
        LEFT JOIN skill_proficiency sp
            ON sp.skill_id = sa.skill_id AND sp.doc_id = sa.doc_id
        WHERE sa.doc_id::text IN :doc_ids
        ORDER BY sa.skill_id,
            CASE sa.decision WHEN 'demonstrated' THEN 1 WHEN 'match' THEN 1 WHEN 'mentioned' THEN 2 ELSE 3 END,
            sa.created_at DESC
    """).bindparams(bindparam("doc_ids", expanding=True))
    assess_rows = db.execute(assess_sql, {"doc_ids": tuple(consented_doc_ids)}).mappings().all()
    skill_map: Dict[str, Dict] = {}
    for r in assess_rows:
        skill_map[r["skill_id"]] = {"decision": r["decision"], "level": int(r["level"]) if r["level"] is not None else 0}

    # 3) Get role titles
    from sqlalchemy.sql import bindparam as bp2
    role_title_sql = text("SELECT role_id, role_title FROM roles WHERE role_id IN :rids").bindparams(bp2("rids", expanding=True))
    role_titles = {str(r["role_id"]): str(r["role_title"]) for r in db.execute(role_title_sql, {"rids": tuple(role_ids)}).mappings().all()}

    # 4) Get ALL role requirements in one query
    req_sql = text("""
        SELECT rsr.role_id, rsr.skill_id, rsr.target_level, rsr.required, rsr.weight,
               COALESCE(s.canonical_name, rsr.skill_id) AS skill_name
        FROM role_skill_requirements rsr
        LEFT JOIN skills s ON s.skill_id = rsr.skill_id
        WHERE rsr.role_id IN :rids
        ORDER BY rsr.role_id, rsr.skill_id
    """).bindparams(bp2("rids", expanding=True))
    req_rows = db.execute(req_sql, {"rids": tuple(role_ids)}).mappings().all()

    # 5) Group requirements by role and compute readiness
    from collections import defaultdict
    role_reqs: Dict[str, list] = defaultdict(list)
    for r in req_rows:
        role_reqs[r["role_id"]].append(dict(r))

    items = []
    for rid in role_ids:
        reqs = role_reqs.get(rid, [])
        if not reqs:
            items.append({"role_id": rid, "role_title": role_titles.get(rid, ""), "readiness": 0})
            continue

        total_weight = 0.0
        weighted_score = 0.0
        meet_count = 0
        gap_skills = []

        for req_item in reqs:
            sid = req_item["skill_id"]
            target = int(req_item["target_level"]) if req_item["target_level"] is not None else 2
            weight = float(req_item["weight"]) if req_item["weight"] is not None else 1.0
            required = bool(req_item["required"])

            sk = skill_map.get(sid, {})
            decision = sk.get("decision", "")
            achieved = sk.get("level", 0)

            if decision in ("demonstrated", "match") and achieved >= target:
                score = 1.0
                meet_count += 1
            elif decision in ("demonstrated", "match") and achieved > 0:
                score = max(0.3, min(1.0, achieved / max(target, 1)))
                gap_skills.append(req_item["skill_name"])
            else:
                score = 0.0 if required else 0.1
                gap_skills.append(req_item["skill_name"])

            weighted_score += score * weight
            total_weight += weight

        readiness = round((weighted_score / total_weight) * 100) if total_weight > 0 else 0
        items.append({
            "role_id": rid,
            "role_title": role_titles.get(rid, ""),
            "readiness": readiness,
            "skills_met": meet_count,
            "skills_total": len(reqs),
            "gaps": gap_skills[:3],
        })

    return {"items": items, "count": len(items)}


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

    from backend.app.routers.assess import role_readiness, RoleReadinessRequest
    req = RoleReadinessRequest(
        role_id=payload.role_id,
        doc_id=doc_id,
        subject_id=ident.subject_id,
        store=True,
    )
    result = role_readiness(req=req, db=db, ident=ident)
    score = float(result.get("score", result.get("readiness_score", 0)))
    if "score" not in result and "readiness_score" in result:
        result["score"] = score
    breakdown = {"status_summary": result.get("status_summary", {}), "items": result.get("items", [])}

    request_id = str(uuid.uuid4())
    try:
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
    except Exception as exc:
        _log.warning("role alignment snapshot/changelog write failed (non-blocking): %s", exc)

    if score < 0.30:
        result["refusal"] = refusal_dict(
            "low_readiness",
            f"Readiness score {score*100:.0f}% is below threshold.",
            "Upload evidence for missing skills, or take interactive assessments.",
        )

    try:
        log_audit(
            engine,
            subject_id=ident.subject_id,
            action="bff.assess.role_readiness",
            object_type="role",
            object_id=payload.role_id,
            status="ok",
            detail={"request_id": request_id},
        )
    except Exception:
        pass
    return result


# ─── Course Recommendations for Skill Gaps ───────────────────────────────────

class CourseForGapsReq(BaseModel):
    role_id: Optional[str] = None
    skill_ids: Optional[List[str]] = None


@router.post("/courses/for-gaps")
def bff_courses_for_gaps(
    payload: CourseForGapsReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Return HKU courses that develop the requested gap skills.

    Accepts either a role_id (looks up its required skills) or an explicit
    list of skill_ids.  Returns courses joined through course_skill_map with
    human-readable skill names.
    """
    target_skill_ids: List[str] = []

    if payload.role_id:
        rows = db.execute(
            text("SELECT skill_id FROM role_skill_requirements WHERE role_id = :rid"),
            {"rid": payload.role_id},
        ).fetchall()
        target_skill_ids = [r[0] for r in rows]

    if payload.skill_ids:
        for sid in payload.skill_ids:
            if sid not in target_skill_ids:
                target_skill_ids.append(sid)

    if not target_skill_ids:
        return {"items": [], "count": 0}

    placeholders = ", ".join(f":s{i}" for i in range(len(target_skill_ids)))
    params = {f"s{i}": sid for i, sid in enumerate(target_skill_ids)}

    sql = text(f"""
        SELECT
            c.course_id,
            c.title          AS course_name,
            c.description,
            csm.skill_id,
            s.canonical_name AS skill_name,
            csm.intended_level
        FROM course_skill_map csm
        JOIN courses c  ON c.course_id = csm.course_id
        JOIN skills  s  ON s.skill_id  = csm.skill_id
        WHERE csm.skill_id IN ({placeholders})
        ORDER BY c.course_id
    """)
    rows = db.execute(sql, params).mappings().all()

    courses_map: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        cid = r["course_id"]
        if cid not in courses_map:
            desc = r["description"] or ""
            parts = desc.split(" · ", 1)
            programme = parts[0] if parts else ""
            category = parts[1] if len(parts) > 1 else ""
            courses_map[cid] = {
                "course_id": cid,
                "course_name": r["course_name"],
                "programme": programme,
                "category": category,
                "credits": 6,
                "skills": [],
            }
        courses_map[cid]["skills"].append({
            "skill_id": r["skill_id"],
            "skill_name": r["skill_name"],
            "intended_level": r["intended_level"],
        })

    items = sorted(courses_map.values(), key=lambda c: len(c["skills"]), reverse=True)
    return {"items": items, "count": len(items)}


# ─── Actions / Recommend ─────────────────────────────────────────────────────

class ActionsReq(BaseModel):
    skill_id: str
    doc_id: Optional[str] = None
    role_id: Optional[str] = None


@router.post("/actions/recommend")
def bff_actions_recommend(
    payload: ActionsReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Direct call to recommend_actions (no internal HTTP). Requires consent if doc_id is provided."""
    if not payload.doc_id:
        raise HTTPException(status_code=400, detail="doc_id is required for action recommendations")
    _check_consent(db, payload.doc_id, ident.subject_id)

    from backend.app.routers.actions import recommend_actions, ActionRecommendRequest
    req = ActionRecommendRequest(
        doc_id=payload.doc_id,
        role_id=payload.role_id,
        skill_ids=[payload.skill_id] if payload.skill_id else None,
    )
    result = recommend_actions(req=req, db=db, ident=ident)
    actions = result.get("actions") or []
    subject_id = ident.subject_id
    for action in actions:
        skill_id = action.get("skill_id")
        gap_type = action.get("gap_type")
        if not skill_id or not gap_type:
            action["progress_status"] = "pending"
            action["completed_at"] = None
            continue
        row = db.execute(
            text("""
                SELECT status, completed_at FROM action_progress
                WHERE user_id = :uid AND skill_id = :skill_id AND gap_type = :gap_type
                LIMIT 1
            """),
            {"uid": subject_id, "skill_id": skill_id, "gap_type": gap_type},
        ).mappings().first()
        if row:
            action["progress_status"] = row["status"] or "pending"
            action["completed_at"] = row["completed_at"].isoformat() if row.get("completed_at") else None
        else:
            action["progress_status"] = "pending"
            action["completed_at"] = None
    result["actions"] = actions
    return result


class ActionProgressReq(BaseModel):
    skill_id: str
    gap_type: str
    role_id: Optional[str] = None
    doc_id: Optional[str] = None
    status: str = "completed"


@router.get("/actions/progress")
def bff_actions_progress_list(
    role_id: Optional[str] = None,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List current user's action progress (optional filter by role_id)."""
    subject_id = ident.subject_id
    if role_id:
        rows = db.execute(
            text("""
                SELECT skill_id, gap_type, role_id, status, completed_at, created_at
                FROM action_progress WHERE user_id = :uid AND (role_id = :rid OR role_id IS NULL)
                ORDER BY completed_at DESC NULLS LAST, created_at DESC
            """),
            {"uid": subject_id, "rid": role_id},
        ).mappings().all()
    else:
        rows = db.execute(
            text("""
                SELECT skill_id, gap_type, role_id, status, completed_at, created_at
                FROM action_progress WHERE user_id = :uid
                ORDER BY completed_at DESC NULLS LAST, created_at DESC
            """),
            {"uid": subject_id},
        ).mappings().all()
    items = [
        {
            "skill_id": r["skill_id"],
            "gap_type": r["gap_type"],
            "role_id": r.get("role_id"),
            "status": r["status"],
            "completed_at": r["completed_at"].isoformat() if r.get("completed_at") else None,
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]
    return {"items": items, "count": len(items)}


@router.post("/actions/progress")
def bff_actions_progress_upsert(
    payload: ActionProgressReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Upsert action progress (e.g. mark as completed)."""
    if payload.status not in ("pending", "completed"):
        raise HTTPException(status_code=422, detail="status must be 'pending' or 'completed'")
    subject_id = ident.subject_id
    now = _now_utc()
    completed_at = now if payload.status == "completed" else None
    doc_id_val = payload.doc_id if payload.doc_id else None
    db.execute(
        text("""
            INSERT INTO action_progress (user_id, skill_id, gap_type, role_id, doc_id, status, completed_at, created_at, updated_at)
            VALUES (:uid, :skill_id, :gap_type, :role_id, :doc_id::uuid, :status, :completed_at, :now, :now)
            ON CONFLICT (user_id, skill_id, gap_type)
            DO UPDATE SET status = EXCLUDED.status, completed_at = EXCLUDED.completed_at, updated_at = EXCLUDED.updated_at
        """),
        {
            "uid": subject_id,
            "skill_id": payload.skill_id,
            "gap_type": payload.gap_type,
            "role_id": payload.role_id,
            "doc_id": doc_id_val,
            "status": payload.status,
            "completed_at": completed_at,
            "now": now,
        },
    )
    db.commit()
    return {"skill_id": payload.skill_id, "gap_type": payload.gap_type, "status": payload.status, "completed_at": completed_at.isoformat() if completed_at else None}


# ─── Achievements (Gap 10) ─────────────────────────────────────────────────────

ACHIEVEMENT_DEFINITIONS: List[Dict[str, Any]] = [
    {"id": "first_assessment", "name": "初次尝试", "nameEn": "First Try", "description": "完成第一次评估", "descriptionEn": "Complete your first assessment", "icon": "🎯", "category": "assessment", "target": 1, "rarity": "common"},
    {"id": "comm_master", "name": "沟通达人", "nameEn": "Communication Master", "description": "沟通能力评估获得80分以上", "descriptionEn": "Score 80+ on communication assessment", "icon": "🎙️", "category": "assessment", "target": 80, "rarity": "rare"},
    {"id": "code_ninja", "name": "代码忍者", "nameEn": "Code Ninja", "description": "编程评估获得90分以上", "descriptionEn": "Score 90+ on programming assessment", "icon": "💻", "category": "assessment", "target": 90, "rarity": "epic"},
    {"id": "writer", "name": "文字工匠", "nameEn": "Word Smith", "description": "写作评估获得85分以上", "descriptionEn": "Score 85+ on writing assessment", "icon": "✍️", "category": "assessment", "target": 85, "rarity": "rare"},
    {"id": "triple_threat", "name": "三栖能手", "nameEn": "Triple Threat", "description": "三项评估均达到75分以上", "descriptionEn": "Score 75+ on all three assessments", "icon": "🏆", "category": "assessment", "target": 3, "rarity": "legendary"},
    {"id": "skill_seeker", "name": "技能探索者", "nameEn": "Skill Seeker", "description": "解锁5项技能", "descriptionEn": "Unlock 5 skills", "icon": "🔍", "category": "learning", "target": 5, "rarity": "common"},
    {"id": "document_master", "name": "文档达人", "nameEn": "Document Master", "description": "上传10份证据文档", "descriptionEn": "Upload 10 evidence documents", "icon": "📚", "category": "learning", "target": 10, "rarity": "rare"},
    {"id": "week_streak", "name": "持续进步", "nameEn": "On a Roll", "description": "连续7天登录", "descriptionEn": "7-day login streak", "icon": "🔥", "category": "milestone", "target": 7, "rarity": "rare"},
    {"id": "perfectionist", "name": "完美主义者", "nameEn": "Perfectionist", "description": "任意评估获得100分", "descriptionEn": "Score 100 on any assessment", "icon": "💯", "category": "milestone", "target": 100, "rarity": "legendary"},
    {"id": "early_bird", "name": "早起鸟", "nameEn": "Early Bird", "description": "在早上6点前完成评估", "descriptionEn": "Complete assessment before 6 AM", "icon": "🌅", "category": "special", "target": 1, "rarity": "epic"},
    {"id": "night_owl", "name": "夜猫子", "nameEn": "Night Owl", "description": "在凌晨12点后完成评估", "descriptionEn": "Complete assessment after midnight", "icon": "🦉", "category": "special", "target": 1, "rarity": "epic"},
]
RARITY_POINTS = {"common": 10, "rare": 25, "epic": 50, "legendary": 100}


def _update_achievement_progress(db: Session, user_id: str, achievement_id: str, progress: int) -> None:
    """Internal: upsert achievement progress (e.g. after upload or assessment)."""
    defn = next((d for d in ACHIEVEMENT_DEFINITIONS if d["id"] == achievement_id), None)
    if not defn:
        return
    target = int(defn["target"])
    progress = min(max(0, progress), target)
    unlocked = progress >= target
    now = _now_utc()
    unlocked_at = now if unlocked else None
    db.execute(
        text("""
            INSERT INTO user_achievements (user_id, achievement_id, progress, target, unlocked, unlocked_at, created_at, updated_at)
            VALUES (:uid, :aid, :progress, :target, :unlocked, :unlocked_at, :now, :now)
            ON CONFLICT (user_id, achievement_id)
            DO UPDATE SET progress = GREATEST(user_achievements.progress, EXCLUDED.progress),
                           unlocked = (user_achievements.unlocked OR EXCLUDED.unlocked),
                           unlocked_at = CASE WHEN EXCLUDED.unlocked AND user_achievements.unlocked_at IS NULL THEN EXCLUDED.unlocked_at ELSE user_achievements.unlocked_at END,
                           updated_at = EXCLUDED.updated_at
        """),
        {"uid": user_id, "aid": achievement_id, "progress": progress, "target": target, "unlocked": unlocked, "unlocked_at": unlocked_at, "now": now},
    )
    db.commit()


@router.get("/achievements")
def bff_achievements_list(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List achievements with progress and unlocked state from DB."""
    subject_id = ident.subject_id
    rows = db.execute(
        text("SELECT achievement_id, progress, target, unlocked, unlocked_at FROM user_achievements WHERE user_id = :uid"),
        {"uid": subject_id},
    ).mappings().all()
    db_by_id = {str(r["achievement_id"]): r for r in rows}
    achievements_out = []
    total_points = 0
    recent_unlock = None
    recent_row = db.execute(
        text("SELECT achievement_id, unlocked_at FROM user_achievements WHERE user_id = :uid AND unlocked = TRUE AND unlocked_at IS NOT NULL ORDER BY unlocked_at DESC LIMIT 1"),
        {"uid": subject_id},
    ).mappings().first()
    for defn in ACHIEVEMENT_DEFINITIONS:
        aid = defn["id"]
        row = db_by_id.get(aid)
        progress = int(row["progress"]) if row else 0
        target = int(defn["target"])
        unlocked = bool(row["unlocked"]) if row else (progress >= target)
        unlocked_at = row["unlocked_at"].isoformat() if row and row.get("unlocked_at") else None
        if unlocked:
            total_points += RARITY_POINTS.get(defn.get("rarity", "common"), 10)
        entry = {
            "id": aid,
            "name": defn["name"],
            "nameEn": defn["nameEn"],
            "description": defn["description"],
            "descriptionEn": defn["descriptionEn"],
            "icon": defn["icon"],
            "category": defn["category"],
            "progress": progress,
            "target": target,
            "unlocked": unlocked,
            "unlockedAt": unlocked_at,
            "rarity": defn["rarity"],
        }
        achievements_out.append(entry)
        if recent_row and str(recent_row["achievement_id"]) == aid:
            recent_unlock = entry
    return {"achievements": achievements_out, "totalPoints": total_points, "recentUnlock": recent_unlock}


class AchievementProgressReq(BaseModel):
    achievement_id: str
    progress: int


@router.post("/achievements/progress")
def bff_achievements_progress(
    payload: AchievementProgressReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Upsert achievement progress; set unlocked when progress >= target."""
    subject_id = ident.subject_id
    defn = next((d for d in ACHIEVEMENT_DEFINITIONS if d["id"] == payload.achievement_id), None)
    if not defn:
        raise HTTPException(status_code=404, detail="Achievement not found")
    target = int(defn["target"])
    progress = min(max(0, payload.progress), target)
    unlocked = progress >= target
    now = _now_utc()
    unlocked_at = now if unlocked else None
    db.execute(
        text("""
            INSERT INTO user_achievements (user_id, achievement_id, progress, target, unlocked, unlocked_at, created_at, updated_at)
            VALUES (:uid, :aid, :progress, :target, :unlocked, :unlocked_at, :now, :now)
            ON CONFLICT (user_id, achievement_id)
            DO UPDATE SET progress = EXCLUDED.progress, unlocked = EXCLUDED.unlocked,
                           unlocked_at = CASE WHEN EXCLUDED.unlocked AND user_achievements.unlocked_at IS NULL THEN EXCLUDED.unlocked_at ELSE user_achievements.unlocked_at END,
                           updated_at = EXCLUDED.updated_at
        """),
        {"uid": subject_id, "aid": payload.achievement_id, "progress": progress, "target": target, "unlocked": unlocked, "unlocked_at": unlocked_at, "now": now},
    )
    db.commit()
    return {"achievement_id": payload.achievement_id, "progress": progress, "unlocked": unlocked, "unlocked_at": unlocked_at.isoformat() if unlocked_at else None}


# ─── Career summary for advisor (Gap 8) ───────────────────────────────────────

@router.get("/career-summary")
def bff_career_summary(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """One-pager summary for HKU Career Centre: skill gaps, top actions, link to export statement."""
    subject_id = ident.subject_id
    snapshot = _build_profile_skills_snapshot(db, subject_id, skill_limit=30)
    gap_names: List[str] = [
        s["canonical_name"] for s in snapshot
        if (s.get("label") or "").lower() in ("not_enough_information", "not_assessed", "")
    ]

    first_doc = db.execute(
        text("""
            SELECT d.doc_id::text FROM documents d
            JOIN consents c ON c.doc_id = d.doc_id::text
            WHERE c.user_id = :sub AND c.status = 'granted'
            ORDER BY d.created_at DESC LIMIT 1
        """),
        {"sub": subject_id},
    ).scalar()
    top_actions: List[str] = []
    if first_doc:
        from backend.app.routers.actions import recommend_actions, ActionRecommendRequest
        try:
            req = ActionRecommendRequest(doc_id=first_doc, role_id=None, skill_ids=None)
            result = recommend_actions(req=req, db=db, ident=ident)
            actions = result.get("actions") or []
            for a in actions[:3]:
                title = a.get("title") or "Action"
                top_actions.append(f"- {title}")
        except Exception:
            pass
    actions_block = "\n".join(top_actions) if top_actions else "(Complete an assessment to see actions.)"
    summary_text = (
        "SkillSight – Summary for HKU Career Centre\n"
        "==========================================\n\n"
        f"Skills with gaps or not yet evidenced: {', '.join(gap_names) or 'None identified.'}\n\n"
        "Top recommended actions:\n" + actions_block
        + "\n\nView your full skills statement and evidence in the Export / Certificate page."
    )
    base = os.getenv("SKILLSIGHT_APP_URL") or os.getenv("BFF_BACKEND_URL") or ""
    export_url = f"{base.rstrip('/')}/export" if base else ""
    return {"summary": summary_text, "gap_skills": gap_names, "top_actions": top_actions, "export_statement_url": export_url}


# ─── Leaderboard (Gap 11) ─────────────────────────────────────────────────────

@router.get("/leaderboard")
def bff_leaderboard(
    top_n: int = 10,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Anonymous leaderboard: my_rank, my_points, top N by total achievement points."""
    subject_id = ident.subject_id
    rarity_to_points = RARITY_POINTS
    defn_by_id = {d["id"]: d for d in ACHIEVEMENT_DEFINITIONS}
    rows = db.execute(
        text("SELECT user_id, achievement_id FROM user_achievements WHERE unlocked = TRUE"),
    ).mappings().all()
    user_points: Dict[str, int] = {}
    for r in rows:
        uid = str(r["user_id"])
        aid = str(r["achievement_id"])
        rarity = defn_by_id.get(aid, {}).get("rarity", "common")
        user_points[uid] = user_points.get(uid, 0) + rarity_to_points.get(rarity, 10)
    sorted_users = sorted(user_points.items(), key=lambda x: -x[1])
    my_points = user_points.get(subject_id, 0)
    my_rank = None
    for i, (uid, _) in enumerate(sorted_users, 1):
        if uid == subject_id:
            my_rank = i
            break
    top = [{"rank": i, "points": pts} for i, (_, pts) in enumerate(sorted_users[: max(1, min(top_n, 50))], 1)]
    return {"my_rank": my_rank, "my_points": my_points, "top": top}


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
                c.consent_id, c.doc_id, c.status,
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
        items.append({
            "consent_id": str(row["consent_id"]),
            "doc_id": row["doc_id"],
            "filename": row.get("filename") or row["doc_id"],
            "doc_type": row.get("doc_type"),
            "purpose": "skill_assessment",
            "scope": "full",
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


# ─── Resume Enhancement Center ──────────────────────────────────────────────────

@router.get("/resume-templates")
def bff_student_resume_templates(
    role_id: Optional[str] = None,
    industry: Optional[str] = None,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List resume templates for the Resume Enhancement Center."""
    rows = db.execute(
        text("""
            SELECT template_id, name, description, industry_tags, preview_url, template_file, is_active
            FROM resume_templates
            WHERE is_active = TRUE
            ORDER BY name
            LIMIT 50
        """),
    ).mappings().all()
    templates = []
    for r in rows:
        d = dict(r)
        if d.get("template_id"):
            d["template_id"] = str(d["template_id"])
        if isinstance(d.get("industry_tags"), str):
            try:
                d["industry_tags"] = json.loads(d["industry_tags"])
            except Exception:
                d["industry_tags"] = []
        templates.append(d)
    if not templates:
        templates = [
            {
                "template_id": "__professional_classic",
                "name": "Professional Classic",
                "description": "Clean single-column layout with centered header and horizontal rules. ATS-friendly design ideal for traditional industries.",
                "industry_tags": ["finance", "consulting", "corporate"],
                "preview_url": "",
                "template_file": "professional_classic.docx",
                "is_active": True,
            },
            {
                "template_id": "__modern_tech",
                "name": "Modern Tech",
                "description": "Two-column layout with dark sidebar for skills and contact. Contemporary design popular on LinkedIn for tech roles.",
                "industry_tags": ["technology", "engineering", "software"],
                "preview_url": "",
                "template_file": "modern_tech.docx",
                "is_active": True,
            },
            {
                "template_id": "__creative_portfolio",
                "name": "Creative Portfolio",
                "description": "Bold purple accents with large first-letter styling and Georgia serif font. Expressive layout for creative professionals.",
                "industry_tags": ["marketing", "design", "creative"],
                "preview_url": "",
                "template_file": "creative_portfolio.docx",
                "is_active": True,
            },
            {
                "template_id": "__academic_research",
                "name": "Academic CV",
                "description": "Formal Curriculum Vitae format with Times New Roman and structured indentation. Standard for academic and research positions.",
                "industry_tags": ["research", "academia", "education"],
                "preview_url": "",
                "template_file": "academic_research.docx",
                "is_active": True,
            },
            {
                "template_id": "__executive",
                "name": "Executive",
                "description": "Premium navy and gold design with Cambria font and generous spacing. Refined elegance for senior leadership roles.",
                "industry_tags": ["leadership", "executive", "management"],
                "preview_url": "",
                "template_file": "executive.docx",
                "is_active": True,
            },
            {
                "template_id": "__minimalist_clean",
                "name": "Minimalist Clean",
                "description": "Ultra-clean monochrome layout with maximum whitespace and Calibri Light font. Lets your content speak for itself.",
                "industry_tags": ["any industry", "startup", "modern"],
                "preview_url": "",
                "template_file": "minimalist_clean.docx",
                "is_active": True,
            },
            {
                "template_id": "__corporate_elegance",
                "name": "Corporate Elegance",
                "description": "Teal header block with single-column body layout. ATS-friendly corporate style for business and operations roles.",
                "industry_tags": ["business", "operations", "corporate"],
                "preview_url": "",
                "template_file": "corporate_elegance.docx",
                "is_active": True,
            },
            {
                "template_id": "__fresh_graduate",
                "name": "Fresh Graduate",
                "description": "Compact layout with blue header bar, skills-first ordering, and inline skill formatting. Designed for students and early-career professionals.",
                "industry_tags": ["entry-level", "student", "internship"],
                "preview_url": "",
                "template_file": "fresh_graduate.docx",
                "is_active": True,
            },
        ]
    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.resume.templates.list",
        object_type="resume_templates",
        object_id="",
        status="ok",
        detail={"count": len(templates)},
    )
    return {"templates": templates}


@router.get("/resume-reviews")
def bff_student_resume_reviews(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List current user's resume reviews (paginated)."""
    subject_id = ident.subject_id
    limit = min(max(1, limit), 50)
    offset = max(0, offset)
    total_row = db.execute(
        text("SELECT COUNT(*) FROM resume_reviews WHERE user_id = :uid"),
        {"uid": subject_id},
    ).scalar()
    total = int(total_row or 0)
    rows = db.execute(
        text("""
            SELECT review_id, doc_id, target_role_id, status, total_initial, total_final, created_at
            FROM resume_reviews
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"uid": subject_id, "lim": limit, "off": offset},
    ).mappings().all()
    reviews = []
    for r in rows:
        d = dict(r)
        if d.get("review_id"):
            d["review_id"] = str(d["review_id"])
        if d.get("created_at") is not None:
            d["created_at"] = d["created_at"].isoformat() if hasattr(d["created_at"], "isoformat") else d["created_at"]
        reviews.append(d)
    return {"reviews": reviews, "total": total}


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

def _make_verification_token(subject_id: str, generated_at: str, skills_summary: str) -> str:
    """Create HMAC-signed token for certificate verification (Gap 12)."""
    secret = (os.getenv("EXPORT_VERIFY_SECRET") or "skillsight-export-verify-default").encode("utf-8")
    payload = json.dumps({"subject_id": subject_id, "generated_at": generated_at, "skills_hash": hashlib.sha256(skills_summary.encode("utf-8")).hexdigest()}, sort_keys=True)
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).digest()
    raw = payload.encode("utf-8") + b"." + sig
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


EXPORT_VERIFY_MAX_AGE_DAYS = int(os.getenv("EXPORT_VERIFY_MAX_AGE_DAYS", "365"))


def _verify_statement_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify token and return payload dict or None if invalid. Sets _expired=True when signature is valid but statement is older than EXPORT_VERIFY_MAX_AGE_DAYS."""
    if not token:
        return None
    try:
        padded = token + "=" * (4 - len(token) % 4)
        raw = base64.urlsafe_b64decode(padded)
        payload_b, sig_b = raw.rsplit(b".", 1)
        secret = (os.getenv("EXPORT_VERIFY_SECRET") or "skillsight-export-verify-default").encode("utf-8")
        expected = hmac.new(secret, payload_b, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, sig_b):
            return None
        payload = json.loads(payload_b.decode("utf-8"))
        generated_at_str = (payload.get("generated_at") or "")[:10]
        if generated_at_str and len(generated_at_str) >= 10:
            try:
                gen_date = datetime.strptime(generated_at_str, "%Y-%m-%d").date()
                now_date = datetime.now(timezone.utc).date()
                if (now_date - gen_date).days > EXPORT_VERIFY_MAX_AGE_DAYS:
                    payload["_expired"] = True
            except ValueError:
                pass
        return payload
    except Exception:
        return None


@router.get("/export/statement")
async def bff_export_statement(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Generate one-page skills statement for download.
    Includes: skill claims + evidence items, sources, timestamps.
    Returns verification_token for GET /export/verify?token=...
    """
    profile = await bff_student_profile(db=db, ident=ident)

    total_evidence = sum(len(s.get("evidence_items", [])) for s in profile.get("skills", []))
    demonstrated = [s for s in profile.get("skills", []) if s.get("label") in ("demonstrated", "mentioned")]

    generated_at = _now_utc().isoformat()
    skills_summary = json.dumps([{"skill_id": s.get("skill_id"), "label": s.get("label")} for s in profile.get("skills", [])], sort_keys=True)
    verification_token = _make_verification_token(ident.subject_id, generated_at, skills_summary)

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
        "generated_at": generated_at,
        "verification_token": verification_token,
        "statement": {
            "total_skills_assessed": len(profile.get("skills", [])),
            "demonstrated_skills": len(demonstrated),
            "total_evidence_items": total_evidence,
            "documents": profile.get("documents", []),
            "skills": profile.get("skills", []),
        },
    }


@router.get("/export/verify")
def bff_export_verify(token: str = ""):
    """
    Public endpoint: verify a statement token (no auth).
    Returns 200 with minimal payload (valid statement from YYYY-MM-DD for subject) or 400 if invalid.
    """
    payload = _verify_statement_token(token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    if payload.get("_expired"):
        raise HTTPException(status_code=400, detail="Statement expired, please regenerate.")
    subject_id = payload.get("subject_id", "")
    generated_at = (payload.get("generated_at") or "")[:10]
    return {"valid": True, "message": f"Valid statement from {generated_at} for subject.", "subject_id": subject_id, "generated_at": generated_at}


# ─── Tutor dialogue (Live Agent + RAG) ───────────────────────────────────────

class TutorSessionStartReq(BaseModel):
    skill_id: str
    doc_ids: Optional[List[str]] = None
    mode: Optional[str] = "assessment"  # "assessment" | "resume_review"


class TutorMessageReq(BaseModel):
    content: str


def _get_skill_for_tutor(db: Session, skill_id: str) -> Optional[Dict[str, Any]]:
    """Get skill with rubric (same as ai._get_skill)."""
    from backend.app.routers.ai import _get_skill
    return _get_skill(db, skill_id)


def _build_profile_skills_snapshot(db: Session, subject_id: str, skill_limit: int = 30) -> List[Dict[str, Any]]:
    """
    Single query surface for skill list + latest assessment label + latest proficiency level.
    Returns list of {skill_id, canonical_name, label, level} for use in career-summary, resume_review summary, etc.
    """
    skills_rows = db.execute(
        text("SELECT skill_id, canonical_name FROM skills ORDER BY canonical_name LIMIT :lim"),
        {"lim": skill_limit},
    ).mappings().all()
    if not skills_rows:
        return []
    # Latest assessment per skill (consented docs only); dedupe by skill_id keeping latest
    ass_rows = db.execute(
        text("""
            SELECT sa.skill_id, sa.decision
            FROM skill_assessments sa
            JOIN consents c ON c.doc_id = sa.doc_id::text AND c.user_id = :sub AND c.status = 'granted'
            ORDER BY sa.created_at DESC
        """),
        {"sub": subject_id},
    ).mappings().all()
    ass_by_sid: Dict[str, str] = {}
    for r in ass_rows:
        sid = str(r["skill_id"])
        if sid not in ass_by_sid:
            ass_by_sid[sid] = (r.get("decision") or "not_assessed")
    # Latest proficiency per skill (consented docs only)
    prof_rows = db.execute(
        text("""
            SELECT sp.skill_id, sp.level
            FROM skill_proficiency sp
            JOIN consents c ON c.doc_id = sp.doc_id::text AND c.user_id = :sub AND c.status = 'granted'
            ORDER BY sp.created_at DESC
        """),
        {"sub": subject_id},
    ).mappings().all()
    prof_by_sid: Dict[str, Optional[int]] = {}
    for r in prof_rows:
        sid = str(r["skill_id"])
        if sid not in prof_by_sid:
            prof_by_sid[sid] = int(r["level"]) if r.get("level") is not None else None
    out: List[Dict[str, Any]] = []
    for s in skills_rows:
        sid = str(s["skill_id"])
        out.append({
            "skill_id": sid,
            "canonical_name": s.get("canonical_name") or sid,
            "label": ass_by_sid.get(sid) or "not_assessed",
            "level": prof_by_sid.get(sid),
        })
    return out


def _build_student_skill_summary(db: Session, subject_id: str) -> str:
    """Build a short summary of the student's verified skills and levels for resume_review context. Uses profile snapshot."""
    snapshot = _build_profile_skills_snapshot(db, subject_id, skill_limit=25)
    parts: List[str] = []
    for s in snapshot:
        name = s.get("canonical_name") or s["skill_id"]
        level = s.get("level")
        label = s.get("label") or "not_assessed"
        if level is not None:
            parts.append(f"- {name}: level {level} ({label})")
        else:
            parts.append(f"- {name}: {label} (no level yet)")
    if not parts:
        return "No skills assessed yet; student has not run assessments on uploaded documents."
    return "\n".join(parts)


def _rag_retrieve_for_tutor(
    skill_definition: str,
    doc_ids: List[str],
    top_k: int = 8,
    request_id: str = "",
) -> List[Dict[str, Any]]:
    """Retrieve evidence chunks for tutor context; merge results from each doc."""
    from backend.app.retrieval_pipeline import retrieve_evidence, RetrievalItem
    merged: List[tuple] = []
    query = (skill_definition or "").strip() or "skill evidence"
    for doc_id in doc_ids[:20]:
        result = retrieve_evidence(
            query,
            doc_filter=doc_id,
            top_k=5,
            use_reranker=False,
            include_snippet=True,
            request_id=request_id,
        )
        for item in result.items:
            merged.append((item.score, item))
    merged.sort(key=lambda x: -x[0])
    seen = set()
    out = []
    for _, item in merged[:top_k]:
        if item.chunk_id in seen:
            continue
        seen.add(item.chunk_id)
        out.append({
            "chunk_id": item.chunk_id,
            "doc_id": item.doc_id,
            "score": item.score,
            "snippet": (item.snippet or "")[:400],
        })
    return out


@router.post("/tutor-session/start")
def bff_tutor_session_start(
    payload: TutorSessionStartReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """
    Start a tutor dialogue session for a skill (evidence-insufficient follow-up) or resume review.
    Optionally pass doc_ids; otherwise uses all consented docs for the user.
    mode: "assessment" (default) or "resume_review".
    """
    user_id = ident.subject_id
    mode = (payload.mode or "assessment").strip().lower()
    if mode not in ("assessment", "resume_review"):
        mode = "assessment"
    doc_ids = list(payload.doc_ids) if payload.doc_ids else []
    if not doc_ids:
        rows = db.execute(
            text("""
                SELECT d.doc_id::text
                FROM documents d
                JOIN consents c ON c.doc_id = d.doc_id::text
                WHERE c.user_id = :sub AND c.status = 'granted'
            """),
            {"sub": user_id},
        ).mappings().all()
        doc_ids = [r["doc_id"] for r in rows]
    for doc_id in doc_ids:
        _check_consent(db, doc_id, user_id)
    from backend.app.services import tutor_dialogue as svc
    session_id = svc.create_session(db, user_id, payload.skill_id, doc_ids, mode=mode)
    log_audit(
        engine,
        subject_id=user_id,
        action="bff.student.tutor_session.start",
        object_type="tutor_session",
        object_id=session_id,
        status="ok",
        detail={"skill_id": payload.skill_id, "doc_count": len(doc_ids), "mode": mode},
    )
    return {"session_id": session_id, "skill_id": payload.skill_id, "doc_ids": doc_ids, "mode": mode}


@router.get("/tutor-session/{session_id}")
def bff_tutor_session_get(
    session_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Get tutor session and dialogue history."""
    from backend.app.services import tutor_dialogue as svc
    session = svc.get_session(db, session_id, ident.subject_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    turns = svc.get_turns(db, session_id)
    return {
        "session_id": session_id,
        "skill_id": session["skill_id"],
        "doc_ids": session.get("doc_ids") or [],
        "status": session.get("status", "active"),
        "mode": session.get("mode", "assessment"),
        "created_at": session.get("created_at").isoformat() if session.get("created_at") else None,
        "turns": [{"role": t["role"], "content": t["content"], "created_at": (t.get("created_at") or _now_utc()).isoformat() if t.get("created_at") else None} for t in turns],
    }


@router.post("/tutor-session/{session_id}/message")
def bff_tutor_session_message(
  session_id: str,
  payload: TutorMessageReq,
  db: Session = Depends(get_db),
  ident: Identity = Depends(require_auth),
):
    """
    Send a message in a tutor session; RAG retrieval + OpenAI chat; persist turn and optional assessment.
    Returns { reply, concluded, assessment? }.
    """
    from backend.app.services import tutor_dialogue as svc
    from backend.app.openai_client import openai_chat

    user_id = ident.subject_id
    session = svc.get_session(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("status") == "concluded":
        raise HTTPException(status_code=400, detail="Session already concluded")

    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=422, detail="content is required")

    doc_ids = session.get("doc_ids") or []
    skill_id = session["skill_id"]
    mode = session.get("mode") or "assessment"

    if mode == "resume_review":
        skill_def = "Resume and career feedback."
        rubric_summary = ""
        student_skill_summary = _build_student_skill_summary(db, user_id)
        chunks = _rag_retrieve_for_tutor("resume experience skills", doc_ids, top_k=8, request_id=str(uuid.uuid4()))
    else:
        student_skill_summary = None
        skill = _get_skill_for_tutor(db, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        skill_def = (skill.get("definition") or "")[:2000]
        chunks = _rag_retrieve_for_tutor(skill_def, doc_ids, top_k=8, request_id=str(uuid.uuid4()))
        rubric = skill.get("level_rubric") or skill.get("level_rubric_json")
        if isinstance(rubric, str):
            try:
                rubric = json.loads(rubric) if rubric else {}
            except Exception:
                rubric = {}
        rubric_summary = json.dumps(rubric, ensure_ascii=False)[:1500] if rubric else "Levels 0-3: novice, developing, proficient, advanced."

    evidence_lines = [f"- {c['chunk_id']}: {c['snippet']}" for c in chunks]
    evidence_text = "\n".join(evidence_lines) if evidence_lines else "(No evidence chunks retrieved.)"

    doc_count = len(doc_ids) if doc_ids else 0
    verified_skills_count = None
    if mode == "resume_review" and student_skill_summary:
        verified_skills_count = len([ln for ln in student_skill_summary.split("\n") if ln.strip().startswith("-")])

    # Append user turn first
    svc.append_turn(db, session_id, "user", content)

    # Build messages (context + history + this turn already in history as last user)
    messages = svc.get_messages_for_llm(
        db, session_id, skill_def, rubric_summary, evidence_text, mode=mode,
        student_skill_summary=student_skill_summary if mode == "resume_review" else None,
        doc_count=doc_count,
        verified_skills_count=verified_skills_count,
    )
    # Last message is the user's current one; openai_chat will use it
    reply_text = ""
    try:
        reply_text = openai_chat(
            messages,
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.3,
            stream=False,
        )
    except Exception as e:
        _log.warning("tutor openai_chat failed: %s", e)
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")

    reply_text = (reply_text or "").strip()
    chunk_ids_used = [c["chunk_id"] for c in chunks]
    svc.append_turn(db, session_id, "assistant", reply_text, chunk_ids_used)

    assessment = None
    concluded = False
    if mode == "assessment":
        parsed = svc.parse_assessment_from_reply(reply_text)
        if parsed:
            concluded = True
            svc.conclude_and_persist_assessment(
                db, session_id, user_id,
                level=parsed["level"],
                evidence_chunk_ids=parsed["evidence_chunk_ids"],
                why=parsed.get("why") or "Tutor dialogue conclusion.",
            )
            assessment = {"level": parsed["level"], "evidence_chunk_ids": parsed["evidence_chunk_ids"], "why": parsed.get("why")}

    log_audit(
        engine,
        subject_id=user_id,
        action="bff.student.tutor_session.message",
        object_type="tutor_session",
        object_id=session_id,
        status="ok",
        detail={"concluded": concluded},
    )
    return {"reply": reply_text, "concluded": concluded, "assessment": assessment}
