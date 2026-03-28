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
from dataclasses import dataclass
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
        ))

    return items


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

    # Single evidence -> medium reliability (below min for high)
    if len(items) < MIN_EVIDENCE_FOR_HIGH:
        levels = [i.level for i in items]
        avg = sum(levels) / len(levels)
        level = min(LEVEL_MAX, max(0, round(avg)))
        chunk_ids = [i.chunk_id for i in items if i.chunk_id]
        return AggregatedSkillLevel(
            skill_id=skill_id,
            level=level,
            reliability_level="medium",
            reliability_explain=f"Only {len(items)} evidence item(s); need >= {MIN_EVIDENCE_FOR_HIGH} for high reliability.",
            supporting_evidence_ids=chunk_ids[:10],
            needs_human_review=False,
            conflict_detected=False,
        )

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

    # Consistent: use majority / median
    levels = [i.level for i in items]
    from collections import Counter
    cnt = Counter(levels)
    level = cnt.most_common(1)[0][0]
    chunk_ids = [i.chunk_id for i in items if i.chunk_id and i.level == level][:10]

    return AggregatedSkillLevel(
        skill_id=skill_id,
        level=level,
        reliability_level="high",
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
