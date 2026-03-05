"""
P4 Protocol 5: Explainable Change Log Service

- Writes to skill_assessment_snapshots, role_readiness_snapshots, change_log_events
- Enforces denylist for staff/programme scope (no subject_id, chunk_text, stored_path, etc.)
- Evidence pointers: doc_id, chunk_id, char_start, char_end, quote_hash, snippet (<=300 chars)
- JSON fields capped at 10KB, truncated=true when exceeded
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# Denylist keys for staff/programme scope - must not appear in before_state/after_state/diff/why
DENYLIST_KEYS = frozenset({
    "subject_id", "user_id", "student_id", "chunk_text", "stored_path",
    "storage_uri", "embedding", "raw_response", "request_json", "retrieval_json",
})

MAX_JSON_BYTES = 10 * 1024  # 10KB
MAX_SNIPPET_CHARS = 300


def _truncate_json(obj: Any) -> tuple[Any, bool]:
    """Truncate JSON-serializable object to MAX_JSON_BYTES. Returns (obj, truncated)."""
    s = json.dumps(obj, default=str, ensure_ascii=False)
    if len(s.encode("utf-8")) <= MAX_JSON_BYTES:
        return obj, False
    # Truncate by removing nested content
    truncated = {"_truncated": True, "_original_size": len(s)}
    return truncated, True


def _sanitize_for_scope(data: Dict[str, Any], scope: str) -> Dict[str, Any]:
    """Remove denylist keys for staff/programme scope."""
    if scope in ("student", "admin"):
        return data
    out = {}
    for k, v in data.items():
        k_lower = k.lower() if isinstance(k, str) else ""
        if k_lower in DENYLIST_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = _sanitize_for_scope(v, scope)
        elif isinstance(v, list):
            out[k] = [_sanitize_for_scope(x, scope) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


def _build_evidence_pointers(
    db: Session,
    chunk_ids: List[str],
    doc_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Build evidence pointers from chunk_ids.
    Each pointer: doc_id, chunk_id, char_start, char_end, quote_hash, snippet (<=300).
    No chunk_text, stored_path, storage_uri, embedding.
    """
    if not chunk_ids:
        return []
    pointers = []
    for cid in chunk_ids[:10]:  # Limit to 10 pointers
        row = db.execute(
            text("""
                SELECT chunk_id, doc_id, char_start, char_end, quote_hash, snippet
                FROM chunks WHERE chunk_id = :cid LIMIT 1
            """),
            {"cid": cid},
        ).mappings().first()
        if not row:
            continue
        snippet = (row.get("snippet") or "")[:MAX_SNIPPET_CHARS]
        pointers.append({
            "doc_id": str(row.get("doc_id") or ""),
            "chunk_id": str(row.get("chunk_id") or cid),
            "char_start": row.get("char_start"),
            "char_end": row.get("char_end"),
            "quote_hash": row.get("quote_hash"),
            "snippet": snippet,
        })
    return pointers


def _cap_and_sanitize(
    obj: Dict[str, Any],
    scope: str,
) -> str:
    """Sanitize, truncate to 10KB, return JSON string."""
    sanitized = _sanitize_for_scope(obj, scope)
    s = json.dumps(sanitized, default=str, ensure_ascii=False)
    if len(s.encode("utf-8")) > MAX_JSON_BYTES:
        return json.dumps({"_truncated": True, "_size": len(s)}, default=str)
    return s


def write_skill_snapshot(
    db: Session,
    subject_id: str,
    skill_id: str,
    label: str,
    rationale: str,
    evidence_pointers: List[Dict[str, Any]],
    request_id: Optional[str] = None,
    level: Optional[int] = None,
    model_info: Optional[Dict[str, Any]] = None,
) -> str:
    """Write skill_assessment_snapshots row. Returns snapshot id."""
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    evidence_json = json.dumps(evidence_pointers[:20], default=str)[:MAX_JSON_BYTES]
    if len(evidence_json) > MAX_JSON_BYTES - 100:
        evidence_json = json.dumps([{"_truncated": True}], default=str)

    db.execute(
        text("""
            INSERT INTO skill_assessment_snapshots
            (id, subject_id, skill_id, label, level, rationale, evidence, request_id, model_info, created_at)
            VALUES (:id, :subject_id, :skill_id, :label, :level, :rationale, (:evidence)::jsonb, :request_id, (:model_info)::jsonb, :created_at)
        """),
        {
            "id": sid,
            "subject_id": subject_id,
            "skill_id": skill_id,
            "label": label,
            "level": level,
            "rationale": (rationale or "")[:500],
            "evidence": evidence_json,
            "request_id": request_id,
            "model_info": json.dumps(model_info or {}),
            "created_at": now,
        },
    )
    db.commit()
    return sid


def write_role_readiness_snapshot(
    db: Session,
    subject_id: str,
    role_id: str,
    score: float,
    breakdown: Dict[str, Any],
    request_id: Optional[str] = None,
) -> str:
    """Write role_readiness_snapshots row. Returns snapshot id."""
    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    breakdown_json = json.dumps(breakdown, default=str)
    if len(breakdown_json.encode("utf-8")) > MAX_JSON_BYTES:
        breakdown_json = json.dumps({"_truncated": True})

    db.execute(
        text("""
            INSERT INTO role_readiness_snapshots
            (id, subject_id, role_id, score, breakdown, request_id, created_at)
            VALUES (:id, :subject_id, :role_id, :score, (:breakdown)::jsonb, :request_id, :created_at)
        """),
        {
            "id": rid,
            "subject_id": subject_id,
            "role_id": role_id,
            "score": score,
            "breakdown": breakdown_json,
            "request_id": request_id,
            "created_at": now,
        },
    )
    db.commit()
    return rid


