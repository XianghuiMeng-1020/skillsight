"""
Assessment Routes for SkillSight
- POST /assess/skill: Skill matching assessment
- POST /assess/proficiency: Proficiency level assessment
- POST /assess/role_readiness: Role readiness assessment (Decision 4)
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.deps import check_doc_access
from backend.app.security import Identity, require_auth
from backend.app.skill_level_aggregator import (
    get_aggregated_levels_for_subject,
    aggregate_skill_level,
    AggregatedSkillLevel,
)
from backend.app.change_log_events import (
    get_prev_skill_snapshot,
    write_skill_snapshot,
    write_change_event,
)
from backend.app.services.market_demand_index import compute_market_demand_index
from backend.app.services.semantic_job_matcher import match_job_skill_semantic
from backend.app.change_log_events import (
    get_prev_skill_snapshot,
    write_skill_snapshot,
    write_change_event,
)

router = APIRouter(prefix="/assess", tags=["assess"], dependencies=[Depends(require_auth)])
_log = logging.getLogger(__name__)


def _now_utc():
    return datetime.now(timezone.utc)


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


def _get_role_with_requirements(db: Session, role_id: str) -> Optional[Dict[str, Any]]:
    """Get role and its skill requirements."""
    # Get role
    role_sql = text("""
        SELECT role_id, role_title, description, created_at
        FROM roles
        WHERE role_id = :role_id
        LIMIT 1
    """)
    role_row = db.execute(role_sql, {"role_id": role_id}).mappings().first()
    if not role_row:
        return None
    
    role = dict(role_row)
    
    # Get skill requirements with canonical names
    req_sql = text("""
        SELECT rsr.req_id, rsr.role_id, rsr.skill_id, rsr.target_level, rsr.required, rsr.weight,
               s.canonical_name AS skill_name
        FROM role_skill_requirements rsr
        LEFT JOIN skills s ON s.skill_id = rsr.skill_id
        WHERE rsr.role_id = :role_id
        ORDER BY rsr.required DESC, rsr.skill_id ASC
    """)
    req_rows = db.execute(req_sql, {"role_id": role_id}).mappings().all()

    requirements = []
    for r in req_rows:
        requirements.append({
            "skill_id": r["skill_id"],
            "skill_name": r["skill_name"] or r["skill_id"],
            "target_level": int(r["target_level"]) if r["target_level"] is not None else 0,
            "required": bool(r["required"]),
            "weight": float(r["weight"]) if r["weight"] is not None else 1.0,
        })
    
    role["skills_required"] = requirements
    return role


def _get_skill_proficiency_for_doc(db: Session, doc_id: str) -> Dict[str, Dict[str, Any]]:
    """Get latest proficiency for each skill for a document."""
    sql = text("""
        SELECT DISTINCT ON (skill_id)
            skill_id, level, label, rationale, best_evidence, created_at
        FROM skill_proficiency
        WHERE doc_id = :doc_id
        ORDER BY skill_id, created_at DESC
    """)
    rows = db.execute(sql, {"doc_id": doc_id}).mappings().all()
    
    result = {}
    for r in rows:
        result[r["skill_id"]] = {
            "level": int(r["level"]) if r["level"] is not None else 0,
            "label": r["label"],
            "rationale": r["rationale"],
            "best_evidence": _coerce_json(r.get("best_evidence")) or {},
        }
    return result


def _get_skill_assessments_for_doc(db: Session, doc_id: str) -> Dict[str, Dict[str, Any]]:
    """Get latest assessment for each skill for a document."""
    sql = text("""
        SELECT DISTINCT ON (skill_id)
            skill_id, decision, evidence, decision_meta, created_at
        FROM skill_assessments
        WHERE doc_id = :doc_id
        ORDER BY skill_id, created_at DESC
    """)
    rows = db.execute(sql, {"doc_id": doc_id}).mappings().all()
    
    result = {}
    for r in rows:
        result[r["skill_id"]] = {
            "decision": r["decision"],
            "evidence": _coerce_json(r.get("evidence")) or [],
        }
    return result


def _determine_readiness_status(
    achieved_level: int,
    target_level: int,
    decision: str,
    required: bool
) -> str:
    """
    Determine readiness status for a skill.
    
    Returns:
    - "meet": demonstrated AND level >= target
    - "missing_proof": not enough information OR only mentioned OR no assessment
    - "needs_strengthening": demonstrated but level < target
    """
    # If no decision or not_enough_information -> missing_proof
    if not decision or decision in ("no_match", "not_enough_information"):
        return "missing_proof"
    
    # If only mentioned -> missing_proof
    if decision == "mentioned":
        return "missing_proof"
    
    # If demonstrated (match) -> check level
    if decision in ("match", "demonstrated"):
        if achieved_level >= target_level:
            return "meet"
        else:
            return "needs_strengthening"
    
    return "missing_proof"


def _calculate_readiness_score(items: List[Dict[str, Any]], demand_index: Optional[Dict[str, float]] = None) -> float:
    """
    Calculate weighted readiness score with proportional credit:
    - meet: 100%
    - needs_strengthening: proportional (achieved / target), minimum 30%
    - missing_proof (optional skill): 10%
    - missing_proof (required skill): 0%
    """
    total_weight = 0.0
    weighted_score = 0.0

    for item in items:
        demand_boost = 1.0 + 0.25 * float((demand_index or {}).get(item.get("skill_id", ""), 0.0))
        weight = item.get("weight", 1.0) * demand_boost
        status = item.get("status", "missing_proof")

        if status == "meet":
            score = 1.0
        elif status == "needs_strengthening":
            target = max(item.get("target_level", 1), 1)
            achieved = max(item.get("achieved_level", 0), 0)
            score = max(0.3, min(1.0, achieved / target))
        else:
            score = 0.0 if item.get("required", True) else 0.1

        weighted_score += score * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return round(weighted_score / total_weight, 4)


def _store_role_readiness(
    db: Session,
    doc_id: str,
    role_id: str,
    readiness_data: Dict[str, Any]
) -> str:
    """Store role readiness result."""
    readiness_id = str(uuid.uuid4())
    now = _now_utc()
    
    sql = text("""
        INSERT INTO role_readiness (
            readiness_id, doc_id, role_id, score, status_summary, items, created_at
        ) VALUES (
            :readiness_id, :doc_id, :role_id, :score, CAST(:status_summary AS JSONB), CAST(:items AS JSONB), :created_at
        )
    """)
    
    db.execute(sql, {
        "readiness_id": readiness_id,
        "doc_id": doc_id,
        "role_id": role_id,
        "score": readiness_data["score"],
        "status_summary": json.dumps(readiness_data["status_summary"]),
        "items": json.dumps(readiness_data["items"]),
        "created_at": now,
    })
    db.commit()
    
    return readiness_id


# === Helper Functions for Skill Assessment ===

def _get_skill_info(db: Session, skill_id: str) -> Optional[Dict[str, Any]]:
    """Get skill info including aliases."""
    sql = text("""
        SELECT s.skill_id, s.canonical_name, s.definition, s.evidence_rules, s.level_rubric_json,
               COALESCE(
                   (SELECT jsonb_agg(alias) FROM skill_aliases WHERE skill_id = s.skill_id AND status = 'active'),
                   '[]'::jsonb
               ) as aliases
        FROM skills s
        WHERE s.skill_id = :skill_id
        LIMIT 1
    """)
    row = db.execute(sql, {"skill_id": skill_id}).mappings().first()
    return dict(row) if row else None


def _get_chunks_for_doc(db: Session, doc_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Get chunks for a document."""
    sql = text("""
        SELECT chunk_id, doc_id, idx, char_start, char_end, snippet, chunk_text, quote_hash, created_at
        FROM chunks
        WHERE doc_id = :doc_id
        ORDER BY idx ASC
        LIMIT :limit
    """)
    rows = db.execute(sql, {"doc_id": doc_id, "limit": limit}).mappings().all()
    return [dict(r) for r in rows]


