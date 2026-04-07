"""
BFF Student – Resume Enhancement Center.
Routes: /bff/student/resume-review/*

All endpoints require auth. Document access is validated via consent.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
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
from backend.app.services.docx_pdf import docx_bytes_to_pdf_bytes
from backend.app.services.resume_structured import html_preview_for_resume, layout_health_check
from backend.app.services.resume_template_service import apply_template as template_apply
from backend.app.services.resume_template_service import resolve_template_builder_key
from backend.app.services.resume_text_merge import apply_suggestion_replace_once
from backend.app.services.resume_verification_service import build_verification_snapshot
from backend.app.services.resume_attribution_report_service import build_attribution_report_docx

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
                   accepted_count, rejected_count, template_id,
                   verification_snapshot, verification_version,
                   created_at, updated_at
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
    export_format: Literal["docx", "pdf", "html", "linkedin"] = "docx"
    resume_override_text: Optional[str] = Field(None, max_length=120000)
    template_options: Optional[Dict[str, Any]] = None


class PreviewHtmlRequest(BaseModel):
    template_id: str = Field(..., max_length=256)
    resume_override_text: Optional[str] = Field(None, max_length=120000)
    template_options: Optional[Dict[str, Any]] = None


class CloneReviewRequest(BaseModel):
    target_role_id: Optional[str] = Field(None, max_length=256)
    label: Optional[str] = Field(None, max_length=200)


class DiffInsightsRequest(BaseModel):
    compare_review_id: Optional[str] = Field(None, max_length=128)
    resume_override_text: Optional[str] = Field(None, max_length=120000)


class ExportAttributionReportRequest(BaseModel):
    export_format: Literal["docx", "pdf"] = "docx"
    compare_review_id: Optional[str] = Field(None, max_length=128)
    resume_override_text: Optional[str] = Field(None, max_length=120000)


@router.post("/{review_id}/one-click-enhance")
def resume_review_one_click_enhance(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Generate suggestions -> auto accept high/medium -> rescore in one call."""
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") == "scoring":
        resume_review_score(review_id, db, ident)
    existing = db.execute(
        text("SELECT suggestion_id, priority FROM resume_suggestions WHERE review_id = :rid ORDER BY created_at"),
        {"rid": review_id},
    ).mappings().all()
    if not existing:
        resume_review_suggest(review_id, db, ident)
        existing = db.execute(
            text("SELECT suggestion_id, priority FROM resume_suggestions WHERE review_id = :rid ORDER BY created_at"),
            {"rid": review_id},
        ).mappings().all()
    accepted = 0
    for row in existing:
        pri = (row.get("priority") or "").lower()
        status = "accepted" if pri in ("high", "medium") else "rejected"
        db.execute(
            text("UPDATE resume_suggestions SET status = :status WHERE suggestion_id = :sid"),
            {"status": status, "sid": str(row["suggestion_id"])},
        )
        if status == "accepted":
            accepted += 1
    db.commit()
    rescore = resume_review_rescore(review_id, db, ident)
    return {"review_id": review_id, "accepted_suggestions": accepted, "rescore": rescore}


def _status_to_step(status: str) -> int:
    mapping = {
        "scoring": 2,
        "reviewed": 3,
        "enhanced": 4,
        "completed": 5,
    }
    return mapping.get((status or "").strip().lower(), 1)


def _classify_runtime_error(err: RuntimeError) -> str:
    s = str(err).lower()
    if "timeout" in s or "timed out" in s:
        return "llm_timeout"
    if "parse" in s or "schema" in s or "json" in s:
        return "llm_schema_error"
    return "llm_downstream_error"


def _merge_resume_with_suggestions(db: Session, review_id: str, doc_id: str, subject_id: str) -> str:
    """Base resume text with accepted/edited suggestions applied (same order as export)."""
    _check_consent(db, doc_id, subject_id)
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
    rows_sorted = sorted(rows, key=lambda r: len((r[0] or "")), reverse=True)
    resume_content = base_text
    for r in rows_sorted:
        orig, repl = r[0], r[1]
        if not orig or repl is None:
            continue
        occurrences = resume_content.count(orig.strip()) if orig.strip() else 0
        if occurrences > 1:
            _log.warning(
                "suggestion replacement ambiguous review_id=%s occurrences=%s sample=%s",
                review_id,
                occurrences,
                orig.strip()[:120],
            )
        resume_content = apply_suggestion_replace_once(resume_content, orig, repl)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", resume_content)


def _normalize_nonempty_lines(text_value: str) -> List[str]:
    return [ln.strip() for ln in (text_value or "").splitlines() if ln.strip()]


def _json_obj(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value or {}, ensure_ascii=False)


def _is_resume_header_line(line: str) -> bool:
    s = (line or "").strip().rstrip(":：")
    if not s:
        return False
    if re.match(r"^[A-Z][A-Z\s/&-]{2,48}$", s):
        return True
    if re.match(r"^[A-Za-z][A-Za-z\s/&-]{2,48}$", s):
        kws = {
            "summary", "profile", "objective", "experience", "work history", "work experience",
            "education", "projects", "skills", "certifications", "awards", "publications",
        }
        return s.lower() in kws
    if re.match(r"^(个人简介|简介|摘要|工作经历|工作经验|教育背景|教育经历|项目经历|项目经验|技能|专业技能|证书|奖项|荣誉)$", s):
        return True
    return False


