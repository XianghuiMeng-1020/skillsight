"""Resume claim verification service (vector evidence + rule checks)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.retrieval_pipeline import retrieve_evidence


_ACTION_RE = re.compile(
    r"\b(led|built|designed|implemented|improved|launched|optimized|reduced|increased|managed|delivered)\b|"
    r"(负责|主导|设计|实现|优化|提升|降低|管理|交付)",
    re.IGNORECASE,
)
_NUMERIC_RE = re.compile(r"(\d+%|\$\d+(?:,\d{3})*|\d{2,}|x\b|倍)")
_YEAR_RANGE_RE = re.compile(
    r"\b(19\d{2}|20\d{2})\s*[-–—to]+\s*(present|now|current|至今|现在|19\d{2}|20\d{2})",
    re.IGNORECASE,
)


def extract_resume_claims(resume_text: str, max_claims: int = 14) -> List[str]:
    """Extract potentially verifiable claims from resume lines."""
    lines = [ln.strip() for ln in (resume_text or "").splitlines() if ln.strip()]
    scored: List[tuple[int, str]] = []
    for ln in lines:
        score = 0
        if ln.startswith(("•", "-", "–", "*")):
            score += 2
        if _ACTION_RE.search(ln):
            score += 2
        if _NUMERIC_RE.search(ln):
            score += 2
        if len(ln) > 30:
            score += 1
        if score >= 2:
            cleaned = ln.lstrip("•-–* ").strip()
            scored.append((score, cleaned))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[str] = []
    for _, claim in scored:
        if claim not in out:
            out.append(claim)
        if len(out) >= max_claims:
            break
    if not out:
        out = lines[: min(6, len(lines))]
    return out


def _rule_validate_resume_text(resume_text: str) -> List[Dict[str, str]]:
    """Rule-based risk checks for timeline/fact/exaggeration."""
    issues: List[Dict[str, str]] = []
    lines = [ln.strip() for ln in (resume_text or "").splitlines() if ln.strip()]
    now_year = datetime.now(timezone.utc).year

    ranges: List[tuple[int, int, str]] = []
    for ln in lines:
        m = _YEAR_RANGE_RE.search(ln)
        if not m:
            continue
        y1 = int(m.group(1))
        y2_raw = (m.group(2) or "").lower()
        y2 = now_year if y2_raw in {"present", "now", "current", "至今", "现在"} else int(y2_raw)
        ranges.append((y1, y2, ln))
        if y2 < y1:
            issues.append({"code": "timeline_reverse", "level": "warn", "message": f"Timeline reversed: {ln[:90]}"})
        if y2 > now_year + 1 or y1 > now_year + 1:
            issues.append({"code": "future_year", "level": "warn", "message": f"Future year detected: {ln[:90]}"})

    ranges_sorted = sorted(ranges, key=lambda x: x[0])
    for i in range(1, len(ranges_sorted)):
        prev_end = ranges_sorted[i - 1][1]
        cur_start = ranges_sorted[i][0]
        if cur_start - prev_end > 7:
            issues.append(
                {
                    "code": "timeline_large_gap",
                    "level": "info",
                    "message": f"Large timeline gap detected ({prev_end} -> {cur_start}).",
                }
            )
            break

    # Potential metric conflict: same sentence stem with different numbers.
    stem_to_numbers: Dict[str, set[str]] = {}
    number_re = re.compile(r"\d+(?:\.\d+)?%?|\$\d+(?:,\d{3})*")
    for ln in lines:
        nums = set(number_re.findall(ln))
        if not nums:
            continue
        stem = re.sub(r"\d+(?:\.\d+)?%?|\$\d+(?:,\d{3})*", "#", ln.lower())
        stem = re.sub(r"\s+", " ", stem).strip()
        if len(stem) < 16:
            continue
        prev = stem_to_numbers.get(stem, set())
        if prev and prev != nums:
            issues.append({"code": "metric_conflict", "level": "warn", "message": f"Potential metric conflict: {ln[:90]}"})
            break
        stem_to_numbers[stem] = prev.union(nums)

    for ln in lines:
        if re.search(r"\b([5-9]\d{2,}|[1-9]\d{3,})%\b", ln):
            issues.append({"code": "extreme_percent", "level": "warn", "message": f"Extreme percentage value found: {ln[:90]}"})
        if re.search(r"\b([2-9]\d|[1-9]\d{2,})x\b", ln.lower()):
            issues.append({"code": "extreme_multiplier", "level": "info", "message": f"High multiplier claim found: {ln[:90]}"})

    return issues[:20]


def build_verification_snapshot(
    db: Session,
    *,
    user_id: str,
    doc_id: str,
    resume_text: str,
    target_role_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a structured verification snapshot to persist with scoring."""
    claims = extract_resume_claims(resume_text)
    claim_items: List[Dict[str, Any]] = []
    evidence_items: List[Dict[str, Any]] = []
    supported_count = 0

    for idx, claim in enumerate(claims):
        ret = retrieve_evidence(
            claim,
            doc_filter=str(doc_id),
            top_k=3,
            include_snippet=True,
            request_id=f"resume_verify_{idx}",
        )
        top_score = float(ret.items[0].score) if ret.items else 0.0
        verdict = "supported" if top_score >= 0.25 else ("partial" if ret.items else "unverified")
        if verdict == "supported":
            supported_count += 1
        ev_refs: List[str] = []
        for it in ret.items:
            ref_id = f"{it.doc_id}:{it.chunk_id}"
            ev_refs.append(ref_id)
            evidence_items.append(
                {
                    "id": ref_id,
                    "chunk_id": it.chunk_id,
                    "doc_id": it.doc_id,
                    "score": float(it.score),
                    "snippet": it.snippet or "",
                    "source": it.source,
                }
            )
        claim_items.append(
            {
                "claim_id": f"claim_{idx+1}",
                "text": claim,
                "verdict": verdict,
                "confidence": round(min(1.0, top_score), 3),
                "evidence_refs": ev_refs[:3],
            }
        )

    issues = _rule_validate_resume_text(resume_text)
    total = len(claim_items) or 1
    coverage = round(supported_count / total, 3)
    if coverage >= 0.67 and not any(i["level"] == "warn" for i in issues):
        verdict = "pass"
    elif coverage >= 0.4:
        verdict = "review"
    else:
        verdict = "fail"

    return {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_role_id": target_role_id,
        "claims": claim_items,
        "evidence": evidence_items[:40],
        "issues": issues,
        "summary": {
            "claims_total": len(claim_items),
            "claims_supported": supported_count,
            "coverage": coverage,
            "verdict": verdict,
            "confidence": round(max(0.15, min(0.98, coverage)), 3),
        },
    }