def _tokenize(s: str) -> List[str]:
    """Tokenize string into keywords."""
    if not s:
        return []
    s = s.lower()
    s = re.sub(r"[^a-z0-9_+\- ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.split(" ") if s else []


def _build_keyword_bank(canonical_name: str, aliases: Any) -> List[str]:
    """Build keyword bank from skill name and aliases."""
    bank = []
    bank.extend(_tokenize(canonical_name or ""))
    a = _coerce_json(aliases) or []
    if isinstance(a, str):
        a = [a]
    if isinstance(a, list):
        for x in a:
            bank.extend(_tokenize(str(x)))
    bank = [w for w in bank if w and len(w) >= 2]
    return sorted(set(bank))


def _count_hits(text_lower: str, keywords: List[str]) -> Tuple[int, List[str]]:
    """Count keyword hits in text."""
    hits = []
    cnt = 0
    for kw in keywords:
        n = len(re.findall(rf"\b{re.escape(kw)}\b", text_lower))
        if n > 0:
            hits.append(kw)
            cnt += n
    return cnt, sorted(set(hits))


def _level_from_hits(hit_count: int, hits: List[str]) -> Tuple[int, str]:
    """Determine proficiency level from hits."""
    strong_keywords = {
        "fastapi", "uvicorn", "sqlalchemy", "postgres", "psql", "consent", "pii",
        "anonymize", "de", "identify", "deidentify", "de-identify", "gdpr",
        "sha256", "hash", "citation", "plagiarism", "honesty"
    }
    strong_hits = [h for h in hits if h in strong_keywords]

    if hit_count <= 0:
        return 0, "no_match"
    if hit_count <= 2:
        return 1, "weak_match"
    if hit_count <= 5:
        return 2, "match"
    if hit_count >= 6 or len(strong_hits) >= 2:
        return 3, "strong_match"
    return 2, "match"


# === Request/Response Models ===

class SkillAssessRequest(BaseModel):
    skill_id: str
    doc_id: str
    k: int = Field(default=5, ge=1, le=50, description="Number of evidence chunks to return")
    store: bool = Field(default=False, description="If true, persist result to DB")


class ProficiencyAssessRequest(BaseModel):
    skill_id: str
    doc_id: str
    k: int = Field(default=10, ge=1, le=100, description="Number of chunks to analyze")
    store: bool = Field(default=False, description="If true, persist result to DB")


class RoleReadinessRequest(BaseModel):
    doc_id: str
    role_id: str
    subject_id: Optional[str] = Field(default=None, description="P5: when set, aggregate skill level across all consented docs")
    store: bool = Field(default=False, description="If true, persist result to DB")


# === Routes ===

@router.post("/skill")
def assess_skill(
    req: SkillAssessRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Skill matching assessment.
    
    Checks if a skill is demonstrated in a document by analyzing chunks for keyword matches.
    Returns decision (match/not_enough_information) and matched evidence.
    """
    check_doc_access(ident, req.doc_id, db)
    started = _now_utc()

    # Get skill info
    skill = _get_skill_info(db, req.skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {req.skill_id}")
    
    # Get document chunks
    chunks = _get_chunks_for_doc(db, req.doc_id, limit=200)
    if not chunks:
        return {
            "skill_id": req.skill_id,
            "doc_id": req.doc_id,
            "decision": "not_enough_information",
            "matched_terms": [],
            "best_evidence": None,
            "evidence_count": 0,
            "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
        }
    
    # Build keywords
    keywords = _build_keyword_bank(skill.get("canonical_name", ""), skill.get("aliases", []))
    
    # Find matches
    matched_chunks = []
    all_hits = []
    total_hit_count = 0
    
    for ch in chunks:
        txt = (ch.get("chunk_text") or ch.get("snippet") or "").lower()
        cnt, hits = _count_hits(txt, keywords)
        if cnt > 0:
            matched_chunks.append({
                "count": cnt,
                "hits": hits,
                "chunk": ch,
            })
            total_hit_count += cnt
            all_hits.extend(hits)
    
    all_hits = sorted(set(all_hits))
    
    # Determine decision
    if total_hit_count == 0:
        decision = "not_enough_information"
    else:
        decision = "match"
    
    # Get best evidence
    matched_chunks.sort(key=lambda x: x["count"], reverse=True)
    best_evidence = None
    if matched_chunks:
        best = matched_chunks[0]["chunk"]
        best_evidence = {
            "chunk_id": best.get("chunk_id"),
            "snippet": best.get("snippet", "")[:300],
            "idx": best.get("idx", 0),
        }
    
    # Optionally store
    if req.store and decision == "match":
        try:
            assessment_id = str(uuid.uuid4())
            sql = text("""
                INSERT INTO skill_assessments (assessment_id, doc_id, skill_id, decision, evidence, decision_meta, created_at)
                VALUES (:assessment_id, :doc_id, :skill_id, :decision, CAST(:evidence AS JSONB), CAST(:meta AS JSONB), :created_at)
            """)
            db.execute(sql, {
                "assessment_id": assessment_id,
                "doc_id": req.doc_id,
                "skill_id": req.skill_id,
                "decision": decision,
                "evidence": json.dumps([{"chunk_id": m["chunk"]["chunk_id"], "hits": m["hits"]} for m in matched_chunks[:req.k]]),
                "meta": json.dumps({"matched_terms": all_hits, "total_hits": total_hit_count}),
                "created_at": _now_utc(),
            })
            db.commit()
        except Exception as exc:
            _log.warning("skill assessment commit failed: %s", exc)
            db.rollback()
    
    return {
        "skill_id": req.skill_id,
        "doc_id": req.doc_id,
        "decision": decision,
        "matched_terms": all_hits,
        "best_evidence": best_evidence,
        "evidence_count": len(matched_chunks),
        "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
    }


@router.post("/proficiency")
def assess_proficiency(
    req: ProficiencyAssessRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Proficiency level assessment.
    
    Analyzes document chunks to determine proficiency level (0-3) for a skill.
    Returns level, label, rationale, and best evidence.
    """
    check_doc_access(ident, req.doc_id, db)
    started = _now_utc()

    # Get skill info
    skill = _get_skill_info(db, req.skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {req.skill_id}")
    
    # Get document chunks
    chunks = _get_chunks_for_doc(db, req.doc_id, limit=req.k)
    if not chunks:
        return {
            "skill_id": req.skill_id,
            "doc_id": req.doc_id,
            "level": 0,
            "label": "no_evidence",
            "rationale": "No document chunks found for analysis.",
            "best_evidence": None,
            "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
        }
    
    # Build keywords
    keywords = _build_keyword_bank(skill.get("canonical_name", ""), skill.get("aliases", []))
    
    # Analyze all chunks
    all_hits = []
    total_hit_count = 0
    best_chunk = None
    best_chunk_hits = 0
    
    for ch in chunks:
        txt = (ch.get("chunk_text") or ch.get("snippet") or "").lower()
        cnt, hits = _count_hits(txt, keywords)
        if cnt > 0:
            total_hit_count += cnt
            all_hits.extend(hits)
            if cnt > best_chunk_hits:
                best_chunk_hits = cnt
                best_chunk = ch
    
    all_hits = sorted(set(all_hits))
    
    # Determine level
    level, label = _level_from_hits(total_hit_count, all_hits)
    
    # Build rationale
    if level == 0:
        rationale = f"No evidence found for '{skill.get('canonical_name', req.skill_id)}' in the document."
    elif level == 1:
        rationale = f"Weak evidence found: {total_hit_count} keyword matches ({', '.join(all_hits[:5])})."
    elif level == 2:
        rationale = f"Moderate evidence found: {total_hit_count} keyword matches across {len([h for h in all_hits])} terms."
    else:
        rationale = f"Strong evidence found: {total_hit_count} keyword matches with key terms ({', '.join(all_hits[:5])})."
    
    # Best evidence
    best_evidence = None
    if best_chunk:
        best_evidence = {
            "chunk_id": best_chunk.get("chunk_id"),
            "snippet": best_chunk.get("snippet", "")[:300],
            "idx": best_chunk.get("idx", 0),
        }
    
    # Optionally store
    if req.store:
        try:
            prof_id = str(uuid.uuid4())
            sql = text("""
                INSERT INTO skill_proficiency (prof_id, doc_id, skill_id, level, label, rationale, best_evidence, signals, meta, created_at)
                VALUES (:prof_id, :doc_id, :skill_id, :level, :label, :rationale, CAST(:best_evidence AS JSONB), CAST(:signals AS JSONB), CAST(:meta AS JSONB), :created_at)
            """)
            db.execute(sql, {
                "prof_id": prof_id,
                "doc_id": req.doc_id,
                "skill_id": req.skill_id,
                "level": level,
                "label": label,
                "rationale": rationale,
                "best_evidence": json.dumps(best_evidence or {}),
                "signals": json.dumps({"hit_count": total_hit_count, "keywords_hit": all_hits}),
                "meta": json.dumps({"chunks_analyzed": len(chunks)}),
                "created_at": _now_utc(),
            })
            db.commit()
        except Exception as exc:
            _log.warning("proficiency assessment commit failed: %s", exc)
            db.rollback()
    
    return {
        "skill_id": req.skill_id,
        "doc_id": req.doc_id,
        "level": level,
        "label": label,
        "rationale": rationale,
        "best_evidence": best_evidence,
        "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
    }


@router.post("/role_readiness")
def role_readiness(
    req: RoleReadinessRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Decision 4: Role Readiness Assessment.
    
    Compares student's skill profile (from skill_proficiency + skill_assessments)
    against a role's skill requirements.
    
    Returns for each skill:
    - meet: demonstrated AND level >= target
    - missing_proof: not enough information / only mentioned
    - needs_strengthening: demonstrated but level < target
    """
    started = _now_utc()
    check_doc_access(ident, req.doc_id, db)
    # Get role with requirements
    role = _get_role_with_requirements(db, req.role_id)
    if not role:
        raise HTTPException(status_code=404, detail=f"Role not found: {req.role_id}")
    
    requirements = role.get("skills_required", [])
    if not requirements:
        return {
            "doc_id": req.doc_id,
            "role_id": req.role_id,
            "role_title": role.get("role_title", ""),
            "score": 1.0,
            "status_summary": {"meet": 0, "needs_strengthening": 0, "missing_proof": 0},
            "items": [],
            "message": "Role has no skill requirements.",
            "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
        }
    
    # P5: Use aggregator when subject_id provided; else single-doc
    use_aggregator = bool(req.subject_id)
    skill_ids_req = [r["skill_id"] for r in requirements]

    if use_aggregator:
        aggregated = get_aggregated_levels_for_subject(db, req.subject_id, skill_ids_req)
        proficiency_map = {}
        assessment_map = {}
        for sid, agg in aggregated.items():
            proficiency_map[sid] = {"level": agg.level, "rationale": agg.reliability_explain}
            assessment_map[sid] = {
                "decision": "demonstrated" if agg.level >= 1 and not agg.conflict_detected else ("not_enough_information" if agg.conflict_detected else "not_assessed"),
                "evidence": [{"chunk_id": cid} for cid in agg.supporting_evidence_ids[:3]],
            }
    else:
        proficiency_map = _get_skill_proficiency_for_doc(db, req.doc_id)
        assessment_map = _get_skill_assessments_for_doc(db, req.doc_id)

    # Evaluate each requirement
    items = []
    status_counts = {"meet": 0, "needs_strengthening": 0, "missing_proof": 0}

    for req_item in requirements:
        skill_id = req_item["skill_id"]
        skill_name = req_item.get("skill_name", skill_id)
        target_level = req_item["target_level"]
        required = req_item["required"]
        weight = req_item["weight"]

        # Get achieved level and decision
        prof = proficiency_map.get(skill_id, {})
        assess = assessment_map.get(skill_id, {})

        achieved_level = prof.get("level", 0)
        decision = assess.get("decision", "")
        evidence = assess.get("evidence", [])
        rationale = prof.get("rationale", "")

        # P5: Add reliability when using aggregator
        agg_meta = {}
        if use_aggregator and skill_id in aggregated:
            a = aggregated[skill_id]
            agg_meta = {
                "reliability_level": a.reliability_level,
                "reliability_explain": a.reliability_explain,
                "supporting_evidence_ids": a.supporting_evidence_ids,
                "needs_human_review": a.needs_human_review,
            }
            if a.needs_human_review and a.level == 0:
                decision = "not_enough_information"

        # Determine status (P5: meets/missing_proof/needs_strengthening)
        status = _determine_readiness_status(achieved_level, target_level, decision, required)
        status_counts[status] += 1
        if status == "missing_proof" and required:
            gap_severity = "critical"
        elif status == "needs_strengthening":
            gap_severity = "moderate"
        else:
            gap_severity = "minor"

        rec_hours = max(2, (target_level - achieved_level) * 12) if status != "meet" else 0
        learning_path = [] if status == "meet" else [
            f"Take HKU course mapped to {skill_name}",
            f"Complete one project artifact and upload evidence for {skill_name}",
            f"Expected effort: ~{rec_hours} hours",
        ]

        # Build explanation (P5: why links to pointers)
        if status == "meet":
            explanation = f"Demonstrated at level {achieved_level} (target: {target_level})."
        elif status == "needs_strengthening":
            explanation = f"Demonstrated at level {achieved_level}, but target is {target_level}. Consider more practice or evidence."
        else:
            if not decision:
                explanation = "No assessment found. Run skill assessment first."
            elif decision == "mentioned":
                explanation = "Skill was mentioned but not demonstrated with concrete evidence."
            elif agg_meta.get("needs_human_review"):
                explanation = "Conflicting evidence; needs human review."
            else:
                explanation = "Insufficient evidence to demonstrate this skill."

        sem = match_job_skill_semantic(
            role.get("description", "") or role.get("role_title", ""),
            [rationale] + [str(e.get("snippet", "")) for e in (evidence or []) if isinstance(e, dict)],
        )
        item = {
            "skill_id": skill_id,
            "skill_name": skill_name,
            "target_level": target_level,
            "achieved_level": achieved_level,
            "required": required,
            "weight": weight,
            "status": status,
            "decision": decision or "not_assessed",
            "explanation": explanation,
            "evidence": evidence[:3] if evidence else [],
            "gap_severity": gap_severity,
            "learning_path": learning_path,
            "estimated_hours": rec_hours,
            "semantic_alignment": sem,
        }
        if agg_meta:
            item["reliability_level"] = agg_meta.get("reliability_level")
            item["reliability_explain"] = agg_meta.get("reliability_explain")
            item["supporting_evidence_ids"] = agg_meta.get("supporting_evidence_ids", [])
        items.append(item)
    
    # Calculate overall score
    demand_index = compute_market_demand_index(db)
    score = _calculate_readiness_score(items, demand_index=demand_index)
    
    # Decision 2 B1: overall reliability for role_readiness
    agg_items = [it for it in items if it.get("reliability_level")]
    if not agg_items:
        overall_reliability = "medium"
        reliability_reason = "Single-doc assessment; aggregate reliability not computed."
    else:
        low_count = sum(1 for it in agg_items if it.get("reliability_level") == "low")
        if low_count >= len(agg_items) / 2:
            overall_reliability = "low"
            reliability_reason = "Multiple skills have low reliability (conflict or insufficient evidence)."
        elif low_count > 0:
            overall_reliability = "medium"
            reliability_reason = "Some skills have uncertain reliability."
        else:
            overall_reliability = "high"
            reliability_reason = "Evidence consistent across skills."

    result = {
        "doc_id": req.doc_id,
        "role_id": req.role_id,
        "role_title": role.get("role_title", ""),
        "score": score,
        "status_summary": status_counts,
        "items": items,
        "reliability": {"level": overall_reliability, "reason_codes": [reliability_reason]},
        "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
    }
    
    # Optionally persist
    if req.store:
        try:
            readiness_id = _store_role_readiness(db, req.doc_id, req.role_id, result)
            result["readiness_id"] = readiness_id
            result["stored"] = True
        except Exception as e:
            result["stored"] = False
            result["store_error"] = str(e)

    # P5: Write skill_assessment_snapshots + change_log when aggregator used and level/reliability changed
    if use_aggregator and req.subject_id:
        try:
            request_id = str(uuid.uuid4())
            for sid, agg in aggregated.items():
                prev = get_prev_skill_snapshot(engine, req.subject_id, sid)
                prev_level = prev.get("level") if prev else None
                prev_ev = (prev.get("evidence") or []) if prev else []
                curr_ev_ids = set(agg.supporting_evidence_ids)
                prev_ev_ids = set(
                    e.get("chunk_id") if isinstance(e, dict) else e for e in prev_ev if e
                )
                changed = (
                    prev_level != agg.level
                    or prev_ev_ids != curr_ev_ids
                )
                if changed:
                    write_skill_snapshot(
                        engine,
                        req.subject_id,
                        sid,
                        label=f"level_{agg.level}",
                        rationale=agg.reliability_explain,
                        level=agg.level,
                        evidence=[{"chunk_id": c} for c in agg.supporting_evidence_ids[:10]],
                        request_id=request_id,
                        model_info={"aggregator": "p5", "reliability": agg.reliability_level},
                    )
                    write_change_event(
                        engine,
                        scope="student",
                        event_type="skill_level_changed",
                        subject_id=req.subject_id,
                        entity_key=sid,
                        before_state={"level": prev_level, "evidence_count": len(prev_ev_ids)},
                        after_state={"level": agg.level, "evidence_count": len(curr_ev_ids), "reliability_level": agg.reliability_level},
                        diff={"level_delta": (agg.level - (prev_level or 0))},
                        why={"rule_triggers": ["skill_level_aggregator"], "supporting_evidence_ids": agg.supporting_evidence_ids[:5]},
                        request_id=request_id,
                        actor_role="system",
                    )
        except Exception as exc:
            _log.warning("P5 snapshot/changelog write failed (non-blocking): %s", exc)

    return result


@router.get("/role_readiness")
def list_role_readiness(
    doc_id: str,
    limit: int = 50,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List stored role readiness assessments for a document."""
    sql = text("""
        SELECT readiness_id, doc_id, role_id, score, status_summary, items, created_at
        FROM role_readiness
        WHERE doc_id = :doc_id
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    
    try:
        rows = db.execute(sql, {"doc_id": doc_id, "limit": limit}).mappings().all()
        items = []
        for r in rows:
            items.append({
                "readiness_id": r["readiness_id"],
                "doc_id": r["doc_id"],
                "role_id": r["role_id"],
                "score": float(r["score"]) if r["score"] else 0.0,
                "status_summary": _coerce_json(r.get("status_summary")) or {},
                "items": _coerce_json(r.get("items")) or [],
                "created_at": str(r["created_at"]),
            })
        return {"count": len(items), "items": items}
    except Exception as e:
        # Table might not exist yet
        return {"count": 0, "items": [], "error": str(e)}
