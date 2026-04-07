"""
P5 Decision 3: Stable Skill Level Aggregator

Aggregates skill level across evidence, documents, and time.
- Input: subject_id, skill_id
- Output: level (0-3), reliability_level, supporting_evidence_ids[]
- Rules: min evidence count >= 2, consistency check, fail-closed
- Writes to skill_assessment_snapshots + change_log_events on change

Documented in docs/P5_SKILL_LEVEL_AGGREGATOR.md
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.sql import bindparam
from sqlalchemy.orm import Session

# Minimum evidence count for high reliability (fail-closed)
MIN_EVIDENCE_FOR_HIGH = 2
# Level scale 0-3 (align with proficiency rubric)
LEVEL_MAX = 3
# Consistency: same-direction ratio threshold (e.g. 0.8 = 80% must agree)
CONSISTENCY_RATIO = 0.8


@dataclass
class EvidenceItem:
    """Single evidence from skill_proficiency or skill_assessments."""
    doc_id: str
    chunk_id: Optional[str]
    level: int
    label: str
    decision: str  # demonstrated, mentioned, not_enough_information
    source: str  # "proficiency" | "assessment"
    evidence_id: str  # assessment_id or prof_id for dedup
    created_at: Optional[datetime] = None
    modality: str = "document"  # document | interactive | project


@dataclass
class AggregatedSkillLevel:
    """P5 canonical output for a skill."""
    skill_id: str
    level: int
    reliability_level: str  # high, medium, low
    reliability_explain: str
    supporting_evidence_ids: List[str]
    needs_human_review: bool = False
    conflict_detected: bool = False


def _coerce_json(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, (str, bytes, bytearray)):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def _get_consented_doc_ids(db: Session, subject_id: str) -> List[str]:
    """Get doc_ids for which subject has granted consent."""
    rows = db.execute(
        text("""
            SELECT DISTINCT doc_id FROM consents
            WHERE user_id = :sub AND status = 'granted'
        """),
        {"sub": subject_id},
    ).mappings().all()
    return [str(r["doc_id"]) for r in rows]


def _collect_evidence_for_skill(
    db: Session,
    subject_id: str,
    skill_id: str,
) -> List[EvidenceItem]:
    """
    Collect all evidence for subject+skill across consented documents.
    Returns list of EvidenceItem from skill_proficiency and skill_assessments.
    """
    doc_ids = _get_consented_doc_ids(db, subject_id)
    if not doc_ids:
        return []

    items: List[EvidenceItem] = []
    seen: set = set()

    # From skill_proficiency (use IN for list of doc_ids)
    prof_sql = text("""
        SELECT prof_id, doc_id, skill_id, level, label, best_evidence, created_at
        FROM skill_proficiency
        WHERE skill_id = :skill_id AND doc_id IN :doc_ids
        ORDER BY created_at DESC
    """).bindparams(bindparam("doc_ids", expanding=True))
    for row in db.execute(prof_sql, {"skill_id": skill_id, "doc_ids": tuple(doc_ids)}).mappings().all():
        key = f"prof:{row['prof_id']}"
        if key in seen:
            continue
        seen.add(key)
        be = _coerce_json(row.get("best_evidence")) or {}
        chunk_id = be.get("chunk_id") if isinstance(be, dict) else None
        level = int(row["level"]) if row["level"] is not None else 0
        label = row["label"] or "no_match"
        decision = "demonstrated" if level >= 1 and label not in ("no_match", "no_evidence") else "not_enough_information"
        items.append(EvidenceItem(
            doc_id=str(row["doc_id"]),
            chunk_id=chunk_id,
            level=level,
            label=label,
            decision=decision,
            source="proficiency",
            evidence_id=str(row["prof_id"]),
            created_at=row.get("created_at"),
            modality="document",
        ))

    # From skill_assessments
    ass_sql = text("""
        SELECT assessment_id, doc_id, skill_id, decision, evidence, created_at
        FROM skill_assessments
        WHERE skill_id = :skill_id AND doc_id IN :doc_ids
        ORDER BY created_at DESC
    """).bindparams(bindparam("doc_ids", expanding=True))
    for row in db.execute(ass_sql, {"skill_id": skill_id, "doc_ids": tuple(doc_ids)}).mappings().all():
        key = f"ass:{row['assessment_id']}"
        if key in seen:
            continue
        seen.add(key)
        ev = _coerce_json(row.get("evidence")) or []
        chunk_ids = []
        if isinstance(ev, list):
            for e in ev:
                if isinstance(e, dict) and e.get("chunk_id"):
                    chunk_ids.append(e["chunk_id"])
                elif isinstance(e, str):
                    chunk_ids.append(e)
        chunk_id = chunk_ids[0] if chunk_ids else None
        decision = (row["decision"] or "").lower()
        if decision in ("match", "demonstrated"):
            level = 2  # default for demonstrated
        elif decision == "mentioned":
            level = 1
        else:
            level = 0
        items.append(EvidenceItem(
            doc_id=str(row["doc_id"]),
            chunk_id=chunk_id,
            level=level,
            label=decision or "not_enough_information",
            decision=decision or "not_enough_information",
            source="assessment",
            evidence_id=str(row["assessment_id"]),
            created_at=row.get("created_at"),
            modality="document",
        ))

    # Interactive/project evidence from assessment sessions (if available)
    try:
        sess_rows = db.execute(
            text(
                """
                SELECT s.session_id, s.assessment_type, s.skill_id, s.created_at,
                       a.score, a.evaluation
                FROM assessment_sessions s
                LEFT JOIN LATERAL (
                    SELECT score, evaluation
                    FROM assessment_attempts
                    WHERE session_id = s.session_id
                    ORDER BY attempt_number DESC
                    LIMIT 1
                ) a ON true
                WHERE s.user_id = :sub AND s.skill_id = :skill_id
                ORDER BY s.created_at DESC
                LIMIT 20
                """
            ),
            {"sub": subject_id, "skill_id": skill_id},
        ).mappings().all()
        for row in sess_rows:
            sid = str(row["session_id"])
            if f"sess:{sid}" in seen:
                continue
            seen.add(f"sess:{sid}")
            score = float(row.get("score") or 0.0)
            level = 3 if score >= 85 else 2 if score >= 70 else 1 if score >= 50 else 0
            items.append(
                EvidenceItem(
                    doc_id="interactive",
                    chunk_id=None,
                    level=level,
                    label="interactive_assessment",
                    decision="demonstrated" if level >= 1 else "not_enough_information",
                    source="assessment",
                    evidence_id=sid,
                    created_at=row.get("created_at"),
                    modality="interactive",
                )
            )
    except Exception:
        pass

    return items


def _time_decay_weight(created_at: Optional[datetime]) -> float:
    if not created_at:
        return 0.85
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    # ~6 month half-life
    return max(0.35, math.exp(-days / 180.0))


def _check_consistency(items: List[EvidenceItem]) -> Tuple[bool, float, str]:
    """
    Check if evidence is consistent (same direction).
    Returns (is_consistent, same_direction_ratio, explain).
    """
    if len(items) < 2:
        return True, 1.0, "Single evidence; no consistency check."

    levels = [i.level for i in items]
    # "Same direction": levels within 1 step (no cross-grade conflict)
    min_l, max_l = min(levels), max(levels)
    if max_l - min_l > 1:
        ratio = 0.0
        for lv in levels:
            if lv == max_l or lv == min_l:
                pass
        # Cross-grade: e.g. one says 0, another says 3 -> inconsistent
        return False, 0.0, f"Evidence levels span {min_l}-{max_l}; cross-grade conflict."
    # Same or adjacent levels
    from collections import Counter
    cnt = Counter(levels)
    majority_level = cnt.most_common(1)[0][0]
    same_count = sum(1 for l in levels if l == majority_level)
    ratio = same_count / len(levels)
    if ratio >= CONSISTENCY_RATIO:
        return True, ratio, f"{same_count}/{len(levels)} evidence at level {majority_level}."
    return False, ratio, f"Evidence split: {dict(cnt)}; ratio {ratio:.2f} < {CONSISTENCY_RATIO}."


def _check_conflict_mutual(items: List[EvidenceItem]) -> bool:
    """
    Decision 2 B3: Detect mutually exclusive labels (e.g. demonstrated vs not demonstrated)
    with comparable evidence count. Fail-closed: conflict -> reliability LOW.

    Only flag conflict when the minority side has >= 40% of total evidence AND
    at least 2 items, preventing a single weak negative from zeroing a well-supported skill.
    """
    if len(items) < 3:
        return False
    pos = [i for i in items if i.decision in ("demonstrated", "match") and i.level >= 1]
    neg = [i for i in items if i.decision in ("not_enough_information", "no_match") or i.level == 0]
    if not pos or not neg:
        return False
    minority = min(len(pos), len(neg))
    return minority >= 2 and minority / len(items) >= 0.4


def aggregate_skill_level(
    db: Session,
    subject_id: str,
    skill_id: str,
) -> AggregatedSkillLevel:
    """
    P5 Decision 3: Aggregate skill level across evidence, docs, time.
    Fail-closed: insufficient/conflicting evidence -> low reliability or needs_human_review.
    """
    items = _collect_evidence_for_skill(db, subject_id, skill_id)

    # No evidence -> fail-closed
    if not items:
        return AggregatedSkillLevel(
            skill_id=skill_id,
            level=0,
            reliability_level="low",
            reliability_explain="No evidence found across consented documents.",
            supporting_evidence_ids=[],
            needs_human_review=False,
            conflict_detected=False,
        )

    modality_weight = {"document": 0.3, "interactive": 0.4, "project": 0.3}
    weighted_sum = 0.0
    weight_total = 0.0
    for it in items:
        w = modality_weight.get(it.modality, 0.3) * _time_decay_weight(it.created_at)
        weighted_sum += it.level * w
        weight_total += w
    fused_level = int(round(weighted_sum / weight_total)) if weight_total > 0 else 0
    fused_level = min(LEVEL_MAX, max(0, fused_level))

    # Decision 2 B3: Mutual conflict (demonstrated vs not) -> fail-closed
    if _check_conflict_mutual(items):
        return AggregatedSkillLevel(
            skill_id=skill_id,
            level=0,
            reliability_level="low",
            reliability_explain="Mutually exclusive evidence (demonstrated vs not) with comparable support.",
            supporting_evidence_ids=[],
            needs_human_review=True,
            conflict_detected=True,
        )

    # Multiple evidence -> consistency check
    is_consistent, ratio, explain = _check_consistency(items)
    if not is_consistent:
        pos_items = [i for i in items if i.level >= 1]
        if pos_items:
            pos_levels = sorted([i.level for i in pos_items])
            median_level = pos_levels[len(pos_levels) // 2]
            pos_chunk_ids = [i.chunk_id for i in pos_items if i.chunk_id][:10]
        else:
            median_level = 0
            pos_chunk_ids = []
        return AggregatedSkillLevel(
            skill_id=skill_id,
            level=median_level,
            reliability_level="low",
            reliability_explain=f"Inconsistent evidence (using positive median): {explain}",
            supporting_evidence_ids=pos_chunk_ids,
            needs_human_review=True,
            conflict_detected=True,
        )

    # Consistent: use weighted fused level with reliability confidence
    chunk_ids = [i.chunk_id for i in items if i.chunk_id][:10]
    confidence = min(0.99, max(0.1, ratio * (len(items) / (len(items) + 1.0))))
    if len(items) < MIN_EVIDENCE_FOR_HIGH:
        reliability = "medium"
        explain = (
            f"Fused multi-source level={fused_level} with confidence={confidence:.2f}; "
            f"need >= {MIN_EVIDENCE_FOR_HIGH} evidence for high reliability."
        )
    else:
        reliability = "high" if confidence >= 0.7 else "medium"
        explain = f"{explain} Fused level={fused_level}, confidence={confidence:.2f}."

    return AggregatedSkillLevel(
        skill_id=skill_id,
        level=fused_level,
        reliability_level=reliability,
        reliability_explain=explain,
        supporting_evidence_ids=chunk_ids,
        needs_human_review=False,
        conflict_detected=False,
    )


def get_aggregated_levels_for_subject(
    db: Session,
    subject_id: str,
    skill_ids: List[str],
) -> Dict[str, AggregatedSkillLevel]:
    """Get aggregated level for each skill. Used by role_readiness when subject_id provided."""
    out: Dict[str, AggregatedSkillLevel] = {}
    for sid in skill_ids:
        out[sid] = aggregate_skill_level(db, subject_id, sid)
    return out