def _extract_role_keywords(role_id: Optional[str]) -> List[str]:
    if not role_id:
        return []
    role_tokens = re.findall(r"[A-Za-z]{3,}", role_id.lower().replace("_", " ").replace("-", " "))
    stop = {"role", "senior", "junior", "intern", "lead", "manager", "specialist"}
    out: List[str] = []
    for tok in role_tokens:
        if tok in stop:
            continue
        if tok not in out:
            out.append(tok)
    return out[:8]


def _split_sentences(text_value: str) -> List[str]:
    compact = re.sub(r"[ \t]+", " ", (text_value or "").strip())
    if not compact:
        return []
    parts = re.split(r"[。！？!?;\n]+", compact)
    out = [p.strip() for p in parts if p and len(p.strip()) >= 4]
    return out[:220]


def _sentence_vector(sentence: str) -> Counter:
    toks = re.findall(r"[a-z0-9+#./-]{2,}|[\u4e00-\u9fff]{1,}", sentence.lower())
    return Counter(toks)


def _cosine(vec_a: Counter, vec_b: Counter) -> float:
    if not vec_a or not vec_b:
        return 0.0
    inter = set(vec_a.keys()) & set(vec_b.keys())
    num = sum(vec_a[k] * vec_b[k] for k in inter)
    if num <= 0:
        return 0.0
    den = math.sqrt(sum(v * v for v in vec_a.values())) * math.sqrt(sum(v * v for v in vec_b.values()))
    if den <= 0:
        return 0.0
    return float(num / den)


def _parse_score_map(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _normalize_dim_name(raw: str) -> str:
    s = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "ats": "ats_friendly",
        "ats_friendly": "ats_friendly",
        "skills": "skills_presentation",
        "skills_presentation": "skills_presentation",
    }
    return mapping.get(s, s)


def _compute_score_attribution(
    baseline_scores_raw: Any,
    current_scores_raw: Any,
    dimension_impact: Dict[str, Any],
    baseline_total: Optional[float],
    current_total: Optional[float],
) -> Dict[str, Any]:
    baseline_scores = _parse_score_map(baseline_scores_raw)
    current_scores = _parse_score_map(current_scores_raw)
    dims = sorted(set(list(baseline_scores.keys()) + list(current_scores.keys())))
    by_dim: List[Dict[str, Any]] = []
    for dim in dims:
        base_obj = baseline_scores.get(dim) if isinstance(baseline_scores.get(dim), dict) else {}
        cur_obj = current_scores.get(dim) if isinstance(current_scores.get(dim), dict) else {}
        base_score = float(base_obj.get("score", 0) or 0)
        cur_score = float(cur_obj.get("score", 0) or 0)
        delta = cur_score - base_score
        key = _normalize_dim_name(dim)
        signal_obj = dimension_impact.get(key, {}) if isinstance(dimension_impact, dict) else {}
        signal = signal_obj.get("signal", "neutral")
        alignment = "aligned" if (delta > 0 and signal == "positive") or (delta < 0 and signal == "negative") else "mixed"
        if delta == 0:
            alignment = "neutral"
        by_dim.append(
            {
                "dimension": dim,
                "score_before": base_score,
                "score_after": cur_score,
                "score_delta": delta,
                "change_signal": signal,
                "alignment": alignment,
            }
        )
    total_delta = None
    if baseline_total is not None and current_total is not None:
        total_delta = float(current_total) - float(baseline_total)
    return {"total_delta": total_delta, "by_dimension": by_dim}


