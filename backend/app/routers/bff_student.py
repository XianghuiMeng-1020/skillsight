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
import io
import json
import logging
import os
import re
import uuid
import base64
from urllib.parse import urlparse
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
from backend.app.services.learning_path_recommender import recommend_learning_path
from backend.app.services.market_analytics import market_skill_trends, salary_reference

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
    except Exception:
        _log.exception("Failed to embed chunks for doc_id=%s", doc_id)
        raise HTTPException(status_code=500, detail="Failed to embed document chunks")

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


class GithubImportReq(BaseModel):
    repo_url: str


def _parse_github_repo(repo_url: str) -> Optional[Dict[str, str]]:
    try:
        parsed = urlparse(repo_url.strip())
    except Exception:
        return None
    if parsed.netloc not in ("github.com", "www.github.com"):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    return {"owner": parts[0], "repo": parts[1].replace(".git", "")}


@router.post("/documents/import-github")
async def bff_import_github_repo(
    payload: GithubImportReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    parsed = _parse_github_repo(payload.repo_url)
    if not parsed:
        raise HTTPException(status_code=422, detail="Invalid GitHub repository URL")

    owner = parsed["owner"]
    repo = parsed["repo"]
    api = "https://api.github.com"
    async with httpx.AsyncClient(timeout=20.0) as client:
        readme_res = await client.get(f"{api}/repos/{owner}/{repo}/readme", headers={"Accept": "application/vnd.github.raw"})
        commits_res = await client.get(f"{api}/repos/{owner}/{repo}/commits?per_page=20")
        tree_res = await client.get(f"{api}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1")
    if readme_res.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Cannot access README for {owner}/{repo}")

    readme_text = readme_res.text[:20000]
    commit_msgs: List[str] = []
    if commits_res.status_code < 400:
        try:
            for c in commits_res.json()[:20]:
                message = str((c.get("commit") or {}).get("message") or "").strip()
                if message:
                    commit_msgs.append(message.splitlines()[0][:200])
        except Exception:
            commit_msgs = []

    files: List[str] = []
    if tree_res.status_code < 400:
        try:
            for item in (tree_res.json().get("tree") or [])[:300]:
                if item.get("type") == "blob":
                    files.append(str(item.get("path")))
        except Exception:
            files = []

    assembled = "\n".join(
        [
            f"Repository: {owner}/{repo}",
            f"URL: {payload.repo_url}",
            "",
            "README:",
            readme_text,
            "",
            "Recent commits:",
            *[f"- {m}" for m in commit_msgs[:20]],
            "",
            "File list:",
            *[f"- {f}" for f in files[:300]],
        ]
    )

    from backend.app.routers.documents import import_document_txt
    virtual_file = UploadFile(filename=f"github_{owner}_{repo}.txt", file=io.BytesIO(assembled.encode("utf-8")))
    result = await import_document_txt(file=virtual_file, db=db, ident=ident)
    return {
        "repo": f"{owner}/{repo}",
        "doc_id": result.get("doc_id"),
        "chunks_created": result.get("chunks_created", 0),
        "filename": result.get("filename", f"github_{owner}_{repo}.txt"),
    }


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
    except Exception:
        db.rollback()
        _log.exception("Failed to persist assessment for skill_id=%s", payload.skill_id)
        raise HTTPException(status_code=500, detail="Failed to persist assessment")

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
        text(
            """
            WITH user_skills AS (
                SELECT DISTINCT sp.skill_id
                FROM skill_proficiency sp
                JOIN consents c ON c.doc_id = sp.doc_id::text
                WHERE c.user_id = :sub AND c.status = 'granted'

                UNION

                SELECT DISTINCT sa.skill_id
                FROM skill_assessments sa
                JOIN consents c ON c.doc_id = sa.doc_id::text
                WHERE c.user_id = :sub AND c.status = 'granted'

                UNION

                SELECT DISTINCT s.skill_id
                FROM skill_assessment_snapshots s
                WHERE s.subject_id = :sub
            )
            SELECT sk.skill_id, sk.canonical_name, sk.definition
            FROM skills sk
            JOIN user_skills us ON us.skill_id = sk.skill_id
            ORDER BY sk.canonical_name
            LIMIT 50
            """
        ),
        {"sub": subject},
    ).mappings().all()
    if not skills_rows:
        # Backward-compatible fallback for brand new users without any assessments.
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

        # Frequency-based evidence: count all chunks across all consented
        # docs that mention this skill, and collect evidence_sources with
        # snippet + source filename for the explainability UI.
        evidence_sources: List[Dict[str, Any]] = []
        frequency = 0
        try:
            freq_rows = db.execute(
                text("""
                    SELECT ch.chunk_id, ch.snippet, ch.doc_id, d.filename
                    FROM chunks ch
                    JOIN documents d ON d.doc_id = ch.doc_id
                    JOIN consents c ON c.doc_id = d.doc_id::text
                    JOIN skill_assessments sa
                        ON sa.doc_id = ch.doc_id::text
                       AND sa.skill_id = :sid
                    WHERE c.user_id = :sub AND c.status = 'granted'
                      AND sa.decision IN ('demonstrated', 'match', 'mentioned')
                      AND (
                          sa.evidence::text LIKE '%%' || ch.chunk_id || '%%'
                      )
                    ORDER BY d.filename, ch.chunk_id
                    LIMIT 50
                """),
                {"sid": skill_id, "sub": subject},
            ).mappings().all()
            frequency = len(freq_rows)
            for fr in freq_rows:
                evidence_sources.append({
                    "chunk_id": fr["chunk_id"],
                    "snippet": (fr["snippet"] or "")[:300],
                    "doc_id": fr["doc_id"],
                    "filename": fr["filename"] or "unknown",
                })
        except Exception as exc:
            _log.debug("frequency evidence query failed for skill %s: %s", skill_id, exc)
            frequency = len(evidence_items)
            for ei in evidence_items:
                doc_row = db.execute(
                    text("SELECT filename FROM documents WHERE doc_id = :did LIMIT 1"),
                    {"did": ei["doc_id"]},
                ).mappings().first()
                evidence_sources.append({
                    "chunk_id": ei["chunk_id"],
                    "snippet": ei["snippet"],
                    "doc_id": ei["doc_id"],
                    "filename": (doc_row["filename"] if doc_row else "unknown"),
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
            "frequency": frequency,
            "evidence_sources": evidence_sources,
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

    recent_role_events: List[Dict[str, Any]] = []
    try:
        rows = db.execute(
            text(
                """
                SELECT rr.role_id, r.role_title, rr.score, rr.created_at
                FROM role_readiness rr
                LEFT JOIN roles r ON r.role_id = rr.role_id
                JOIN consents c ON c.doc_id = rr.doc_id::text
                WHERE c.user_id = :uid AND c.status = 'granted'
                ORDER BY rr.created_at DESC
                LIMIT 6
                """
            ),
            {"uid": subject},
        ).mappings().all()
        for r in rows:
            evt = {
                "role_id": str(r.get("role_id") or ""),
                "role_title": str(r.get("role_title") or r.get("role_id") or ""),
                "score": float(r.get("score") or 0),
                "created_at": r.get("created_at").isoformat() if r.get("created_at") and hasattr(r.get("created_at"), "isoformat") else None,
            }
            recent_role_events.append(evt)
    except Exception as exc:
        _log.warning("role readiness events query failed: %s", exc)
        recent_role_events = []

    recent_export_events: List[Dict[str, Any]] = []
    try:
        rows = db.execute(
            text(
                """
                SELECT action, created_at
                FROM audit_logs
                WHERE subject_id = :uid
                  AND action IN ('bff.export.statement', 'bff.export.credential')
                ORDER BY created_at DESC
                LIMIT 6
                """
            ),
            {"uid": subject},
        ).mappings().all()
        for r in rows:
            recent_export_events.append(
                {
                    "action": str(r.get("action") or ""),
                    "created_at": r.get("created_at").isoformat() if r.get("created_at") and hasattr(r.get("created_at"), "isoformat") else None,
                }
            )
    except Exception as exc:
        _log.warning("export events query failed: %s", exc)
        recent_export_events = []

    stale_skills: List[Dict[str, Any]] = []
    try:
        rows = db.execute(
            text(
                """
                WITH latest_skill AS (
                    SELECT DISTINCT ON (sp.skill_id)
                        sp.skill_id, sp.label, sp.level, sp.created_at
                    FROM skill_proficiency sp
                    JOIN consents c ON c.doc_id = sp.doc_id::text
                    WHERE c.user_id = :uid AND c.status = 'granted'
                    ORDER BY sp.skill_id, sp.created_at DESC
                )
                SELECT ls.skill_id, ls.label, ls.level, ls.created_at, s.canonical_name
                FROM latest_skill ls
                LEFT JOIN skills s ON s.skill_id = ls.skill_id
                WHERE ls.created_at < (now() - interval '90 days')
                ORDER BY ls.created_at ASC
                LIMIT 20
                """
            ),
            {"uid": subject},
        ).mappings().all()
        for r in rows:
            stale_skills.append(
                {
                    "skill_id": str(r.get("skill_id") or ""),
                    "skill_name": str(r.get("canonical_name") or r.get("skill_id") or ""),
                    "level": int(r.get("level") or 0),
                    "label": str(r.get("label") or ""),
                    "last_updated_at": r.get("created_at").isoformat() if r.get("created_at") and hasattr(r.get("created_at"), "isoformat") else None,
                }
            )
    except Exception as exc:
        _log.warning("stale skills query failed: %s", exc)
        stale_skills = []

    return {
        "subject_id": subject,
        "documents_count": len(doc_rows),
        "documents": [dict(d) for d in doc_rows],
        "skills": skills_profile,
        "recent_assessment_events": recent_assessment_events,
        "recent_role_events": recent_role_events,
        "recent_export_events": recent_export_events,
        "stale_skills": stale_skills,
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


class InterviewPrepReq(BaseModel):
    role_id: str
    question_count: int = 5


# Scoring constants/heuristics live in backend.app.services.role_match_scoring
# so the heavy and light paths cannot drift apart.  We re-export the legacy
# constant names that the rest of this module references to keep the diff
# small.
from backend.app.services.role_match_scoring import (
    MUST_WEIGHT_BOOST as READINESS_MUST_WEIGHT_BOOST,
    OPTIONAL_WEIGHT_FACTOR as READINESS_OPTIONAL_WEIGHT_FACTOR,
    MENTIONED_FLOOR as READINESS_MENTIONED_FLOOR,
    RECENCY_HALF_LIFE_DAYS as READINESS_RECENCY_HALF_LIFE_DAYS,
    RECENCY_MIN_FACTOR as READINESS_RECENCY_MIN_FACTOR,
    MET_THRESHOLD as READINESS_MET_THRESHOLD,
    RoleRequirement as _RoleRequirement,
    StudentSkill as _StudentSkill,
    score_role as _score_role,
    canonicalize as _canon,
    normalize_skill_label as _normalize_skill_label,
)
from backend.app.services import concept_graph as _concept_graph

READINESS_CRITICAL_GAP_THRESHOLD = 0.45  # legacy; kept for any callers


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


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

    # 1+2) Get best assessment decision + proficiency level per skill via consented docs
    assess_sql = text("""
        SELECT DISTINCT ON (sa.skill_id)
            sa.skill_id, sa.decision,
            COALESCE(sp.level, 0) AS level,
            sa.created_at AS assessed_at
        FROM skill_assessments sa
        JOIN consents c ON c.doc_id = sa.doc_id::text AND c.user_id = :sub AND c.status = 'granted'
        LEFT JOIN skill_proficiency sp
            ON sp.skill_id = sa.skill_id AND sp.doc_id = sa.doc_id
        ORDER BY sa.skill_id,
            CASE sa.decision WHEN 'demonstrated' THEN 1 WHEN 'match' THEN 1 WHEN 'mentioned' THEN 2 ELSE 3 END,
            sa.created_at DESC
    """)
    assess_rows = db.execute(assess_sql, {"sub": ident.subject_id}).mappings().all()
    skill_map: Dict[str, Dict] = {}
    for r in assess_rows:
        decision = r["decision"] or ""
        raw_level = int(r["level"]) if r["level"] is not None else 0
        # If demonstrated but no proficiency level recorded, infer level 2
        if decision in ("demonstrated", "match") and raw_level == 0:
            raw_level = 2
        elif decision == "mentioned" and raw_level == 0:
            raw_level = 1
        skill_map[r["skill_id"]] = {
            "decision": decision,
            "level": raw_level,
            "assessed_at": r.get("assessed_at"),
        }

    # 3) Get role titles + descriptions (description feeds the soft-requirement bonus)
    from sqlalchemy.sql import bindparam as bp2
    # last_seen_at is optional — if the freshness migration hasn't run
    # yet the column won't exist, so we try the rich query first and
    # fall back to the legacy projection on any error.
    role_titles: Dict[str, str] = {}
    role_descriptions: Dict[str, str] = {}
    role_last_seen: Dict[str, Any] = {}
    role_meta_sql_full = text(
        "SELECT role_id, role_title, description, last_seen_at "
        "FROM roles WHERE role_id IN :rids"
    ).bindparams(bp2("rids", expanding=True))
    role_meta_sql_legacy = text(
        "SELECT role_id, role_title, description "
        "FROM roles WHERE role_id IN :rids"
    ).bindparams(bp2("rids", expanding=True))
    try:
        meta_rows = db.execute(role_meta_sql_full, {"rids": tuple(role_ids)}).mappings().all()
        for r in meta_rows:
            rid = str(r["role_id"])
            role_titles[rid] = str(r["role_title"])
            role_descriptions[rid] = str(r.get("description") or "")
            role_last_seen[rid] = r.get("last_seen_at")
    except Exception:
        meta_rows = db.execute(role_meta_sql_legacy, {"rids": tuple(role_ids)}).mappings().all()
        for r in meta_rows:
            rid = str(r["role_id"])
            role_titles[rid] = str(r["role_title"])
            role_descriptions[rid] = str(r.get("description") or "")

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

    # Build a StudentSkill list once (canonical lookup happens inside the
    # scorer).  We need a name for each skill_id so aliases/adjacency can
    # work on free-text labels rather than opaque ids.
    skill_name_sql = text(
        "SELECT skill_id, canonical_name FROM skills WHERE skill_id IN :sids"
    ).bindparams(bp2("sids", expanding=True))
    student_skill_ids = [sid for sid in skill_map.keys() if sid]
    student_skill_names: Dict[str, str] = {}
    if student_skill_ids:
        try:
            for r in db.execute(
                skill_name_sql, {"sids": tuple(student_skill_ids)}
            ).mappings():
                student_skill_names[str(r["skill_id"])] = str(r["canonical_name"] or r["skill_id"])
        except Exception:
            student_skill_names = {}

    student_skills = [
        _StudentSkill(
            skill_id=sid,
            skill_name=student_skill_names.get(sid, sid),
            decision=info.get("decision", ""),
            achieved_level=int(info.get("level") or 0),
            assessed_at=info.get("assessed_at"),
        )
        for sid, info in skill_map.items()
    ]

    # Pull DB-backed concept graph (falls back to in-code defaults if
    # the migration hasn't been applied yet).
    try:
        cg_aliases = _concept_graph.get_aliases(engine)
        cg_adjacency = _concept_graph.get_adjacency(engine)
    except Exception as exc:  # never let loader errors break the API
        _log.warning("concept_graph load failed (%s); using in-code defaults", exc)
        cg_aliases = None
        cg_adjacency = None

    now_utc = _now_utc()
    items = []
    for rid in role_ids:
        reqs = role_reqs.get(rid, [])
        role_title = role_titles.get(rid, "")
        if not reqs:
            items.append({
                "role_id": rid,
                "role_title": role_title,
                "readiness": 0,
                "match_class": "below",
            })
            continue

        requirements = [
            _RoleRequirement(
                skill_id=str(r["skill_id"]),
                skill_name=str(r.get("skill_name") or r["skill_id"]),
                target_level=int(r["target_level"]) if r["target_level"] is not None else 2,
                required=bool(r["required"]),
                weight=float(r["weight"]) if r["weight"] is not None else 1.0,
            )
            for r in reqs
        ]

        result = _score_role(
            role_id=rid,
            role_title=role_title,
            requirements=requirements,
            student_skills=student_skills,
            now_utc=now_utc,
            aliases=cg_aliases,
            adjacency=cg_adjacency,
            role_description=role_descriptions.get(rid),
            role_last_seen_at=role_last_seen.get(rid),
        )

        # Backward-compatible projection of the scorer result.
        required_skills_all = [r.skill_name for r in requirements]
        required_skills_must = [r.skill_name for r in requirements if r.required]
        required_skills_optional = [r.skill_name for r in requirements if not r.required]
        all_gaps = result.critical_gaps + result.improvable_gaps

        next_best_assessment: Optional[Dict[str, str]] = None
        for it in result.items:
            if it.met:
                continue
            next_best_assessment = {
                "skill_id": str(it.skill_id),
                "skill_name": it.skill_name,
                "reason": "critical_gap" if it.required else "improvable_gap",
            }
            break

        items.append({
            "role_id": rid,
            "role_title": role_title,
            "readiness": result.readiness,
            "raw_readiness": result.raw_readiness,
            "match_class": result.match_class,
            "skills_met": result.skills_met,
            "skills_total": result.skills_total,
            "skills_met_must": result.skills_met_must,
            "skills_total_must": result.skills_total_must,
            "skills_met_optional": result.skills_met_optional,
            "skills_total_optional": result.skills_total_optional,
            "match_ratio_must": result.match_ratio_must,
            "gaps": all_gaps[:3],
            "gaps_all": all_gaps,
            "critical_gaps": result.critical_gaps,
            "improvable_gaps": result.improvable_gaps,
            "required_skills": required_skills_all,
            "required_skills_all": required_skills_all,
            "required_skills_must": required_skills_must,
            "required_skills_optional": required_skills_optional,
            "adjacent_credits": result.adjacent_credits,
            "next_best_assessment": next_best_assessment,
            "freshness_label": result.freshness_label,
            "freshness_age_days": result.freshness_age_days,
            "rank_score": result.rank_score,
            "last_seen_at": (
                role_last_seen.get(rid).isoformat()
                if role_last_seen.get(rid) is not None
                and hasattr(role_last_seen.get(rid), "isoformat")
                else None
            ),
        })

    return {"items": items, "count": len(items)}


# ─── Match feedback (ground-truth signal for future calibration) ──────────────


class MatchFeedbackReq(BaseModel):
    role_id: str
    verdict: str  # "good" | "bad" | "unsure"
    readiness: Optional[float] = None
    match_class: Optional[str] = None
    note: Optional[str] = None


@router.post("/match/feedback")
def bff_match_feedback(
    payload: MatchFeedbackReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Capture per-user thumbs up/down on a role-match recommendation.

    Stored in ``match_feedback``.  Falls through gracefully if the table
    hasn't been migrated yet so the FE never sees a 500.
    """
    verdict = (payload.verdict or "").strip().lower()
    if verdict not in {"good", "bad", "unsure"}:
        raise HTTPException(status_code=400, detail="verdict must be good|bad|unsure")
    role_id = (payload.role_id or "").strip()
    if not role_id:
        raise HTTPException(status_code=400, detail="role_id required")

    try:
        db.execute(
            text(
                """
                INSERT INTO match_feedback
                    (subject_id, role_id, verdict, readiness, match_class, note)
                VALUES
                    (:sid, :rid, :v, :rd, :mc, :note)
                """
            ),
            {
                "sid": ident.subject_id,
                "rid": role_id,
                "v": verdict,
                "rd": float(payload.readiness) if payload.readiness is not None else None,
                "mc": payload.match_class,
                "note": (payload.note or None),
            },
        )
        db.commit()
        log_audit(
            engine,
            subject_id=ident.subject_id,
            action="bff.student.match.feedback",
            object_type="role",
            object_id=role_id,
            status="ok",
            detail={"verdict": verdict, "readiness": payload.readiness},
        )
        return {"ok": True}
    except Exception as exc:
        db.rollback()
        # Most likely the migration hasn't been applied yet — never break the FE.
        _log.warning("match_feedback insert failed (likely missing table): %s", exc)
        return {"ok": False, "reason": "feedback_unavailable"}


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


@router.post("/interview-prep")
def bff_interview_prep(
    payload: InterviewPrepReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    role = db.execute(
        text("SELECT role_id, role_title, description FROM roles WHERE role_id = :rid LIMIT 1"),
        {"rid": payload.role_id},
    ).mappings().first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    req_rows = db.execute(
        text(
            """
            SELECT rsr.skill_id, rsr.target_level, COALESCE(s.canonical_name, rsr.skill_id) AS skill_name
            FROM role_skill_requirements rsr
            LEFT JOIN skills s ON s.skill_id = rsr.skill_id
            WHERE rsr.role_id = :rid
            ORDER BY rsr.weight DESC, rsr.required DESC
            LIMIT 20
            """
        ),
        {"rid": payload.role_id},
    ).mappings().all()
    my_rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (sp.skill_id) sp.skill_id, sp.level
            FROM skill_proficiency sp
            JOIN consents c ON c.doc_id = sp.doc_id::text
            WHERE c.user_id = :uid AND c.status = 'granted'
            ORDER BY sp.skill_id, sp.created_at DESC
            """
        ),
        {"uid": ident.subject_id},
    ).mappings().all()
    my_level = {str(r["skill_id"]): int(r.get("level") or 0) for r in my_rows}
    gaps = []
    for r in req_rows:
        sid = str(r["skill_id"])
        target = int(r.get("target_level") or 2)
        achieved = my_level.get(sid, 0)
        if achieved < target:
            gaps.append({"skill_id": sid, "skill_name": str(r.get("skill_name") or sid), "target": target, "achieved": achieved})
    if not gaps:
        gaps = [{"skill_id": str(r["skill_id"]), "skill_name": str(r.get("skill_name") or r["skill_id"]), "target": int(r.get("target_level") or 2), "achieved": my_level.get(str(r["skill_id"]), 0)} for r in req_rows[:3]]
    questions = []
    for g in gaps[: max(1, min(payload.question_count, 10))]:
        questions.append(
            {
                "skill_id": g["skill_id"],
                "skill_name": g["skill_name"],
                "question": f"For {role.get('role_title')}, describe a real project where you demonstrated {g['skill_name']}. What was the challenge, your approach, and measurable result?",
            }
        )
    return {"role_id": role["role_id"], "role_title": role.get("role_title"), "questions": questions, "count": len(questions)}


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
        except Exception as exc:
            _log.warning("career summary recommend_actions failed: %s", exc)
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
    defn_by_id = {d["id"]: d for d in ACHIEVEMENT_DEFINITIONS}
    case_branches: List[str] = []
    params: Dict[str, Any] = {}
    for idx, aid in enumerate(defn_by_id.keys()):
        params[f"aid_{idx}"] = aid
        rarity = defn_by_id.get(aid, {}).get("rarity", "common")
        points = RARITY_POINTS.get(rarity, 10)
        case_branches.append(f"WHEN achievement_id = :aid_{idx} THEN {points}")
    case_expr = "CASE " + " ".join(case_branches) + " ELSE 10 END"
    rows = db.execute(
        text(
            f"""
            SELECT user_id, SUM({case_expr}) AS points
            FROM user_achievements
            WHERE unlocked = TRUE
            GROUP BY user_id
            ORDER BY points DESC, user_id ASC
            """
        ),
        params,
    ).mappings().all()
    sorted_users = [(str(r["user_id"]), int(r.get("points") or 0)) for r in rows]
    my_points = next((pts for uid, pts in sorted_users if uid == subject_id), 0)
    my_rank = next((i for i, (uid, _) in enumerate(sorted_users, 1) if uid == subject_id), None)
    top = [{"rank": i, "points": pts} for i, (_, pts) in enumerate(sorted_users[: max(1, min(top_n, 50))], 1)]
    return {"my_rank": my_rank, "my_points": my_points, "top": top}


@router.get("/peer-benchmark")
def bff_peer_benchmark(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Anonymous peer percentile by skill.

    Lookup priority for current user's skills:
    1. skill_proficiency joined via consents (granted) — standard path
    2. skill_proficiency joined via documents (ownership) — fallback when no consents
    3. skill_proficiency by subject_id direct column — if schema supports it

    Peer comparison uses all skill_proficiency rows regardless of consent status,
    so percentile is meaningful even with a small user base.
    """
    # --- Try standard path (consents) first ---
    me_rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (sp.skill_id) sp.skill_id, sp.level
            FROM skill_proficiency sp
            JOIN consents c ON c.doc_id = sp.doc_id::text
            WHERE c.user_id = :uid AND c.status = 'granted'
            ORDER BY sp.skill_id, sp.created_at DESC
            """
        ),
        {"uid": ident.subject_id},
    ).mappings().all()

    # --- Fallback: skill_assessment_snapshots which has subject_id directly ---
    use_snapshots = False
    if not me_rows:
        snap_rows = db.execute(
            text(
                """
                SELECT DISTINCT ON (skill_id) skill_id, level
                FROM skill_assessment_snapshots
                WHERE subject_id = :uid AND level IS NOT NULL
                ORDER BY skill_id, created_at DESC
                """
            ),
            {"uid": ident.subject_id},
        ).mappings().all()
        if snap_rows:
            me_rows = snap_rows
            use_snapshots = True

    # Build a set of user's skill IDs for filtering
    user_skill_ids = [str(r["skill_id"]) for r in me_rows]
    if not user_skill_ids:
        return {"count": 0, "items": []}

    # Single query with window function to compute percentiles for all user's skills
    if use_snapshots:
        pct_sql = text("""
            WITH latest AS (
                SELECT DISTINCT ON (subject_id, skill_id)
                    subject_id, skill_id, level
                FROM skill_assessment_snapshots
                WHERE skill_id = ANY(:sids) AND level IS NOT NULL
                ORDER BY subject_id, skill_id, created_at DESC
            ),
            stats AS (
                SELECT
                    skill_id,
                    level,
                    COUNT(*) OVER (PARTITION BY skill_id) AS total,
                    COUNT(*) OVER (PARTITION BY skill_id ORDER BY level) AS cum_count
                FROM latest
            )
            SELECT
                skill_id,
                ROUND(100.0 * MAX(cum_count) / NULLIF(MAX(total), 0), 2) AS pct,
                MAX(level) AS max_level
            FROM stats
            GROUP BY skill_id
        """)
    else:
        pct_sql = text("""
            WITH latest AS (
                SELECT DISTINCT ON (c.user_id, sp.skill_id)
                    c.user_id, sp.skill_id, sp.level
                FROM skill_proficiency sp
                JOIN consents c ON c.doc_id = sp.doc_id::text
                WHERE c.status = 'granted' AND sp.skill_id = ANY(:sids)
                ORDER BY c.user_id, sp.skill_id, sp.created_at DESC
            ),
            stats AS (
                SELECT
                    skill_id,
                    level,
                    COUNT(*) OVER (PARTITION BY skill_id) AS total,
                    COUNT(*) OVER (PARTITION BY skill_id ORDER BY level) AS cum_count
                FROM latest
            )
            SELECT
                skill_id,
                ROUND(100.0 * MAX(cum_count) / NULLIF(MAX(total), 0), 2) AS pct,
                MAX(level) AS max_level
            FROM stats
            GROUP BY skill_id
        """)

    pct_rows = db.execute(pct_sql, {"sids": user_skill_ids}).mappings().all()
    pct_by_sid: Dict[str, float] = {str(r["skill_id"]): float(r["pct"]) for r in pct_rows if r["pct"]}
    level_by_sid: Dict[str, int] = {str(r["skill_id"]): int(r["max_level"]) for r in pct_rows if r["max_level"]}

    # Map user's levels to their skill IDs
    user_level_by_sid = {str(r["skill_id"]): int(r["level"] or 0) for r in me_rows}

    out = [
        {
            "skill_id": sid,
            "level": user_level_by_sid.get(sid, 0),
            "percentile": pct_by_sid.get(sid)
        }
        for sid in user_skill_ids
    ]
    return {"count": len(out), "items": out}


@router.get("/learning-path")
def bff_learning_path(
    limit: int = 8,
    target_role_id: Optional[str] = None,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    items = recommend_learning_path(db, ident.subject_id, limit=limit, target_role_id=target_role_id)
    return {"count": len(items), "items": items}


@router.get("/market-insights")
def bff_market_insights(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    trends = market_skill_trends(db, limit=12)
    salary = salary_reference(db)
    total_postings = db.execute(
        text("SELECT COUNT(*) FROM job_postings WHERE status = 'active'")
    ).scalar() or 0
    return {"trends": trends, "salary_reference": salary, "source_postings_count": int(total_postings)}


@router.get("/jobs-live")
def bff_jobs_live(
    q: Optional[str] = None,
    source_site: Optional[str] = None,
    limit: int = 30,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    safe_limit = max(1, min(limit, 100))
    where: List[str] = ["status = 'active'"]
    params: Dict[str, Any] = {"lim": safe_limit}
    if q:
        where.append("(title ILIKE :q OR company ILIKE :q OR description ILIKE :q)")
        params["q"] = f"%{q}%"
    if source_site:
        where.append("source_site = :source_site")
        params["source_site"] = source_site
    where_sql = " AND ".join(where)
    # Total count (without limit) for frontend pagination display
    count_params = {k: v for k, v in params.items() if k != "lim"}
    total_count = db.execute(
        text(f"SELECT COUNT(*) FROM job_postings WHERE {where_sql}"),
        count_params,
    ).scalar() or 0

    rows = db.execute(
        text(
            f"""
            SELECT posting_id, source_site, title, company, location, salary, source_url, description, snapshot_at
            FROM job_postings
            WHERE {where_sql}
            ORDER BY snapshot_at DESC
            LIMIT :lim
            """
        ),
        params,
    ).mappings().all()

    # Get user skills from consents path first, then skill_assessment_snapshots fallback
    my_rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (sp.skill_id) sp.skill_id, sp.level, s.canonical_name
            FROM skill_proficiency sp
            JOIN consents c ON c.doc_id = sp.doc_id::text
            LEFT JOIN skills s ON s.skill_id = sp.skill_id
            WHERE c.user_id = :uid AND c.status = 'granted'
            ORDER BY sp.skill_id, sp.created_at DESC
            """
        ),
        {"uid": ident.subject_id},
    ).mappings().all()

    if not my_rows:
        # Fallback: use skill_assessment_snapshots for skill names
        my_rows = db.execute(
            text(
                """
                SELECT DISTINCT ON (skill_id) skill_id, level,
                       REPLACE(REPLACE(skill_id, 'HKU.SKILL.', ''), '.v1', '') AS canonical_name
                FROM skill_assessment_snapshots
                WHERE subject_id = :uid AND level IS NOT NULL AND level > 0
                ORDER BY skill_id, created_at DESC
                """
            ),
            {"uid": ident.subject_id},
        ).mappings().all()

    my_skill_names = [str(r.get("canonical_name") or "") for r in my_rows if int(r.get("level") or 0) > 0]
    my_skill_names = [s.replace("_", " ").strip().lower() for s in my_skill_names if s]
    my_skill_patterns = [
        re.compile(rf"(?<!\w){re.escape(skill)}(?!\w)")
        for skill in my_skill_names
        if skill
    ]

    items: List[Dict[str, Any]] = []
    for row in rows:
        desc = f"{row.get('title', '')}\n{row.get('description', '')}".lower()
        matched = [
            skill
            for skill, pattern in zip(my_skill_names, my_skill_patterns)
            if pattern.search(desc)
        ]
        denom = max(1, min(len(my_skill_names), 10))
        score = round((len(matched) / denom) * 100, 1) if my_skill_names else 0.0
        item = dict(row)
        if item.get("snapshot_at") and hasattr(item.get("snapshot_at"), "isoformat"):
            item["snapshot_at"] = item["snapshot_at"].isoformat()
        item["match_score"] = score
        item["matched_skills"] = matched[:6]
        items.append(item)
    return {"count": int(total_count), "items": items}


@router.get("/notifications")
def bff_notifications(
    limit: int = 20,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    rows = db.execute(
        text(
            """
            SELECT notification_id, title, message, source_url, is_read, created_at
            FROM notifications
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT :lim
            """
        ),
        {"uid": ident.subject_id, "lim": max(1, min(limit, 100))},
    ).mappings().all()
    items = []
    for r in rows:
        item = dict(r)
        if item.get("created_at") and hasattr(item["created_at"], "isoformat"):
            item["created_at"] = item["created_at"].isoformat()
        items.append(item)
    unread = sum(1 for i in items if not i.get("is_read"))
    return {"count": len(items), "unread_count": unread, "items": items}


@router.post("/notifications/{notification_id}/read")
def bff_mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    db.execute(
        text(
            """
            UPDATE notifications
            SET is_read = TRUE
            WHERE notification_id = :nid AND user_id = :uid
            """
        ),
        {"nid": notification_id, "uid": ident.subject_id},
    )
    db.commit()
    return {"ok": True}


class MentorCommentReq(BaseModel):
    subject_id: str
    skill_id: str
    comment: str


@router.post("/collaboration/mentor-comment")
def bff_add_mentor_comment(
    payload: MentorCommentReq,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    if ident.role not in ("staff", "admin", "programme"):
        raise HTTPException(status_code=403, detail="Only staff/admin can add mentor comments")
    subject_id = (payload.subject_id or "").strip()
    if not subject_id:
        raise HTTPException(status_code=422, detail="subject_id is required")
    db.execute(
        text(
            """
            INSERT INTO mentor_comments (comment_id, subject_id, skill_id, comment, created_by, created_at)
            VALUES (:cid, :sid, :skill_id, :comment, :created_by, :now)
            """
        ),
        {
            "cid": str(uuid.uuid4()),
            "sid": subject_id,
            "skill_id": payload.skill_id,
            "comment": payload.comment[:2000],
            "created_by": ident.subject_id,
            "now": _now_utc(),
        },
    )
    db.commit()
    return {"ok": True}


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
    review_id: Optional[str] = None,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """List resume templates for the Resume Enhancement Center. Optional review_id ranks templates for target role."""
    from backend.app.services.resume_structured import score_templates_for_role

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

    role_title: Optional[str] = None
    if review_id and review_id.strip():
        row = db.execute(
            text("""
                SELECT ro.role_title AS role_title
                FROM resume_reviews r
                LEFT JOIN roles ro ON ro.role_id = r.target_role_id
                WHERE r.review_id = :rid AND r.user_id = :uid
                LIMIT 1
            """),
            {"rid": review_id.strip(), "uid": ident.subject_id},
        ).mappings().first()
        if row and row.get("role_title"):
            role_title = str(row["role_title"])
    if not role_title and role_id and role_id.strip():
        rt = db.execute(
            text("SELECT role_title FROM roles WHERE role_id = :rid LIMIT 1"),
            {"rid": role_id.strip()},
        ).scalar()
        if rt:
            role_title = str(rt)

    if not templates:
        templates = [
            {
                "template_id": "__professional_classic",
                "name": "Professional Classic",
                "description": "Clean single-column layout with centered header and horizontal rules. ATS-friendly design ideal for traditional industries.",
                "industry_tags": ["finance", "consulting", "corporate"],
                "preview_url": "/resume-templates/professional_classic.png",
                "template_file": "professional_classic.docx",
                "is_active": True,
            },
            {
                "template_id": "__modern_tech",
                "name": "Modern Tech",
                "description": "Two-column layout with dark sidebar for skills and contact. Contemporary design popular on LinkedIn for tech roles.",
                "industry_tags": ["technology", "engineering", "software"],
                "preview_url": "/resume-templates/modern_tech.png",
                "template_file": "modern_tech.docx",
                "is_active": True,
            },
            {
                "template_id": "__creative_portfolio",
                "name": "Creative Portfolio",
                "description": "Bold purple accents with large first-letter styling and Georgia serif font. Expressive layout for creative professionals.",
                "industry_tags": ["marketing", "design", "creative"],
                "preview_url": "/resume-templates/creative_portfolio.png",
                "template_file": "creative_portfolio.docx",
                "is_active": True,
            },
            {
                "template_id": "__academic_research",
                "name": "Academic CV",
                "description": "Formal Curriculum Vitae format with Times New Roman and structured indentation. Standard for academic and research positions.",
                "industry_tags": ["research", "academia", "education"],
                "preview_url": "/resume-templates/academic_research.png",
                "template_file": "academic_research.docx",
                "is_active": True,
            },
            {
                "template_id": "__executive",
                "name": "Executive",
                "description": "Premium navy and gold design with Cambria font and generous spacing. Refined elegance for senior leadership roles.",
                "industry_tags": ["leadership", "executive", "management"],
                "preview_url": "/resume-templates/executive.png",
                "template_file": "executive.docx",
                "is_active": True,
            },
            {
                "template_id": "__minimalist_clean",
                "name": "Minimalist Clean",
                "description": "Ultra-clean monochrome layout with maximum whitespace and Calibri Light font. Lets your content speak for itself.",
                "industry_tags": ["any industry", "startup", "modern"],
                "preview_url": "/resume-templates/minimalist_clean.png",
                "template_file": "minimalist_clean.docx",
                "is_active": True,
            },
            {
                "template_id": "__corporate_elegance",
                "name": "Corporate Elegance",
                "description": "Teal header block with single-column body layout. ATS-friendly corporate style for business and operations roles.",
                "industry_tags": ["business", "operations", "corporate"],
                "preview_url": "/resume-templates/corporate_elegance.png",
                "template_file": "corporate_elegance.docx",
                "is_active": True,
            },
            {
                "template_id": "__fresh_graduate",
                "name": "Fresh Graduate",
                "description": "Compact layout with blue header bar, skills-first ordering, and inline skill formatting. Designed for students and early-career professionals.",
                "industry_tags": ["entry-level", "student", "internship"],
                "preview_url": "/resume-templates/fresh_graduate.png",
                "template_file": "fresh_graduate.docx",
                "is_active": True,
            },
        ]

    templates = score_templates_for_role(templates, role_title)

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


@router.get("/export/credential")
async def bff_export_credential(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """W3C-like lightweight verifiable credential payload."""
    statement = await bff_export_statement(db=db, ident=ident)
    issued = _now_utc().isoformat()
    credential = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "type": ["VerifiableCredential", "SkillSightCredential"],
        "issuer": "did:web:skillsight.hku.hk",
        "issuanceDate": issued,
        "credentialSubject": {
            "id": f"did:skillsight:{ident.subject_id}",
            "subject_id": ident.subject_id,
            "skills_summary": statement.get("statement", {}).get("skills", [])[:20],
        },
        "proof": {
            "type": "HmacProof2026",
            "token": statement.get("verification_token"),
        },
    }
    return {"credential": credential, "share_hint": "You can attach this credential when sharing to LinkedIn."}


@router.get("/timeline/export-report")
async def bff_export_timeline_report(
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    profile = await bff_student_profile(db=db, ident=ident)
    lines: List[str] = []
    for doc in profile.get("documents", []) or []:
        created_at = str(doc.get("created_at") or "")[:19]
        lines.append(f"{created_at}  Uploaded document: {doc.get('filename')}")
    for evt in profile.get("recent_assessment_events", []) or []:
        created_at = str(evt.get("created_at") or evt.get("completed_at") or "")[:19]
        lines.append(f"{created_at}  Completed assessment: {evt.get('assessment_type')} (score={evt.get('score')})")
    for evt in profile.get("recent_role_events", []) or []:
        created_at = str(evt.get("created_at") or "")[:19]
        lines.append(f"{created_at}  Role readiness refreshed: {evt.get('role_title')} ({evt.get('score')})")
    for evt in profile.get("recent_export_events", []) or []:
        created_at = str(evt.get("created_at") or "")[:19]
        action = str(evt.get("action") or "").replace("bff.export.", "")
        lines.append(f"{created_at}  Exported: {action}")
    if not lines:
        lines = ["No timeline events yet."]
    lines = sorted(lines, reverse=True)

    try:
        import fitz  # pymupdf
        pdf = fitz.open()
        page = pdf.new_page(width=595, height=842)
        y = 50
        page.insert_text((50, y), f"SkillSight Growth Report - {ident.subject_id}", fontsize=14)
        y += 24
        page.insert_text((50, y), f"Generated at: {_now_utc().isoformat()}", fontsize=10)
        y += 24
        for line in lines[:48]:
            page.insert_text((50, y), f"- {line}", fontsize=9)
            y += 14
            if y > 800:
                page = pdf.new_page(width=595, height=842)
                y = 40
        data = pdf.write()
        pdf.close()
        return {
            "filename": f"skillsight_growth_report_{ident.subject_id}.pdf",
            "mime_type": "application/pdf",
            "content_base64": base64.b64encode(data).decode("ascii"),
            "events_count": len(lines),
        }
    except Exception as exc:
        # Fallback text payload when PDF engine is unavailable.
        payload = "\n".join(lines)
        return {
            "filename": f"skillsight_growth_report_{ident.subject_id}.txt",
            "mime_type": "text/plain",
            "content_base64": base64.b64encode(payload.encode("utf-8")).decode("ascii"),
            "events_count": len(lines),
            "fallback": True,
            "reason": str(exc),
        }


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
    Single CTE query for skill list + latest assessment label + latest proficiency level.
    Returns list of {skill_id, canonical_name, label, level} for use in career-summary, resume_review summary, etc.
    """
    cte_sql = text("""
        WITH skills_list AS (
            SELECT skill_id, canonical_name FROM skills ORDER BY canonical_name LIMIT :lim
        ),
        latest_ass AS (
            SELECT DISTINCT ON (sa.skill_id)
                sa.skill_id,
                sa.decision
            FROM skill_assessments sa
            JOIN consents c ON c.doc_id = sa.doc_id::text AND c.user_id = :sub AND c.status = 'granted'
            ORDER BY sa.skill_id, sa.created_at DESC
        ),
        latest_prof AS (
            SELECT DISTINCT ON (sp.skill_id)
                sp.skill_id,
                sp.level
            FROM skill_proficiency sp
            JOIN consents c ON c.doc_id = sp.doc_id::text AND c.user_id = :sub AND c.status = 'granted'
            ORDER BY sp.skill_id, sp.created_at DESC
        )
        SELECT
            s.skill_id,
            s.canonical_name,
            COALESCE(la.decision, 'not_assessed') AS label,
            lp.level
        FROM skills_list s
        LEFT JOIN latest_ass la ON la.skill_id = s.skill_id
        LEFT JOIN latest_prof lp ON lp.skill_id = s.skill_id
        ORDER BY s.canonical_name
    """)
    rows = db.execute(cte_sql, {"lim": skill_limit, "sub": subject_id}).mappings().all()
    return [
        {
            "skill_id": str(r["skill_id"]),
            "canonical_name": r.get("canonical_name") or str(r["skill_id"]),
            "label": r["label"],
            "level": int(r["level"]) if r.get("level") is not None else None,
        }
        for r in rows
    ]


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
    except Exception:
        _log.exception("Tutor LLM request failed for session_id=%s", session_id)
        raise HTTPException(status_code=502, detail="LLM request failed")

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


@router.post("/tutor-session/{session_id}/end")
def bff_tutor_session_end(
    session_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Allow the client to end a tutor session when turn limit is reached or the user wants to stop."""
    from backend.app.services import tutor_dialogue as svc

    session = svc.get_session(db, session_id, ident.subject_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("status") == "concluded":
        return {"success": True, "already_concluded": True}

    svc.set_session_concluded(db, session_id)
    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.student.tutor_session.end",
        object_type="tutor_session",
        object_id=session_id,
        status="ok",
        detail={"mode": session.get("mode", "assessment")},
    )
    return {"success": True, "already_concluded": False}
