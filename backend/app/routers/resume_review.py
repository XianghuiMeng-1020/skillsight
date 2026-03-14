"""
BFF Student – Resume Enhancement Center.
Routes: /bff/student/resume-review/*

All endpoints require auth. Document access is validated via consent.
"""
from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.audit import log_audit
from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.refusal import make_refusal
from backend.app.security import Identity, require_auth
from backend.app.services.resume_enhancer import generate_suggestions as enhancer_generate_suggestions
from backend.app.services.resume_scorer import (
    get_resume_text_from_doc,
    score_resume,
)
from backend.app.services.resume_template_service import apply_template as template_apply

router = APIRouter(prefix="/resume-review", tags=["resume-review"])
_log = logging.getLogger(__name__)


def _now_utc():
    return datetime.now(timezone.utc)


def _check_consent(db: Session, doc_id: str, subject_id: str) -> None:
    """Raise 403 if user does not have granted consent for doc_id."""
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
                f"Consent for this document is '{row['status']}'.",
                "Re-upload with consent or restore it.",
            ),
        )


def _get_review_for_user(db: Session, review_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Return review row if it belongs to user_id."""
    row = db.execute(
        text("""
            SELECT review_id, user_id, doc_id, target_role_id, status,
                   initial_scores, final_scores, total_initial, total_final,
                   accepted_count, rejected_count, template_id, created_at, updated_at
            FROM resume_reviews
            WHERE review_id = :rid AND user_id = :uid
            LIMIT 1
        """),
        {"rid": review_id, "uid": user_id},
    ).mappings().first()
    return dict(row) if row else None


# ─── Request/Response models ────────────────────────────────────────────────────

class StartRequest(BaseModel):
    doc_id: str = Field(..., max_length=256)
    target_role_id: Optional[str] = Field(None, max_length=256)


class PatchSuggestionRequest(BaseModel):
    status: Literal["accepted", "rejected", "edited"]
    student_edit: Optional[str] = Field(None, max_length=50000)


class ApplyTemplateRequest(BaseModel):
    template_id: str = Field(..., max_length=256)


# ─── POST /resume-review/start ───────────────────────────────────────────────────

@router.post("/start")
def resume_review_start(
    payload: StartRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Create a new resume review session. Validates doc consent."""
    subject_id = ident.subject_id
    doc_id = payload.doc_id.strip()
    if not doc_id:
        raise HTTPException(status_code=400, detail={"error": "doc_id_required", "message": "doc_id is required"})
    _check_consent(db, doc_id, subject_id)
    # Ensure document exists and has chunks (optional: allow empty for later upload)
    review_id = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO resume_reviews (review_id, user_id, doc_id, target_role_id, status, created_at, updated_at)
            VALUES (:rid, :uid, :doc_id, :target_role_id, 'scoring', :now, :now)
        """),
        {
            "rid": review_id,
            "uid": subject_id,
            "doc_id": doc_id,
            "target_role_id": payload.target_role_id or None,
            "now": _now_utc(),
        },
    )
    db.commit()
    log_audit(
        engine,
        subject_id=subject_id,
        action="bff.resume.start",
        object_type="resume_review",
        object_id=review_id,
        status="ok",
        detail={"doc_id": doc_id},
    )
    return {"review_id": review_id, "status": "scoring"}


# ─── POST /resume-review/{review_id}/score ───────────────────────────────────────

@router.post("/{review_id}/score")
def resume_review_score(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Trigger AI scoring for the review's document. Persists initial_scores and total_initial."""
    subject_id = ident.subject_id
    review = _get_review_for_user(db, review_id, subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") != "scoring":
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_state", "message": "Scoring already done or invalid step. Start a new review."},
        )
    doc_id = review["doc_id"]
    _check_consent(db, doc_id, subject_id)
    resume_text = get_resume_text_from_doc(db, doc_id)
    if not (resume_text and len(resume_text.strip()) >= 100):
        raise HTTPException(
            status_code=400,
            detail={"error": "no_chunks", "message": "Document not yet parsed or content too short. Please try again later."},
        )
    try:
        result = score_resume(
            db,
            doc_id=doc_id,
            user_id=subject_id,
            target_role_id=review.get("target_role_id"),
        )
    except ValueError as e:
        err = str(e)
        if err == "resume_too_short":
            raise HTTPException(
                status_code=400,
                detail={"error": "resume_too_short", "message": "Resume content is too short. Please upload a complete resume."},
            ) from e
        if err == "llm_parse_error":
            raise HTTPException(
                status_code=422,
                detail={"error": "llm_parse_error", "message": "AI could not parse the response. Please try again."},
            ) from e
        raise HTTPException(status_code=400, detail={"error": "validation", "message": err}) from e
    except RuntimeError as e:
        _log.exception("Resume score failed")
        raise HTTPException(
            status_code=502,
            detail={"error": "llm_timeout", "message": str(e), "retry": True},
        ) from e
    scores = result["scores"]
    total = result["total"]
    db.execute(
        text("""
            UPDATE resume_reviews
            SET initial_scores = :scores, total_initial = :total, status = 'reviewed', updated_at = :now
            WHERE review_id = :rid AND user_id = :uid
        """),
        {
            "rid": review_id,
            "uid": subject_id,
            "scores": json.dumps(scores),
            "total": float(total),
            "now": _now_utc(),
        },
    )
    db.commit()
    log_audit(
        engine,
        subject_id=subject_id,
        action="bff.resume.score",
        object_type="resume_review",
        object_id=review_id,
        status="ok",
        detail={"total_initial": total},
    )
    return {"initial_scores": scores, "total_initial": total, "total_final": None, "final_scores": None}


# ─── GET /resume-review/{review_id}/score ────────────────────────────────────────

@router.get("/{review_id}/score")
def resume_review_get_score(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Return current initial and final scores for the review."""
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    initial = review.get("initial_scores")
    final = review.get("final_scores")
    if isinstance(initial, str):
        try:
            initial = json.loads(initial)
        except Exception:
            initial = None
    if isinstance(final, str):
        try:
            final = json.loads(final)
        except Exception:
            final = None
    return {
        "initial_scores": initial,
        "final_scores": final,
        "total_initial": review.get("total_initial"),
        "total_final": review.get("total_final"),
    }


# ─── POST /resume-review/{review_id}/suggest ─────────────────────────────────────

@router.post("/{review_id}/suggest")
def resume_review_suggest(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Generate AI suggestions and persist to resume_suggestions. Returns list of suggestions."""
    subject_id = ident.subject_id
    review = _get_review_for_user(db, review_id, subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") != "reviewed":
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_state", "message": "Run scoring first."},
        )
    # Prevent duplicate suggestion runs
    existing = db.execute(
        text("SELECT 1 FROM resume_suggestions WHERE review_id = :rid LIMIT 1"),
        {"rid": review_id},
    ).scalar()
    if existing:
        raise HTTPException(
            status_code=400,
            detail={"error": "suggestions_already_generated", "message": "Suggestions already generated for this review."},
        )
    initial_scores = review.get("initial_scores")
    if isinstance(initial_scores, str):
        try:
            initial_scores = json.loads(initial_scores)
        except Exception:
            initial_scores = {}
    if not initial_scores:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_scores", "message": "Run scoring first."},
        )
    resume_text = get_resume_text_from_doc(db, review["doc_id"])
    if not resume_text or len(resume_text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_chunks", "message": "Document content not available."},
        )
    try:
        suggestions = enhancer_generate_suggestions(
            db,
            user_id=subject_id,
            resume_text=resume_text,
            scoring_json=initial_scores,
            target_role_id=review.get("target_role_id"),
        )
    except ValueError as e:
        if str(e) == "llm_parse_error":
            raise HTTPException(
                status_code=422,
                detail={"error": "llm_parse_error", "message": "AI could not generate suggestions. Please try again."},
            ) from e
        raise HTTPException(status_code=400, detail={"error": "validation", "message": str(e)}) from e
    except RuntimeError as e:
        _log.exception("Resume suggest failed")
        raise HTTPException(
            status_code=502,
            detail={"error": "llm_timeout", "message": str(e), "retry": True},
        ) from e
    now = _now_utc()
    out = []
    for s in suggestions:
        sid = str(uuid.uuid4())
        db.execute(
            text("""
                INSERT INTO resume_suggestions (suggestion_id, review_id, dimension, section, original_text, suggested_text, explanation, priority, status, created_at)
                VALUES (:sid, :rid, :dim, :section, :orig, :sug, :expl, :pri, 'pending', :now)
            """),
            {
                "sid": sid,
                "rid": review_id,
                "dim": s["dimension"],
                "section": s.get("section"),
                "orig": s.get("original_text"),
                "sug": s.get("suggested_text"),
                "expl": s.get("explanation"),
                "pri": s.get("priority", "medium"),
                "now": now,
            },
        )
        out.append({
            "suggestion_id": sid,
            "dimension": s["dimension"],
            "section": s.get("section"),
            "original_text": s.get("original_text"),
            "suggested_text": s.get("suggested_text"),
            "explanation": s.get("explanation"),
            "priority": s.get("priority", "medium"),
            "status": "pending",
        })
    db.commit()
    log_audit(
        engine,
        subject_id=subject_id,
        action="bff.resume.suggest",
        object_type="resume_review",
        object_id=review_id,
        status="ok",
        detail={"count": len(out)},
    )
    return {"suggestions": out}


# ─── GET /resume-review/{review_id}/suggestions ──────────────────────────────────

@router.get("/{review_id}/suggestions")
def resume_review_get_suggestions(
    review_id: str,
    priority: Optional[str] = None,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Return all suggestions for the review, optionally filtered by priority."""
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    sql = """
        SELECT suggestion_id, review_id, dimension, section, original_text, suggested_text, explanation, priority, status, student_edit, created_at
        FROM resume_suggestions
        WHERE review_id = :rid
    """
    params: Dict[str, Any] = {"rid": review_id}
    if priority and priority.strip().lower() in ("high", "medium", "low"):
        sql += " AND priority = :pri"
        params["pri"] = priority.strip().lower()
    sql += " ORDER BY created_at ASC"
    rows = db.execute(text(sql), params).mappings().all()
    suggestions = [dict(r) for r in rows]
    for s in suggestions:
        if "suggestion_id" in s and s["suggestion_id"]:
            s["suggestion_id"] = str(s["suggestion_id"])
    return {"suggestions": suggestions}


# ─── PATCH /resume-review/{review_id}/suggestion/{suggestion_id} ─────────────────

@router.patch("/{review_id}/suggestion/{suggestion_id}")
def resume_review_patch_suggestion(
    review_id: str,
    suggestion_id: str,
    payload: PatchSuggestionRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Update a suggestion's status (accepted | rejected | edited) and optional student_edit."""
    subject_id = ident.subject_id
    review = _get_review_for_user(db, review_id, subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    status = payload.status
    row = db.execute(
        text("""
            SELECT suggestion_id, status FROM resume_suggestions
            WHERE suggestion_id = :sid AND review_id = :rid
            LIMIT 1
        """),
        {"sid": suggestion_id, "rid": review_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "suggestion_not_found", "message": "Suggestion not found"})
    # Lock review row to avoid race on counter updates
    db.execute(
        text("SELECT review_id FROM resume_reviews WHERE review_id = :rid AND user_id = :uid FOR UPDATE"),
        {"rid": review_id, "uid": subject_id},
    ).fetchall()
    db.execute(
        text("""
            UPDATE resume_suggestions SET status = :status, student_edit = :student_edit WHERE suggestion_id = :sid AND review_id = :rid
        """),
        {
            "sid": suggestion_id,
            "rid": review_id,
            "status": status,
            "student_edit": payload.student_edit if status == "edited" else None,
        },
    )
    # Recompute counts in one shot to avoid race conditions
    db.execute(
        text("""
            UPDATE resume_reviews
            SET accepted_count = (SELECT COUNT(*) FROM resume_suggestions WHERE review_id = :rid AND status IN ('accepted', 'edited')),
                rejected_count = (SELECT COUNT(*) FROM resume_suggestions WHERE review_id = :rid AND status = 'rejected')
            WHERE review_id = :rid AND user_id = :uid
        """),
        {"rid": review_id, "uid": subject_id},
    )
    db.commit()
    log_audit(
        engine,
        subject_id=subject_id,
        action="bff.resume.suggestion.patch",
        object_type="resume_suggestion",
        object_id=suggestion_id,
        status="ok",
        detail={"status": status},
    )
    return {"suggestion_id": suggestion_id, "status": status}


# ─── POST /resume-review/{review_id}/rescore ───────────────────────────────────────

@router.post("/{review_id}/rescore")
def resume_review_rescore(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Build new resume text from accepted/edited suggestions, re-run scorer, persist final_scores."""
    subject_id = ident.subject_id
    review = _get_review_for_user(db, review_id, subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") not in ("reviewed", "enhanced"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_state", "message": "Accept some suggestions first, then rescore."},
        )
    doc_id = review["doc_id"]
    base_text = get_resume_text_from_doc(db, doc_id)
    if not base_text or len(base_text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_chunks", "message": "Document content not available."},
        )
    rows = db.execute(
        text("""
            SELECT original_text, COALESCE(student_edit, suggested_text) AS replacement, status
            FROM resume_suggestions
            WHERE review_id = :rid AND status IN ('accepted', 'edited')
            ORDER BY created_at ASC
        """),
        {"rid": review_id},
    ).fetchall()
    new_text = base_text
    for r in rows:
        orig, repl, _ = r[0], r[1], r[2]
        if orig and repl is not None and orig in new_text:
            new_text = new_text.replace(orig, repl, 1)
    if not new_text or len(new_text.strip()) < 100:
        raise HTTPException(
            status_code=400,
            detail={"error": "resume_too_short", "message": "Resulting content too short after applying suggestions."},
        )
    try:
        result = score_resume(
            db,
            doc_id=doc_id,
            user_id=subject_id,
            target_role_id=review.get("target_role_id"),
            resume_text_override=new_text,
        )
    except ValueError as e:
        if str(e) == "llm_parse_error":
            raise HTTPException(status_code=422, detail={"error": "llm_parse_error", "message": "AI could not rescore. Try again."}) from e
        raise HTTPException(status_code=400, detail={"error": "validation", "message": str(e)}) from e
    except RuntimeError as e:
        _log.exception("Resume rescore failed")
        raise HTTPException(status_code=502, detail={"error": "llm_timeout", "message": str(e), "retry": True}) from e
    scores = result["scores"]
    total = result["total"]
    initial_total = review.get("total_initial") or 0
    db.execute(
        text("""
            UPDATE resume_reviews
            SET final_scores = :scores, total_final = :total, status = 'enhanced', updated_at = :now
            WHERE review_id = :rid AND user_id = :uid
        """),
        {"rid": review_id, "uid": subject_id, "scores": json.dumps(scores), "total": float(total), "now": _now_utc()},
    )
    db.commit()
    log_audit(
        engine,
        subject_id=subject_id,
        action="bff.resume.rescore",
        object_type="resume_review",
        object_id=review_id,
        status="ok",
        detail={"total_final": total},
    )
    improvements = {}
    initial_scores = review.get("initial_scores")
    if isinstance(initial_scores, str):
        try:
            initial_scores = json.loads(initial_scores)
        except Exception:
            initial_scores = {}
    if isinstance(initial_scores, dict) and scores:
        for k, v in scores.items():
            if isinstance(v, dict) and "score" in v:
                prev = initial_scores.get(k, {})
                prev_s = prev.get("score", 0) if isinstance(prev, dict) else 0
                improvements[k] = int(v["score"]) - int(prev_s)
    return {
        "final_scores": scores,
        "total_final": total,
        "total_initial": initial_total,
        "improvements": improvements,
    }


# ─── POST /resume-review/{review_id}/apply-template ──────────────────────────────

@router.post("/{review_id}/apply-template")
def resume_review_apply_template(
    review_id: str,
    payload: ApplyTemplateRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Fill template with review's final resume content and return DOCX as base64 for download."""
    subject_id = ident.subject_id
    review = _get_review_for_user(db, review_id, subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") not in ("reviewed", "enhanced", "completed"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_state", "message": "Complete scoring and suggestions before applying a template."},
        )
    doc_id = review["doc_id"]
    base_text = get_resume_text_from_doc(db, doc_id)
    if not base_text or len(base_text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_chunks", "message": "Document content not available."},
        )
    rows = db.execute(
        text("""
            SELECT original_text, COALESCE(student_edit, suggested_text) AS replacement
            FROM resume_suggestions
            WHERE review_id = :rid AND status IN ('accepted', 'edited')
            ORDER BY created_at ASC
        """),
        {"rid": review_id},
    ).fetchall()
    resume_content = base_text
    for r in rows:
        orig, repl = r[0], r[1]
        if orig and repl is not None and orig in resume_content:
            resume_content = resume_content.replace(orig, repl, 1)
    try:
        doc_bytes = template_apply(
            db,
            review_id=review_id,
            template_id=payload.template_id,
            resume_content=resume_content,
        )
    except FileNotFoundError as e:
        if "template_not_found" in str(e):
            raise HTTPException(status_code=404, detail={"error": "template_not_found", "message": "Template file not found"}) from e
        raise HTTPException(status_code=404, detail={"error": "template_not_found", "message": str(e)}) from e
    b64 = base64.b64encode(doc_bytes).decode("ascii")
    filename = f"resume_enhanced_{review_id[:8]}.docx"
    db.execute(
        text("UPDATE resume_reviews SET template_id = :tid, status = 'completed', updated_at = :now WHERE review_id = :rid AND user_id = :uid"),
        {"tid": payload.template_id, "now": _now_utc(), "rid": review_id, "uid": subject_id},
    )
    db.commit()
    log_audit(
        engine,
        subject_id=subject_id,
        action="bff.resume.apply_template",
        object_type="resume_review",
        object_id=review_id,
        status="ok",
        detail={"template_id": payload.template_id},
    )
    return {"filename": filename, "content_base64": b64, "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}