def _analyze_resume_diff(
    baseline_text: str,
    current_text: str,
    role_id: Optional[str],
    baseline_scores: Any = None,
    current_scores: Any = None,
    baseline_total: Optional[float] = None,
    current_total: Optional[float] = None,
) -> Dict[str, Any]:
    base_lines = _normalize_nonempty_lines(baseline_text)
    cur_lines = _normalize_nonempty_lines(current_text)
    base_set = set(base_lines)
    cur_set = set(cur_lines)
    added_lines = [ln for ln in cur_lines if ln not in base_set]
    removed_lines = [ln for ln in base_lines if ln not in cur_set]

    bullet_re = re.compile(r"^(?:[-•*]|(?:\d{1,2}[.)]))\s+")
    metric_re = re.compile(r"(\d+%|\$\d+|\d{2,}|x\b|倍)")
    weak_re = re.compile(r"\b(helped|assisted|various|responsible for|participated in)\b|参与|协助|负责", re.IGNORECASE)
    year_re = re.compile(r"\b(19\d{2}|20\d{2})\b")

    def _metric_count(lines: List[str]) -> int:
        return sum(1 for ln in lines if bullet_re.match(ln) and metric_re.search(ln))

    def _bullet_count(lines: List[str]) -> int:
        return sum(1 for ln in lines if bullet_re.match(ln))

    def _weak_count(lines: List[str]) -> int:
        return sum(1 for ln in lines if weak_re.search(ln))

    def _dup_count(lines: List[str]) -> int:
        seen = set()
        dup = 0
        for ln in lines:
            key = ln.lower()
            if key in seen:
                dup += 1
            else:
                seen.add(key)
        return dup

    def _section_count(lines: List[str]) -> int:
        return sum(1 for ln in lines if _is_resume_header_line(ln))

    def _role_hits(lines: List[str], kws: List[str]) -> int:
        if not kws:
            return 0
        low = "\n".join(lines).lower()
        return sum(1 for kw in kws if kw in low)

    role_kws = _extract_role_keywords(role_id)
    metrics = {
        "before": {
            "line_count": len(base_lines),
            "bullet_count": _bullet_count(base_lines),
            "quantified_bullets": _metric_count(base_lines),
            "weak_phrases": _weak_count(base_lines),
            "duplicate_lines": _dup_count(base_lines),
            "section_headers": _section_count(base_lines),
            "long_lines": sum(1 for ln in base_lines if len(ln) > 160),
            "role_hits": _role_hits(base_lines, role_kws),
        },
        "after": {
            "line_count": len(cur_lines),
            "bullet_count": _bullet_count(cur_lines),
            "quantified_bullets": _metric_count(cur_lines),
            "weak_phrases": _weak_count(cur_lines),
            "duplicate_lines": _dup_count(cur_lines),
            "section_headers": _section_count(cur_lines),
            "long_lines": sum(1 for ln in cur_lines if len(ln) > 160),
            "role_hits": _role_hits(cur_lines, role_kws),
        },
    }

    dim_scores: Dict[str, int] = {
        "impact": 0,
        "relevance": 0,
        "structure": 0,
        "language": 0,
        "skills_presentation": 0,
        "ats_friendly": 0,
    }
    risks: List[Dict[str, str]] = []

    q_delta = metrics["after"]["quantified_bullets"] - metrics["before"]["quantified_bullets"]
    weak_delta = metrics["after"]["weak_phrases"] - metrics["before"]["weak_phrases"]
    dup_delta = metrics["after"]["duplicate_lines"] - metrics["before"]["duplicate_lines"]
    role_delta = metrics["after"]["role_hits"] - metrics["before"]["role_hits"]
    long_delta = metrics["after"]["long_lines"] - metrics["before"]["long_lines"]
    sec_delta = metrics["after"]["section_headers"] - metrics["before"]["section_headers"]

    if q_delta > 0:
        dim_scores["impact"] += 2
    if weak_delta < 0:
        dim_scores["language"] += 1
        dim_scores["impact"] += 1
    if dup_delta < 0:
        dim_scores["structure"] += 1
    if sec_delta > 0:
        dim_scores["structure"] += 1
    if role_delta > 0:
        dim_scores["relevance"] += 2
        dim_scores["ats_friendly"] += 1
    if long_delta > 1:
        dim_scores["ats_friendly"] -= 1
        risks.append({"level": "warn", "code": "long_lines_increase", "message": "More long lines detected; ATS readability may drop."})
    if weak_delta > 1:
        risks.append({"level": "warn", "code": "weak_language", "message": "More vague phrases were introduced; consider stronger action verbs."})
        dim_scores["language"] -= 1
    if dup_delta > 0:
        risks.append({"level": "warn", "code": "duplicate_content", "message": "Duplicate lines increased across sections."})
    if metrics["after"]["quantified_bullets"] == 0 and metrics["after"]["bullet_count"] >= 3:
        risks.append({"level": "info", "code": "missing_metrics", "message": "Bullet points still lack measurable outcomes."})

    years = [int(y) for y in year_re.findall(current_text or "")]
    if years:
        year_span = max(years) - min(years)
        if year_span > 20 and len(years) <= 3:
            risks.append({"level": "info", "code": "timeline_sparse", "message": "Timeline appears sparse; consider filling key periods."})

    # Risk validator: timeline contradictions + fact conflicts + exaggeration signals
    now_year = datetime.now(timezone.utc).year
    timeline_issues: List[Dict[str, str]] = []
    year_range_re = re.compile(r"\b(19\d{2}|20\d{2})\s*[-–—to]+\s*(present|now|current|至今|现在|19\d{2}|20\d{2})", re.IGNORECASE)
    ranges: List[tuple[int, int, str]] = []
    for ln in cur_lines:
        m = year_range_re.search(ln)
        if not m:
            continue
        y1 = int(m.group(1))
        y2_raw = (m.group(2) or "").lower()
        y2 = now_year if y2_raw in {"present", "now", "current", "至今", "现在"} else int(y2_raw)
        ranges.append((y1, y2, ln))
        if y2 < y1:
            timeline_issues.append({"level": "warn", "code": "timeline_reverse", "message": f"Timeline reversed in line: {ln[:90]}"})
        if y1 > now_year + 1 or y2 > now_year + 1:
            timeline_issues.append({"level": "warn", "code": "future_year", "message": f"Future year detected in timeline: {ln[:90]}"})
    ranges_sorted = sorted(ranges, key=lambda x: x[0])
    for idx in range(1, len(ranges_sorted)):
        prev_end = ranges_sorted[idx - 1][1]
        cur_start = ranges_sorted[idx][0]
        if cur_start - prev_end > 7:
            timeline_issues.append(
                {
                    "level": "info",
                    "code": "timeline_large_gap",
                    "message": f"Large timeline gap detected ({prev_end} -> {cur_start}).",
                }
            )
            break

    fact_issues: List[Dict[str, str]] = []
    num_re = re.compile(r"\d+(?:\.\d+)?%?|\$\d+(?:,\d{3})*")
    stem_map: Dict[str, set] = {}
    for ln in cur_lines:
        stem = re.sub(r"\d+(?:\.\d+)?%?|\$\d+(?:,\d{3})*", "#", ln.lower())
        stem = re.sub(r"\s+", " ", stem).strip()
        nums = set(num_re.findall(ln))
        if not nums or len(stem) < 16:
            continue
        prev = stem_map.get(stem, set())
        if prev and prev != nums:
            fact_issues.append({"level": "warn", "code": "metric_conflict", "message": f"Potential metric conflict: {ln[:90]}"})
            break
        stem_map[stem] = prev.union(nums)

    exaggeration_issues: List[Dict[str, str]] = []
    for ln in cur_lines:
        if re.search(r"\b([5-9]\d{2,}|[1-9]\d{3,})%\b", ln):
            exaggeration_issues.append({"level": "warn", "code": "extreme_percent", "message": f"Extreme percentage value found: {ln[:90]}"})
            continue
        if re.search(r"\b([2-9]\d|[1-9]\d{2,})x\b", ln.lower()):
            exaggeration_issues.append({"level": "info", "code": "extreme_multiplier", "message": f"High multiplier claim found: {ln[:90]}"})

    risk_validator_issues = (timeline_issues + fact_issues + exaggeration_issues)[:8]
    risks.extend([r for r in risk_validator_issues if r not in risks])

    # Sentence-level semantic alignment (embedding-lite cosine over token vectors).
    base_sentences = _split_sentences(baseline_text)
    cur_sentences = _split_sentences(current_text)
    base_vecs = [_sentence_vector(s) for s in base_sentences]
    cur_vecs = [_sentence_vector(s) for s in cur_sentences]
    matched_pairs: List[Dict[str, Any]] = []
    used_base = set()
    sim_sum = 0.0
    for ci, cur_vec in enumerate(cur_vecs):
        best_idx = -1
        best_sim = 0.0
        for bi, base_vec in enumerate(base_vecs):
            if bi in used_base:
                continue
            sim = _cosine(cur_vec, base_vec)
            if sim > best_sim:
                best_sim = sim
                best_idx = bi
        if best_idx >= 0 and best_sim >= 0.33:
            used_base.add(best_idx)
            sim_sum += best_sim
            matched_pairs.append(
                {
                    "before": base_sentences[best_idx],
                    "after": cur_sentences[ci],
                    "similarity": round(best_sim, 3),
                }
            )
    matched_count = len(matched_pairs)
    avg_sim = (sim_sum / matched_count) if matched_count else 0.0
    semantic_alignment = {
        "avg_similarity": round(avg_sim, 3),
        "matched_sentences": matched_count,
        "added_sentences": max(0, len(cur_sentences) - matched_count),
        "removed_sentences": max(0, len(base_sentences) - matched_count),
        "pairs": sorted(matched_pairs, key=lambda x: x["similarity"], reverse=True)[:10],
    }
    if semantic_alignment["avg_similarity"] < 0.35 and (semantic_alignment["added_sentences"] + semantic_alignment["removed_sentences"]) > 8:
        risks.append(
            {
                "level": "info",
                "code": "major_semantic_shift",
                "message": "Large semantic shift detected; verify factual consistency before export.",
            }
        )

    def _clamp(v: int) -> int:
        return max(-2, min(2, v))

    dimension_impact = {
        k: {
            "delta": _clamp(v),
            "signal": "positive" if v > 0 else ("negative" if v < 0 else "neutral"),
        }
        for k, v in dim_scores.items()
    }

    highlights: List[str] = []
    if q_delta > 0:
        highlights.append(f"Quantified bullet points increased by {q_delta}.")
    if role_delta > 0:
        highlights.append(f"Role keyword coverage increased by {role_delta}.")
    if dup_delta < 0:
        highlights.append("Duplicate lines reduced.")
    if not highlights:
        highlights.append("Content changed, but key quality signals stayed mostly flat.")

    next_actions: List[str] = []
    if metrics["after"]["quantified_bullets"] < max(2, metrics["after"]["bullet_count"] // 3):
        next_actions.append("Add metrics to high-impact bullets (%, $, scale).")
    if metrics["after"]["long_lines"] > 3:
        next_actions.append("Split long lines into concise bullets for readability.")
    if role_kws and metrics["after"]["role_hits"] < len(role_kws) // 2:
        next_actions.append("Mirror more target-role keywords in Experience and Skills sections.")
    if not next_actions:
        next_actions.append("Current revision quality looks stable; validate with final rubric rescore.")

    attribution = _compute_score_attribution(
        baseline_scores,
        current_scores,
        dimension_impact,
        baseline_total,
        current_total,
    )

    return {
        "summary": {
            "added_lines": len(added_lines),
            "removed_lines": len(removed_lines),
            "overlap_lines": len(base_set.intersection(cur_set)),
        },
        "metrics": metrics,
        "dimension_impact": dimension_impact,
        "highlights": highlights,
        "risks": risks,
        "semantic_alignment": semantic_alignment,
        "risk_validator": {
            "issues": risk_validator_issues,
            "risk_level": (
                "high"
                if any(it.get("level") == "warn" for it in risk_validator_issues)
                else ("medium" if risk_validator_issues else "low")
            ),
        },
        "attribution": attribution,
        "next_actions": next_actions,
    }


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


@router.get("/{review_id}/state")
def resume_review_state(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Return review status and the max reachable step for robust step recovery."""
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    status = str(review.get("status") or "")
    max_step = _status_to_step(status)
    return {
        "review_id": review_id,
        "status": status,
        "max_step": max_step,
        "target_role_id": review.get("target_role_id"),
        "has_initial_scores": review.get("initial_scores") is not None,
        "has_final_scores": review.get("final_scores") is not None,
    }


@router.get("/{review_id}/editable-resume")
def resume_review_editable_resume(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    resume_content = _merge_resume_with_suggestions(db, review_id, review["doc_id"], ident.subject_id)
    return {"review_id": review_id, "resume_text": resume_content}


@router.post("/{review_id}/clone-version")
def resume_review_clone_version(
    review_id: str,
    payload: CloneReviewRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    src = _get_review_for_user(db, review_id, ident.subject_id)
    if not src:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    new_review_id = str(uuid.uuid4())
    now = _now_utc()
    db.execute(
        text(
            """
            INSERT INTO resume_reviews
            (review_id, user_id, doc_id, target_role_id, status, initial_scores, final_scores, total_initial, total_final,
             accepted_count, rejected_count, template_id, verification_snapshot, verification_version, created_at, updated_at)
            VALUES
            (:new_rid, :uid, :doc_id, :target_role_id, :status, :initial_scores, :final_scores, :total_initial, :total_final,
             :accepted_count, :rejected_count, :template_id, :verification_snapshot, :verification_version, :now, :now)
            """
        ),
        {
            "new_rid": new_review_id,
            "uid": ident.subject_id,
            "doc_id": src["doc_id"],
            "target_role_id": payload.target_role_id if payload.target_role_id is not None else src.get("target_role_id"),
            "status": src.get("status") or "reviewed",
            "initial_scores": src.get("initial_scores"),
            "final_scores": src.get("final_scores"),
            "total_initial": src.get("total_initial"),
            "total_final": src.get("total_final"),
            "accepted_count": src.get("accepted_count") or 0,
            "rejected_count": src.get("rejected_count") or 0,
            "template_id": src.get("template_id"),
            "verification_snapshot": src.get("verification_snapshot"),
            "verification_version": src.get("verification_version"),
            "now": now,
        },
    )
    db.commit()
    return {"review_id": new_review_id, "status": src.get("status") or "reviewed", "label": payload.label}


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
    _t0 = time.perf_counter()
    try:
        result = score_resume(
            db,
            doc_id=doc_id,
            user_id=subject_id,
            target_role_id=review.get("target_role_id"),
        )
        _log.info(
            "bff.resume.score.timing_ms=%.1f review_id=%s doc_id=%s",
            (time.perf_counter() - _t0) * 1000,
            review_id,
            doc_id,
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
        err_code = _classify_runtime_error(e)
        _log.exception("Resume score failed code=%s", err_code)
        raise HTTPException(
            status_code=502,
            detail={"error": err_code, "message": "Scoring service is temporarily unavailable. Please retry shortly.", "retry": True},
        ) from e
    except Exception as e:
        _log.exception("Resume score unexpected error: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"error": "scoring_failed", "message": "Scoring failed unexpectedly. Please retry.", "retry": True},
        ) from e
    scores = result["scores"]
    total = result["total"]
    verification_snapshot = build_verification_snapshot(
        db,
        user_id=subject_id,
        doc_id=str(doc_id),
        resume_text=resume_text,
        target_role_id=review.get("target_role_id"),
    )
    verification_version = str(verification_snapshot.get("version") or "v1")
    db.execute(
        text("""
            UPDATE resume_reviews
            SET initial_scores = :scores,
                total_initial = :total,
                verification_snapshot = :verification_snapshot,
                verification_version = :verification_version,
                status = 'reviewed',
                updated_at = :now
            WHERE review_id = :rid AND user_id = :uid
        """),
        {
            "rid": review_id,
            "uid": subject_id,
            "scores": json.dumps(scores),
            "total": float(total),
            "verification_snapshot": json.dumps(verification_snapshot, ensure_ascii=False),
            "verification_version": verification_version,
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
        detail={"total_initial": total, "verification_version": verification_version},
    )
    return {
        "initial_scores": scores,
        "total_initial": total,
        "total_final": None,
        "final_scores": None,
        "verification_snapshot": verification_snapshot,
        "verification_version": verification_version,
    }


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
    verification_snapshot = review.get("verification_snapshot")
    if isinstance(verification_snapshot, str):
        try:
            verification_snapshot = json.loads(verification_snapshot)
        except Exception:
            verification_snapshot = None
    return {
        "initial_scores": initial,
        "final_scores": final,
        "total_initial": review.get("total_initial"),
        "total_final": review.get("total_final"),
        "verification_snapshot": verification_snapshot,
        "verification_version": review.get("verification_version"),
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
    _t0 = time.perf_counter()
    try:
        suggestions = enhancer_generate_suggestions(
            db,
            user_id=subject_id,
            resume_text=resume_text,
            scoring_json=initial_scores,
            target_role_id=review.get("target_role_id"),
        )
        _log.info(
            "bff.resume.suggest.timing_ms=%.1f review_id=%s",
            (time.perf_counter() - _t0) * 1000,
            review_id,
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
    # After template export, status is "completed"; returning to step 4 must not fail — reuse stored scores.
    if review.get("status") == "completed":
        final_scores = review.get("final_scores")
        total_final = review.get("total_final")
        if isinstance(final_scores, str):
            try:
                final_scores = json.loads(final_scores)
            except Exception:
                final_scores = None
        if isinstance(final_scores, dict) and final_scores and total_final is not None:
            initial_total = float(review.get("total_initial") or 0)
            initial_scores = review.get("initial_scores")
            if isinstance(initial_scores, str):
                try:
                    initial_scores = json.loads(initial_scores)
                except Exception:
                    initial_scores = {}
            if not isinstance(initial_scores, dict):
                initial_scores = {}
            improvements: Dict[str, int] = {}
            for k, v in final_scores.items():
                if isinstance(v, dict) and "score" in v:
                    prev = initial_scores.get(k, {})
                    prev_s = prev.get("score", 0) if isinstance(prev, dict) else 0
                    improvements[k] = int(v["score"]) - int(prev_s)
            return {
                "final_scores": final_scores,
                "total_final": float(total_final),
                "total_initial": initial_total,
                "improvements": improvements,
                "verification_snapshot": _json_obj(review.get("verification_snapshot")),
                "verification_version": review.get("verification_version"),
            }
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
    rows_sorted = sorted(rows, key=lambda r: len((r[0] or "")), reverse=True)
    new_text = base_text
    for r in rows_sorted:
        orig, repl, _ = r[0], r[1], r[2]
        if not orig or repl is None:
            continue
        occurrences = new_text.count(orig.strip()) if orig.strip() else 0
        if occurrences > 1:
            _log.warning(
                "rescore replacement ambiguous review_id=%s occurrences=%s sample=%s",
                review_id,
                occurrences,
                orig.strip()[:120],
            )
        new_text = apply_suggestion_replace_once(new_text, orig, repl)
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
    verification_snapshot = build_verification_snapshot(
        db,
        user_id=subject_id,
        doc_id=str(doc_id),
        resume_text=new_text,
        target_role_id=review.get("target_role_id"),
    )
    verification_version = str(verification_snapshot.get("version") or "v1")
    initial_total = review.get("total_initial") or 0
    db.execute(
        text("""
            UPDATE resume_reviews
            SET final_scores = :scores,
                total_final = :total,
                verification_snapshot = :verification_snapshot,
                verification_version = :verification_version,
                status = 'enhanced',
                updated_at = :now
            WHERE review_id = :rid AND user_id = :uid
        """),
        {
            "rid": review_id,
            "uid": subject_id,
            "scores": json.dumps(scores),
            "total": float(total),
            "verification_snapshot": json.dumps(verification_snapshot, ensure_ascii=False),
            "verification_version": verification_version,
            "now": _now_utc(),
        },
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
        "verification_snapshot": verification_snapshot,
        "verification_version": verification_version,
    }


# ─── GET /resume-review/{review_id}/layout-check ───────────────────────────────

@router.get("/{review_id}/layout-check")
def resume_review_layout_check(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Heuristic layout/readability hints before export (版面体检)."""
    subject_id = ident.subject_id
    review = _get_review_for_user(db, review_id, subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") not in ("reviewed", "enhanced", "completed"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_state", "message": "Complete scoring first."},
        )
    doc_id = review["doc_id"]
    try:
        resume_content = _merge_resume_with_suggestions(db, review_id, doc_id, subject_id)
    except HTTPException:
        raise
    out = layout_health_check(resume_content)

    # Surface truncation risks to users before export.
    chunks_count = db.execute(
        text("SELECT COUNT(*) FROM chunks WHERE doc_id::text = :doc_id"),
        {"doc_id": str(doc_id)},
    ).scalar() or 0
    if int(chunks_count) > 500:
        out["issues"].append(
            {
                "level": "warn",
                "code": "chunk_truncation",
                "message": "Document is very long; only first 500 chunks are used during scoring/export.",
            }
        )
    if len(resume_content) > 30000:
        out["issues"].append(
            {
                "level": "info",
                "code": "prompt_truncation",
                "message": "Long content may be truncated in AI scoring prompts; verify critical sections.",
            }
        )
    accepted_rows = db.execute(
        text(
            """
            SELECT original_text
            FROM resume_suggestions
            WHERE review_id = :rid AND status IN ('accepted', 'edited')
            """
        ),
        {"rid": review_id},
    ).fetchall()
    ambiguous = 0
    for row in accepted_rows:
        orig = (row[0] or "").strip()
        if orig and resume_content.count(orig) > 1:
            ambiguous += 1
    if ambiguous > 0:
        out["issues"].append(
            {
                "level": "warn",
                "code": "ambiguous_replacements",
                "message": f"{ambiguous} accepted suggestion(s) match multiple places. Consider editing to make replacements explicit.",
            }
        )
    out["score"] = max(0, int(out.get("score", 100)) - (8 if ambiguous else 0))
    return out


@router.get("/{review_id}/compression-hints")
def resume_review_compression_hints(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Heuristic content compression assistant for 1-page/2-page targets."""
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    resume_content = _merge_resume_with_suggestions(db, review_id, review["doc_id"], ident.subject_id)
    lines = [ln for ln in resume_content.splitlines() if ln.strip()]
    approx_pages = max(1, int(len(lines) / 42) + 1)
    hints: List[str] = []
    if approx_pages > 2:
        hints.append("Current content is likely over two pages; prioritize your most relevant 3-5 achievements.")
    if len(resume_content) > 5500:
        hints.append("Long summary detected; keep profile summary within 3-4 concise lines.")
    if resume_content.count("\n- ") + resume_content.count("\n• ") > 20:
        hints.append("Too many bullets may reduce scanability; merge lower-impact bullets.")
    if "project" in resume_content.lower() and "experience" in resume_content.lower():
        hints.append("Avoid repeating similar impact points across Projects and Experience.")
    if not hints:
        hints.append("Content density looks healthy for one-page targeting.")
    return {"review_id": review_id, "estimated_pages": approx_pages, "hints": hints}


@router.post("/{review_id}/diff-insights")
def resume_review_diff_insights(
    review_id: str,
    payload: DiffInsightsRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Semantic change insights between current review and another review/base version."""
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})

    if payload.resume_override_text and payload.resume_override_text.strip():
        current_text = payload.resume_override_text.strip()
    else:
        current_text = _merge_resume_with_suggestions(db, review_id, review["doc_id"], ident.subject_id)

    baseline_review_id = payload.compare_review_id
    baseline_scores = review.get("initial_scores")
    baseline_total = review.get("total_initial")
    current_scores = review.get("final_scores") or review.get("initial_scores")
    current_total = review.get("total_final") if review.get("total_final") is not None else review.get("total_initial")
    if baseline_review_id:
        baseline_review = _get_review_for_user(db, baseline_review_id, ident.subject_id)
        if not baseline_review:
            raise HTTPException(status_code=404, detail={"error": "compare_review_not_found", "message": "Compared review not found"})
        baseline_text = _merge_resume_with_suggestions(db, baseline_review_id, baseline_review["doc_id"], ident.subject_id)
        baseline_scores = baseline_review.get("final_scores") or baseline_review.get("initial_scores")
        baseline_total = baseline_review.get("total_final") if baseline_review.get("total_final") is not None else baseline_review.get("total_initial")
    else:
        baseline_text = get_resume_text_from_doc(db, review["doc_id"])

    out = _analyze_resume_diff(
        baseline_text or "",
        current_text or "",
        review.get("target_role_id"),
        baseline_scores=baseline_scores,
        current_scores=current_scores,
        baseline_total=baseline_total,
        current_total=current_total,
    )
    out["review_id"] = review_id
    out["compare_review_id"] = baseline_review_id
    out["role_keywords"] = _extract_role_keywords(review.get("target_role_id"))
    out["verification_snapshot"] = _json_obj(review.get("verification_snapshot"))
    out["verification_version"] = review.get("verification_version")
    return out


