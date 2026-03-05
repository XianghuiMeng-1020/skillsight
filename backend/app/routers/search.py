"""
Search Routes for SkillSight
- POST /search/evidence_vector: Vector-based evidence retrieval (Decision 1)
  Uses retrieval_pipeline: reranker + threshold refusal + reliability.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from backend.app.db.deps import get_db
    from backend.app.security import Identity, require_auth
except ImportError:
    from app.db.deps import get_db
    from app.security import Identity, require_auth

try:
    from backend.app.refusal import refusal_dict
    from backend.app.retrieval_pipeline import retrieve_evidence
except ImportError:
    from app.refusal import refusal_dict
    from app.retrieval_pipeline import retrieve_evidence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


def _now_utc():
    return datetime.now(timezone.utc)


def _get_skill(db: Session, skill_id: str) -> Optional[Dict[str, Any]]:
    """Get skill by ID."""
    sql = text("""
        SELECT skill_id, canonical_name, definition, evidence_rules
        FROM skills
        WHERE skill_id = :skill_id
        LIMIT 1
    """)
    row = db.execute(sql, {"skill_id": skill_id}).mappings().first()
    return dict(row) if row else None


def _build_query_text(skill: Dict[str, Any]) -> str:
    """Build search query text from skill definition and evidence rules."""
    parts = []
    if skill.get("canonical_name"):
        parts.append(skill["canonical_name"])
    if skill.get("definition"):
        parts.append(skill["definition"])
    if skill.get("evidence_rules"):
        parts.append(skill["evidence_rules"])
    return " ".join(parts)


class EvidenceSearchRequest(BaseModel):
    """Request for vector-based evidence search."""
    query_text: Optional[str] = Field(default=None, description="Free text query (if not using skill_id)")
    skill_id: Optional[str] = Field(default=None, description="Skill ID to search for (generates query from skill definition)")
    doc_id: Optional[str] = Field(default=None, description="Filter to specific document")
    k: int = Field(default=5, ge=1, le=50, description="Number of results to return")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum similarity score")


class EvidenceItem(BaseModel):
    """Single evidence item in search results."""
    chunk_id: str
    doc_id: str
    idx: int
    snippet: str
    score: float
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    section_path: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    created_at: Optional[str] = None


class EvidenceSearchResponse(BaseModel):
    """Response from evidence search. Decision 1: refusal + reliability."""
    query_text: str
    skill_id: Optional[str] = None
    doc_id: Optional[str] = None
    k: int
    items: List[EvidenceItem]
    timing_ms: int
    refusal: Optional[Dict[str, Any]] = None
    retrieval_meta: Optional[Dict[str, Any]] = None
    reliability: Optional[Dict[str, Any]] = None


@router.post("/evidence_vector", response_model=EvidenceSearchResponse)
def search_evidence_vector(
    req: EvidenceSearchRequest,
    request: Request,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Decision 1: Vector-based evidence retrieval via retrieval_pipeline.
    
    Uses reranker (when enabled) + threshold refusal (fail-closed) + reliability.
    Refusal: items=[], refusal={code, message, next_step}.
    """
    started = _now_utc()

    query_text = None
    skill_id = None

    if req.skill_id:
        skill = _get_skill(db, req.skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found: {req.skill_id}")
        query_text = _build_query_text(skill)
        skill_id = req.skill_id
    elif req.query_text:
        query_text = req.query_text.strip()
    else:
        raise HTTPException(status_code=400, detail="Either skill_id or query_text is required")

    if not query_text:
        raise HTTPException(status_code=400, detail="Query text is empty")

    request_id = getattr(request.state, "request_id", "") or str(id(request))
    result = retrieve_evidence(
        query_text,
        doc_filter=req.doc_id,
        skill_id=skill_id,
        top_k=req.k,
        thresholds={"min_pre": max(req.min_score, 0.20), "min_post": max(req.min_score, 0.25)},
        include_snippet=True,
        request_id=request_id,
    )

    # Denylist: staff/programme must not receive snippet, chunk_text, stored_path
    denylist = ident.role in ("staff", "programme_leader")
    items = []
    for it in result.items:
        if it.score < req.min_score:
            continue
        item = {
            "chunk_id": it.chunk_id,
            "doc_id": it.doc_id,
            "idx": it.position_info.get("idx", 0),
            "snippet": "" if denylist else (it.snippet or ""),
            "score": it.score,
            "char_start": it.position_info.get("char_start"),
            "char_end": it.position_info.get("char_end"),
            "section_path": it.position_info.get("section_path"),
            "page_start": it.position_info.get("page_start"),
            "page_end": it.position_info.get("page_end"),
            "created_at": None,
        }
        items.append(item)

    timing_ms = int((_now_utc() - started).total_seconds() * 1000)
    out = {
        "query_text": query_text[:500],
        "skill_id": skill_id,
        "doc_id": req.doc_id,
        "k": req.k,
        "items": items,
        "timing_ms": timing_ms,
    }
    if result.retrieval_meta.refusal:
        out["refusal"] = result.retrieval_meta.refusal
    elif not items and req.min_score > 0:
        # All pipeline results were filtered by request min_score; return refusal for Decision 1
        out["refusal"] = refusal_dict(
            "evidence_below_threshold_pre",
            f"No results above requested min_score {req.min_score}.",
            "Upload more relevant evidence or refine your query.",
        )
    out["retrieval_meta"] = {
        "reranker_enabled": result.retrieval_meta.reranker_enabled,
        "min_score_passed": result.retrieval_meta.min_score_passed,
    }
    out["reliability"] = {
        "level": result.reliability.level,
        "reason_codes": result.reliability.reason_codes,
    }
    return out


@router.post("/evidence_keyword")
def search_evidence_keyword(
    req: EvidenceSearchRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Keyword-based evidence search (fallback when vector search unavailable).
    Uses SQL ILIKE for simple text matching.
    """
    started = _now_utc()
    
    # Determine query text
    query_text = None
    skill_id = None
    
    if req.skill_id:
        skill = _get_skill(db, req.skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found: {req.skill_id}")
        query_text = skill.get("canonical_name", "")
        skill_id = req.skill_id
    elif req.query_text:
        query_text = req.query_text.strip()
    else:
        raise HTTPException(status_code=400, detail="Either skill_id or query_text is required")
    
    if not query_text:
        raise HTTPException(status_code=400, detail="Query text is empty")
    
    # Build SQL query
    params = {"q": f"%{query_text}%", "limit": req.k}
    
    if req.doc_id:
        sql = text("""
            SELECT chunk_id::text as chunk_id, doc_id::text as doc_id, idx, snippet, 
                   char_start, char_end, section_path, page_start, page_end, created_at::text
            FROM chunks
            WHERE doc_id = :doc_id AND (chunk_text ILIKE :q OR snippet ILIKE :q)
            ORDER BY idx ASC
            LIMIT :limit
        """)
        params["doc_id"] = req.doc_id
    else:
        sql = text("""
            SELECT chunk_id::text as chunk_id, doc_id::text as doc_id, idx, snippet,
                   char_start, char_end, section_path, page_start, page_end, created_at::text
            FROM chunks
            WHERE chunk_text ILIKE :q OR snippet ILIKE :q
            ORDER BY created_at DESC
            LIMIT :limit
        """)
    
    rows = db.execute(sql, params).mappings().all()
    
    items = []
    for r in rows:
        items.append({
            "chunk_id": r["chunk_id"],
            "doc_id": r["doc_id"],
            "idx": int(r["idx"]),
            "snippet": r["snippet"],
            "score": 1.0,  # Keyword match doesn't have score
            "char_start": r.get("char_start"),
            "char_end": r.get("char_end"),
            "section_path": r.get("section_path"),
            "page_start": r.get("page_start"),
            "page_end": r.get("page_end"),
            "created_at": r.get("created_at"),
        })
    
    timing_ms = int((_now_utc() - started).total_seconds() * 1000)
    
    return {
        "query_text": query_text[:500],
        "skill_id": skill_id,
        "doc_id": req.doc_id,
        "k": req.k,
        "items": items,
        "timing_ms": timing_ms,
    }