def write_change_event(
    db: Session,
    scope: str,
    event_type: str,
    subject_id: Optional[str],
    entity_key: Optional[str],
    before_state: Dict[str, Any],
    after_state: Dict[str, Any],
    diff: Dict[str, Any],
    why: Dict[str, Any],
    request_id: Optional[str] = None,
    actor_role: Optional[str] = None,
) -> str:
    """
    Write change_log_events row.
    before_state/after_state/diff/why are sanitized and capped at 10KB.
    """
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    before_json = _cap_and_sanitize(before_state, scope)
    after_json = _cap_and_sanitize(after_state, scope)
    diff_json = _cap_and_sanitize(diff, scope)
    why_json = _cap_and_sanitize(why, scope)

    db.execute(
        text("""
            INSERT INTO change_log_events
            (id, scope, subject_id, event_type, entity_key, before_state, after_state, diff, why, request_id, actor_role, created_at)
            VALUES (:id, :scope, :subject_id, :event_type, :entity_key, (:before_state)::jsonb, (:after_state)::jsonb, (:diff)::jsonb, (:why)::jsonb, :request_id, :actor_role, :created_at)
        """),
        {
            "id": eid,
            "scope": scope,
            "subject_id": subject_id,
            "event_type": event_type,
            "entity_key": entity_key,
            "before_state": before_json,
            "after_state": after_json,
            "diff": diff_json,
            "why": why_json,
            "request_id": request_id,
            "actor_role": actor_role,
            "created_at": now,
        },
    )
    db.commit()
    return eid


def get_prev_skill_snapshot(
    db: Session,
    subject_id: str,
    skill_id: str,
) -> Optional[Dict[str, Any]]:
    """Get latest skill_assessment_snapshots for subject+skill before now."""
    row = db.execute(
        text("""
            SELECT label, level, rationale, evidence, request_id, created_at
            FROM skill_assessment_snapshots
            WHERE subject_id = :subject_id AND skill_id = :skill_id
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"subject_id": subject_id, "skill_id": skill_id},
    ).mappings().first()
    if not row:
        return None
    evidence = row.get("evidence")
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except Exception:
            evidence = []
    return {
        "label": row["label"],
        "level": row.get("level"),
        "rationale": row.get("rationale"),
        "evidence": evidence or [],
    }


def get_prev_role_readiness_snapshot(
    db: Session,
    subject_id: str,
    role_id: str,
) -> Optional[Dict[str, Any]]:
    """Get latest role_readiness_snapshots for subject+role before now."""
    row = db.execute(
        text("""
            SELECT score, breakdown, request_id, created_at
            FROM role_readiness_snapshots
            WHERE subject_id = :subject_id AND role_id = :role_id
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"subject_id": subject_id, "role_id": role_id},
    ).mappings().first()
    if not row:
        return None
    breakdown = row.get("breakdown")
    if isinstance(breakdown, str):
        try:
            breakdown = json.loads(breakdown)
        except Exception:
            breakdown = {}
    return {
        "score": float(row["score"]),
        "breakdown": breakdown or {},
    }


def skill_changed(
    prev: Optional[Dict[str, Any]],
    curr: Dict[str, Any],
) -> bool:
    """True if label, level, or evidence pointers changed."""
    if not prev:
        return True
    pl = prev.get("label")
    cl = curr.get("label") or curr.get("decision")
    if pl != cl:
        return True
    if prev.get("level") != curr.get("level"):
        return True
    pe = prev.get("evidence") or []
    ce = curr.get("evidence_chunk_ids") or curr.get("evidence") or []
    if isinstance(ce, list) and ce:
        ce_ids = [x.get("chunk_id") if isinstance(x, dict) else x for x in ce]
    else:
        ce_ids = ce if isinstance(ce, list) else []
    pe_ids = [x.get("chunk_id") if isinstance(x, dict) else x for x in pe] if isinstance(pe, list) else []
    return set(pe_ids) != set(ce_ids)


def role_readiness_changed(
    prev: Optional[Dict[str, Any]],
    curr_score: float,
    curr_breakdown: Dict[str, Any],
    threshold: float = 0.01,
) -> bool:
    """True if score changed beyond threshold or breakdown key statuses changed."""
    if not prev:
        return True
    if abs(prev.get("score", 0) - curr_score) > threshold:
        return True
    prev_b = prev.get("breakdown") or {}
    curr_items = curr_breakdown.get("items") or curr_breakdown.get("breakdown", {}).get("items") or []
    prev_items = prev_b.get("items") or []
    prev_map = {x.get("skill_id"): x for x in prev_items if isinstance(x, dict) and x.get("skill_id")}
    curr_map = {x.get("skill_id"): x for x in curr_items if isinstance(x, dict) and x.get("skill_id")}
    for sid, cur in curr_map.items():
        pre = prev_map.get(sid)
        if not pre:
            return True
        if pre.get("status") != cur.get("status"):
            return True
    return False