def _compute_attribution_payload(
    db: Session,
    review: Dict[str, Any],
    review_id: str,
    subject_id: str,
) -> Dict[str, Any]:
    baseline_text = get_resume_text_from_doc(db, review["doc_id"])
    current_text = _merge_resume_with_suggestions(db, review_id, review["doc_id"], subject_id)
    return _analyze_resume_diff(
        baseline_text or "",
        current_text or "",
        review.get("target_role_id"),
        baseline_scores=review.get("initial_scores"),
        current_scores=review.get("final_scores") or review.get("initial_scores"),
        baseline_total=review.get("total_initial"),
        current_total=review.get("total_final") if review.get("total_final") is not None else review.get("total_initial"),
    )


@router.get("/{review_id}/attribution")
def resume_review_attribution(
    review_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Structured explainability payload for UI and report export reuse."""
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") not in ("reviewed", "enhanced", "completed"):
        raise HTTPException(status_code=400, detail={"error": "invalid_state", "message": "Complete scoring first."})
    out = _compute_attribution_payload(db, review, review_id, ident.subject_id)
    out["review_id"] = review_id
    out["verification_snapshot"] = _json_obj(review.get("verification_snapshot"))
    out["verification_version"] = review.get("verification_version")
    return out


@router.post("/{review_id}/export-attribution-report")
def resume_review_export_attribution_report(
    review_id: str,
    payload: ExportAttributionReportRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Export explainability report in DOCX/PDF."""
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") not in ("reviewed", "enhanced", "completed"):
        raise HTTPException(status_code=400, detail={"error": "invalid_state", "message": "Complete scoring first."})

    if payload.resume_override_text and payload.resume_override_text.strip():
        current_text = payload.resume_override_text.strip()
    else:
        current_text = _merge_resume_with_suggestions(db, review_id, review["doc_id"], ident.subject_id)
    if payload.compare_review_id:
        compare_review = _get_review_for_user(db, payload.compare_review_id, ident.subject_id)
        if not compare_review:
            raise HTTPException(status_code=404, detail={"error": "compare_review_not_found", "message": "Compared review not found"})
        baseline_text = _merge_resume_with_suggestions(db, payload.compare_review_id, compare_review["doc_id"], ident.subject_id)
        baseline_scores = compare_review.get("final_scores") or compare_review.get("initial_scores")
        baseline_total = compare_review.get("total_final") if compare_review.get("total_final") is not None else compare_review.get("total_initial")
    else:
        baseline_text = get_resume_text_from_doc(db, review["doc_id"])
        baseline_scores = review.get("initial_scores")
        baseline_total = review.get("total_initial")

    attribution = _analyze_resume_diff(
        baseline_text or "",
        current_text or "",
        review.get("target_role_id"),
        baseline_scores=baseline_scores,
        current_scores=review.get("final_scores") or review.get("initial_scores"),
        baseline_total=baseline_total,
        current_total=review.get("total_final") if review.get("total_final") is not None else review.get("total_initial"),
    )
    verification_snapshot = _json_obj(review.get("verification_snapshot"))
    initial_scores = _json_obj(review.get("initial_scores"))
    final_scores = _json_obj(review.get("final_scores"))

    docx_bytes = build_attribution_report_docx(
        review_id=review_id,
        target_role_id=review.get("target_role_id"),
        total_initial=review.get("total_initial"),
        total_final=review.get("total_final"),
        initial_scores=initial_scores,
        final_scores=final_scores,
        verification_snapshot=verification_snapshot,
        attribution=attribution.get("attribution") if isinstance(attribution.get("attribution"), dict) else {"by_dimension": []},
    )

    want_pdf = payload.export_format == "pdf"
    out_bytes = docx_bytes
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    filename = f"resume_explainability_{review_id[:8]}.docx"
    pdf_fallback = False
    if want_pdf:
        pdf_bytes = docx_bytes_to_pdf_bytes(docx_bytes)
        if pdf_bytes:
            out_bytes = pdf_bytes
            mime = "application/pdf"
            filename = f"resume_explainability_{review_id[:8]}.pdf"
        else:
            pdf_fallback = True

    log_audit(
        engine,
        subject_id=ident.subject_id,
        action="bff.resume.export_attribution_report",
        object_type="resume_review",
        object_id=review_id,
        status="ok",
        detail={"format": payload.export_format, "pdf_fallback": pdf_fallback},
    )

    body: Dict[str, Any] = {
        "filename": filename,
        "content_base64": base64.b64encode(out_bytes).decode("ascii"),
        "mime_type": mime,
        "format_used": "pdf" if mime.endswith("/pdf") else "docx",
    }
    if pdf_fallback:
        body["pdf_unavailable"] = True
        body["message"] = "PDF conversion requires LibreOffice (soffice) on the server; DOCX was returned instead."
    return body


# ─── GET /resume-review/{review_id}/preview-html ────────────────────────────────

@router.get("/{review_id}/preview-html", response_class=HTMLResponse)
def resume_review_preview_html(
    review_id: str,
    template_id: str,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Approximate HTML preview for the selected template (high-fidelity preview UX)."""
    subject_id = ident.subject_id
    review = _get_review_for_user(db, review_id, subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") not in ("reviewed", "enhanced", "completed"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_state", "message": "Complete scoring and suggestions before preview."},
        )
    doc_id = review["doc_id"]
    resume_content = _merge_resume_with_suggestions(db, review_id, doc_id, subject_id)
    key = resolve_template_builder_key(template_id, db)
    html = html_preview_for_resume(resume_content, key, {})
    return HTMLResponse(content=html)


@router.post("/{review_id}/preview-html", response_class=HTMLResponse)
def resume_review_preview_html_post(
    review_id: str,
    payload: PreviewHtmlRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    review = _get_review_for_user(db, review_id, ident.subject_id)
    if not review:
        raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
    if review.get("status") not in ("reviewed", "enhanced", "completed"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_state", "message": "Complete scoring and suggestions before preview."},
        )
    if payload.resume_override_text and payload.resume_override_text.strip():
        resume_content = payload.resume_override_text.strip()
    else:
        resume_content = _merge_resume_with_suggestions(db, review_id, review["doc_id"], ident.subject_id)
    key = resolve_template_builder_key(payload.template_id, db)
    html = html_preview_for_resume(resume_content, key, payload.template_options or {})
    return HTMLResponse(content=html)


# ─── POST /resume-review/{review_id}/apply-template ──────────────────────────────

@router.post("/{review_id}/apply-template")
def resume_review_apply_template(
    review_id: str,
    payload: ApplyTemplateRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
):
    """Fill template with review's final resume content and return DOCX (or PDF) as base64 for download."""
    subject_id = ident.subject_id
    want_pdf = payload.export_format == "pdf"
    _log.info(
        "apply-template: review_id=%s template_id=%s user=%s format=%s",
        review_id,
        payload.template_id,
        subject_id,
        payload.export_format,
    )

    try:
        review = _get_review_for_user(db, review_id, subject_id)
        if not review:
            raise HTTPException(status_code=404, detail={"error": "review_not_found", "message": "Review not found"})
        _log.info("apply-template: review status=%s doc_id=%s", review.get("status"), review.get("doc_id"))

        if review.get("status") not in ("reviewed", "enhanced", "completed"):
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_state", "message": "Complete scoring and suggestions before applying a template."},
            )

        doc_id = review["doc_id"]
        if payload.resume_override_text and payload.resume_override_text.strip():
            resume_content = payload.resume_override_text.strip()
        else:
            resume_content = _merge_resume_with_suggestions(db, review_id, doc_id, subject_id)
        _log.info("apply-template: resume_content length=%d, calling template_apply", len(resume_content))

        _t0 = time.perf_counter()
        doc_bytes = template_apply(
            db,
            review_id=review_id,
            template_id=payload.template_id,
            resume_content=resume_content,
            template_options=payload.template_options or {},
        )
        _log.info(
            "apply-template: doc_bytes length=%d timing_ms=%.1f",
            len(doc_bytes),
            (time.perf_counter() - _t0) * 1000,
        )

        pdf_fallback = False
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"resume_enhanced_{review_id[:8]}.docx"
        out_bytes = doc_bytes

        if payload.export_format == "html":
            html = html_preview_for_resume(
                resume_content, resolve_template_builder_key(payload.template_id, db), payload.template_options or {}
            )
            out_bytes = html.encode("utf-8")
            mime = "text/html; charset=utf-8"
            filename = f"resume_enhanced_{review_id[:8]}.html"
        elif payload.export_format == "linkedin":
            linkedin_text = re.sub(r"\n{3,}", "\n\n", resume_content).strip()
            out_bytes = linkedin_text.encode("utf-8")
            mime = "text/plain; charset=utf-8"
            filename = f"resume_enhanced_{review_id[:8]}_linkedin.txt"
        elif want_pdf:
            pdf_bytes = docx_bytes_to_pdf_bytes(doc_bytes)
            if pdf_bytes:
                out_bytes = pdf_bytes
                mime = "application/pdf"
                filename = f"resume_enhanced_{review_id[:8]}.pdf"
            else:
                pdf_fallback = True
                _log.warning("apply-template: PDF requested but LibreOffice not available; returning DOCX")

        b64 = base64.b64encode(out_bytes).decode("ascii")
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
            detail={"template_id": payload.template_id, "format": payload.export_format, "pdf_fallback": pdf_fallback},
        )
        _log.info("apply-template: success, filename=%s", filename)
        body: Dict[str, Any] = {
            "filename": filename,
            "content_base64": b64,
            "mime_type": mime,
            "format_used": "pdf" if mime.endswith("/pdf") else "docx",
            "template_options": payload.template_options or {},
        }
        if pdf_fallback:
            body["pdf_unavailable"] = True
            body["message"] = "PDF conversion requires LibreOffice (soffice) on the server; DOCX was returned instead."
        return body

    except HTTPException:
        raise
    except Exception as e:
        _log.exception("apply-template FAILED")
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Failed to generate document. Please retry."},
        ) from e