"""
P5 Decision 1: Retrieval Pipeline – Reranker + Threshold Refusal

Centralized evidence retrieval with:
- Reranker switch (RERANKER_ENABLED, default off)
- Pre/post threshold refusal (fail-closed)
- Reliability output (high/medium/low)
- Refusal structure: { code, message, next_step }, items=[]

Env vars:
- RERANKER_ENABLED=0|1 (default 0)
- RERANKER_MODEL (optional, placeholder for mock)
- RERANKER_TOP_K (default 10)
- EVIDENCE_MIN_SCORE_PRE (default 0.20)
- EVIDENCE_MIN_SCORE_POST (default 0.25)
- EVIDENCE_MIN_SCORE (unified fallback)
- GAP_HIGH, SCORE_HIGH for reliability
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Env
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "0").strip().lower() in ("1", "true", "yes")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "placeholder").strip()
RERANKER_TOP_K = int(os.getenv("RERANKER_TOP_K", "10"))
EVIDENCE_MIN_SCORE_PRE = float(os.getenv("EVIDENCE_MIN_SCORE_PRE", "0.20"))
EVIDENCE_MIN_SCORE_POST = float(os.getenv("EVIDENCE_MIN_SCORE_POST", "0.25"))
EVIDENCE_MIN_SCORE = float(os.getenv("EVIDENCE_MIN_SCORE", str(EVIDENCE_MIN_SCORE_PRE)))
GAP_HIGH = float(os.getenv("GAP_HIGH", "0.05"))
SCORE_HIGH = float(os.getenv("SCORE_HIGH", "0.35"))


@dataclass
class RetrievalItem:
    """Single evidence item from retrieval."""
    chunk_id: str
    doc_id: str
    score: float
    source: str  # "vector" | "reranked"
    position_info: Dict[str, Any] = field(default_factory=dict)
    snippet: Optional[str] = None  # <=300 for student only


@dataclass
class RetrievalMeta:
    """Metadata about retrieval run."""
    vector_top_k: int
    reranker_enabled: bool
    pre_scores: List[float] = field(default_factory=list)
    post_scores: List[float] = field(default_factory=list)
    min_score_passed: bool = False
    refusal: Optional[Dict[str, Any]] = None


@dataclass
class ReliabilityInfo:
    """Reliability level and reason codes."""
    level: str  # high | medium | low
    reason_codes: List[str] = field(default_factory=list)
    debug: Optional[Dict[str, Any]] = None  # student/admin only


@dataclass
class RetrievalResult:
    """Canonical retrieval output."""
    items: List[RetrievalItem]
    retrieval_meta: RetrievalMeta
    reliability: ReliabilityInfo


def _get_reranker():
    """Lazy init reranker. Returns None on failure (fail-closed)."""
    if not RERANKER_ENABLED:
        return None
    try:
        if RERANKER_MODEL == "placeholder":
            # Pass-through: keep order, assign dummy post scores
            def _placeholder_rerank(query: str, items: List[Dict], top_k: int) -> List[Dict]:
                for i, it in enumerate(items[:top_k]):
                    it["post_score"] = it.get("score", 0.0) - (i * 0.01)
                return items[:top_k]
            return _placeholder_rerank
        # Future: cross-encoder
        return None
    except Exception as e:
        logger.warning("Reranker init failed: %s", e)
        return None


_reranker_fn = None


def _rerank(query: str, items: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """Run reranker. Raises on failure (caller must fail-closed)."""
    global _reranker_fn
    if _reranker_fn is None:
        _reranker_fn = _get_reranker()
    if _reranker_fn is None:
        raise RuntimeError("Reranker unavailable (init failed or disabled)")
    return _reranker_fn(query, items, top_k)


def _compute_reliability(
    pre_scores: List[float],
    post_scores: List[float],
    reranker_enabled: bool,
    min_passed: bool,
    pre_top1_in_post_top3: bool = True,
) -> ReliabilityInfo:
    """
    Compute reliability level per Decision 2 rules.
    HIGH: threshold passed, (top1-top2 gap >= GAP_HIGH or top1 >= SCORE_HIGH), rerank stable
    MEDIUM: threshold passed, gap/score near threshold
    LOW: threshold failed, or rerank unstable, or conflict
    """
    if not min_passed:
        return ReliabilityInfo(level="low", reason_codes=["evidence_below_threshold"])
    if not pre_scores:
        return ReliabilityInfo(level="low", reason_codes=["no_results"])
    top1 = pre_scores[0] if pre_scores else 0.0
    top2 = pre_scores[1] if len(pre_scores) > 1 else 0.0
    gap = top1 - top2
    if reranker_enabled and not pre_top1_in_post_top3:
        return ReliabilityInfo(level="low", reason_codes=["rerank_unstable"])
    if top1 >= SCORE_HIGH or gap >= GAP_HIGH:
        return ReliabilityInfo(level="high", reason_codes=["score_high_or_gap_high"])
    if gap < 0.02 or top1 < EVIDENCE_MIN_SCORE_PRE + 0.05:
        return ReliabilityInfo(level="medium", reason_codes=["near_threshold"])
    return ReliabilityInfo(level="high", reason_codes=["passed"])


def _refusal(code: str, message: str, next_step: str) -> Dict[str, Any]:
    from backend.app.refusal import refusal_dict
    return refusal_dict(code, message, next_step, headers=None)


def retrieve_evidence(
    query: str,
    *,
    doc_filter: Optional[str] = None,
    skill_id: Optional[str] = None,
    top_k: int = 10,
    use_reranker: Optional[bool] = None,
    thresholds: Optional[Dict[str, float]] = None,
    include_snippet: bool = True,
    request_id: str = "",
) -> RetrievalResult:
    """
    Retrieve evidence chunks via vector search + optional reranker.
    Fail-closed: threshold refusal, reranker init/inference failure -> refusal.
    """
    try:
        from backend.app.embeddings import embed_texts
        from backend.app.vector_store import get_client, search
    except ImportError:
        from app.embeddings import embed_texts
        from app.vector_store import get_client, search
    try:
        from qdrant_client.http import models as qm
    except ImportError:
        qm = None

    thr = thresholds or {}
    min_pre = thr.get("min_pre", EVIDENCE_MIN_SCORE_PRE)
    min_post = thr.get("min_post", EVIDENCE_MIN_SCORE_POST)
    do_rerank = use_reranker if use_reranker is not None else RERANKER_ENABLED

    vector_k = RERANKER_TOP_K * 2 if do_rerank else top_k
    vector_k = max(vector_k, top_k)

    client = get_client()
    if client is None:
        return RetrievalResult(
            items=[],
            retrieval_meta=RetrievalMeta(
                vector_top_k=0,
                reranker_enabled=do_rerank,
                min_score_passed=False,
                refusal=_refusal(
                    "vector_search_unavailable",
                    "Vector search service unavailable.",
                    "Check Qdrant connectivity and retry.",
                ),
            ),
            reliability=ReliabilityInfo(level="low", reason_codes=["vector_unavailable"]),
        )

    try:
        query_vec = embed_texts([query])[0]
    except Exception as e:
        return RetrievalResult(
            items=[],
            retrieval_meta=RetrievalMeta(
                vector_top_k=0,
                reranker_enabled=do_rerank,
                min_score_passed=False,
                refusal=_refusal(
                    "embedding_failed",
                    f"Embedding generation failed: {e}",
                    "Retry or check embedding service.",
                ),
            ),
            reliability=ReliabilityInfo(level="low", reason_codes=["embedding_failed"]),
        )

    flt = None
    if doc_filter and qm:
        flt = qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_filter))])

    try:
        raw = search(client, query_vec, vector_k, flt, request_id, doc_filter or "")
    except Exception as e:
        return RetrievalResult(
            items=[],
            retrieval_meta=RetrievalMeta(
                vector_top_k=0,
                reranker_enabled=do_rerank,
                min_score_passed=False,
                refusal=_refusal(
                    "vector_search_failed",
                    f"Vector search failed: {e}",
                    "Retry or check Qdrant.",
                ),
            ),
            reliability=ReliabilityInfo(level="low", reason_codes=["search_failed"]),
        )

    pre_scores = [float(r.score) for r in raw]
    if not pre_scores:
        return RetrievalResult(
            items=[],
            retrieval_meta=RetrievalMeta(
                vector_top_k=vector_k,
                reranker_enabled=do_rerank,
                pre_scores=[],
                post_scores=[],
                min_score_passed=False,
                refusal=_refusal(
                    "evidence_below_threshold_pre",
                    "No evidence chunks retrieved above threshold.",
                    "Upload more documents or try a broader query.",
                ),
            ),
            reliability=ReliabilityInfo(level="low", reason_codes=["no_results"]),
        )

    # Pre threshold: vector top1 < PRE -> refusal
    if pre_scores[0] < min_pre:
        return RetrievalResult(
            items=[],
            retrieval_meta=RetrievalMeta(
                vector_top_k=vector_k,
                reranker_enabled=do_rerank,
                pre_scores=pre_scores[:5],
                post_scores=[],
                min_score_passed=False,
                refusal=_refusal(
                    "evidence_below_threshold_pre",
                    f"Top result score {pre_scores[0]:.4f} below pre-threshold {min_pre}.",
                    "Upload more relevant evidence or refine your query.",
                ),
            ),
            reliability=ReliabilityInfo(level="low", reason_codes=["evidence_below_threshold_pre"]),
        )

    # Build items from raw
    items_data = []
    for i, r in enumerate(raw):
        payload = r.payload or {}
        items_data.append({
            "chunk_id": str(payload.get("chunk_id", "")),
            "doc_id": str(payload.get("doc_id", "")),
            "score": float(r.score),
            "idx": int(payload.get("idx", i)),
            "snippet": (payload.get("snippet") or "")[:300] if include_snippet else None,
            "char_start": payload.get("char_start"),
            "char_end": payload.get("char_end"),
            "section_path": payload.get("section_path"),
            "page_start": payload.get("page_start"),
            "page_end": payload.get("page_end"),
        })

    post_scores = pre_scores[:]
    pre_top1_in_post_top3 = True

    if do_rerank:
        try:
            reranked = _rerank(query, items_data, RERANKER_TOP_K)
            items_data = reranked
            post_scores = [it.get("post_score", it.get("score", 0)) for it in items_data]
            pre_top1_score = pre_scores[0]
            post_top3_scores = post_scores[:3]
            pre_top1_in_post_top3 = any(abs(s - pre_top1_score) < 0.01 for s in post_top3_scores)
        except Exception as e:
            return RetrievalResult(
                items=[],
                retrieval_meta=RetrievalMeta(
                    vector_top_k=vector_k,
                    reranker_enabled=True,
                    pre_scores=pre_scores[:5],
                    post_scores=[],
                    min_score_passed=False,
                    refusal=_refusal(
                        "reranker_failed",
                        f"Reranker failed: {e}",
                        "Retry with RERANKER_ENABLED=0 or fix reranker service.",
                    ),
                ),
                reliability=ReliabilityInfo(level="low", reason_codes=["reranker_failed"]),
            )

        if post_scores and post_scores[0] < min_post:
            return RetrievalResult(
                items=[],
                retrieval_meta=RetrievalMeta(
                    vector_top_k=vector_k,
                    reranker_enabled=True,
                    pre_scores=pre_scores[:5],
                    post_scores=post_scores[:5],
                    min_score_passed=False,
                    refusal=_refusal(
                        "evidence_below_threshold_post",
                        f"Reranked top score {post_scores[0]:.4f} below post-threshold {min_post}.",
                        "Upload more relevant evidence or refine your query.",
                    ),
                ),
                reliability=ReliabilityInfo(level="low", reason_codes=["evidence_below_threshold_post"]),
            )

    # Cap to top_k
    items_data = items_data[:top_k]
    if post_scores:
        post_scores = post_scores[:top_k]
    else:
        post_scores = [it.get("score", 0) for it in items_data]

    items = []
    for i, it in enumerate(items_data):
        scr = post_scores[i] if i < len(post_scores) else it.get("score", 0)
        items.append(RetrievalItem(
            chunk_id=it["chunk_id"],
            doc_id=it["doc_id"],
            score=round(scr, 4),
            source="reranked" if do_rerank else "vector",
            position_info={
                "idx": it.get("idx"),
                "char_start": it.get("char_start"),
                "char_end": it.get("char_end"),
                "section_path": it.get("section_path"),
                "page_start": it.get("page_start"),
                "page_end": it.get("page_end"),
            },
            snippet=it.get("snippet") if include_snippet else None,
        ))

    reliability = _compute_reliability(
        pre_scores, post_scores, do_rerank, min_passed=True, pre_top1_in_post_top3=pre_top1_in_post_top3
    )

    return RetrievalResult(
        items=items,
        retrieval_meta=RetrievalMeta(
            vector_top_k=vector_k,
            reranker_enabled=do_rerank,
            pre_scores=pre_scores[:5],
            post_scores=post_scores[:5],
            min_score_passed=True,
        ),
        reliability=reliability,
    )
