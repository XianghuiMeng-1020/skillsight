"""
P4 Protocol 5: Explainable Change Log service.

- Writes skill_assessment_snapshots, role_readiness_snapshots, change_log_events
- Enforces denylist for staff/programme (no subject_id, chunk_text, stored_path, etc.)
- Evidence pointers: doc_id, chunk_id, char_start, char_end, quote_hash, snippet (<=300 chars)
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Max single JSON field size (bytes). Beyond this, truncate and set truncated=true.
_JSON_MAX = 10 * 1024

# Denylist keys for staff/programme output
_DENYLIST_KEYS = frozenset({
    "subject_id", "user_id", "student_id", "chunk_text", "stored_path",
    "storage_uri", "embedding", "raw_response",
})


def _truncate_json(obj: Any, max_bytes: int = _JSON_MAX) -> Tuple[Any, bool]:
    """Truncate JSON-serializable object if it exceeds max_bytes. Returns (obj, truncated)."""
    s = json.dumps(obj, default=str)
    if len(s.encode("utf-8")) <= max_bytes:
        return obj, False
    truncated = {"_truncated": True, "_original_size": len(s), "_preview": s[:500]}
    return truncated, True


def _sanitize_for_scope(obj: Any, scope: str) -> Any:
    """Remove denylist keys for staff/programme scopes."""
    if scope in ("staff", "programme") and isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(d in k_lower for d in _DENYLIST_KEYS):
                continue
            out[k] = _sanitize_for_scope(v, scope)
        return out
    if isinstance(obj, list):
        return [_sanitize_for_scope(x, scope) for x in obj]
    return obj


def _build_evidence_pointer(
    doc_id: str,
    chunk_id: str,
    snippet: str,
    char_start: Optional[int] = None,
    char_end: Optional[int] = None,
    quote_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a compliant evidence pointer. Snippet max 300 chars."""
    p: Dict[str, Any] = {
        "doc_id": doc_id,
        "chunk_id": chunk_id,
        "snippet": (snippet or "")[:300],
    }
    if char_start is not None:
        p["char_start"] = char_start
    if char_end is not None:
        p["char_end"] = char_end
    if quote_hash:
        p["quote_hash"] = quote_hash
    return p


def write_skill_snapshot(
    engine: Engine,
    subject_id: str,
    skill_id: str,
    label: str,
    rationale: str = "",
    level: Optional[int] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    request_id: Optional[str] = None,
    model_info: Optional[Dict[str, Any]] = None,
) -> str:
    """Write skill_assessment_snapshots row. Returns snapshot id."""
    sid = str(uuid.uuid4())
    ev = evidence or []
    mi = model_info or {}
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO skill_assessment_snapshots
                (id, subject_id, skill_id, label, level, rationale, evidence, request_id, model_info, created_at)
                VALUES (:id, :subject_id, :skill_id, :label, :level, :rationale, (:ev)::jsonb, :request_id, (:mi)::jsonb, :created_at)
            """),
            {
                "id": sid,
                "subject_id": subject_id,
                "skill_id": skill_id,
                "label": label,
                "level": level,
                "rationale": (rationale or "")[:2000],
                "ev": json.dumps(ev),
                "request_id": request_id,
                "mi": json.dumps(mi),
                "created_at": datetime.now(timezone.utc),
            },
        )
    return sid


def write_role_readiness_snapshot(
    engine: Engine,
    subject_id: str,
    role_id: str,
    score: float,
    breakdown: Dict[str, Any],
    request_id: Optional[str] = None,
) -> str:
    """Write role_readiness_snapshots row. Returns snapshot id."""
    rid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
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
                "breakdown": json.dumps(breakdown),
                "request_id": request_id,
                "created_at": datetime.now(timezone.utc),
            },
        )
    return rid


def write_change_event(
    engine: Engine,
    scope: str,
    event_type: str,
    subject_id: Optional[str] = None,
    entity_key: Optional[str] = None,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    diff: Optional[Dict[str, Any]] = None,
    why: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    actor_role: Optional[str] = None,
) -> str:
    """Write change_log_events row. Truncates large JSON. Returns event id."""
    eid = str(uuid.uuid4())
    bs = before_state or {}
    as_ = after_state or {}
    df = diff or {}
    wh = why or {}

    bs, _ = _truncate_json(bs)
    as_, _ = _truncate_json(as_)
    df, _ = _truncate_json(df)
    wh, _ = _truncate_json(wh)

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO change_log_events
                (id, scope, subject_id, event_type, entity_key, before_state, after_state, diff, why, request_id, actor_role, created_at)
                VALUES (:id, :scope, :subject_id, :event_type, :entity_key, (:bs)::jsonb, (:as)::jsonb, (:diff)::jsonb, (:why)::jsonb, :request_id, :actor_role, :created_at)
            """),
            {
                "id": eid,
                "scope": scope,
                "subject_id": subject_id,
                "event_type": event_type,
                "entity_key": entity_key,
                "bs": json.dumps(bs, default=str),
                "as": json.dumps(as_, default=str),
                "diff": json.dumps(df, default=str),
                "why": json.dumps(wh, default=str),
                "request_id": request_id,
                "actor_role": actor_role,
                "created_at": datetime.now(timezone.utc),
            },
        )
    return eid


def get_prev_skill_snapshot(engine: Engine, subject_id: str, skill_id: str) -> Optional[Dict[str, Any]]:
    """Get latest skill snapshot for subject+skill."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, label, level, rationale, evidence, request_id, created_at
                FROM skill_assessment_snapshots
                WHERE subject_id = :sub AND skill_id = :sid
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"sub": subject_id, "sid": skill_id},
        ).mappings().first()
    if not row:
        return None
    d = dict(row)
    d["evidence"] = json.loads(d["evidence"]) if isinstance(d.get("evidence"), str) else (d.get("evidence") or [])
    return d


def get_prev_role_readiness_snapshot(engine: Engine, subject_id: str, role_id: str) -> Optional[Dict[str, Any]]:
    """Get latest role readiness snapshot for subject+role."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, score, breakdown, request_id, created_at
                FROM role_readiness_snapshots
                WHERE subject_id = :sub AND role_id = :rid
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"sub": subject_id, "rid": role_id},
        ).mappings().first()
    if not row:
        return None
    d = dict(row)
    d["breakdown"] = json.loads(d["breakdown"]) if isinstance(d.get("breakdown"), str) else (d.get("breakdown") or {})
    return d


def list_change_log_student(
    engine: Engine,
    subject_id: str,
    limit: int = 50,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    """List change_log_events for a student. Returns items + next_cursor."""
    limit = max(1, min(limit, 200))
    params: Dict[str, Any] = {"sub": subject_id, "lim": limit + 1}

    cursor_sql = ""
    if cursor:
        cursor_sql = "AND created_at < (SELECT created_at FROM change_log_events WHERE id = :cursor::uuid)"
        params["cursor"] = cursor

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, event_type, entity_key, before_state, after_state, diff, why, request_id, actor_role, created_at
                FROM change_log_events
                WHERE scope = 'student' AND subject_id = :sub {cursor_sql}
                ORDER BY created_at DESC
                LIMIT :lim
            """),
            params,
        ).mappings().all()

    items = []
    next_cursor = None
    for i, r in enumerate(rows):
        if i >= limit:
            next_cursor = str(r["id"])
            break
        d = dict(r)
        bs = d.get("before_state") or {}
        as_ = d.get("after_state") or {}
        if isinstance(bs, str):
            try:
                bs = json.loads(bs)
            except Exception:
                bs = {}
        if isinstance(as_, str):
            try:
                as_ = json.loads(as_)
            except Exception:
                as_ = {}
        summary = _make_summary(d["event_type"], d["entity_key"], bs, as_)
        items.append({
            "id": str(d["id"]),
            "event_type": d["event_type"],
            "created_at": d["created_at"].isoformat() if d.get("created_at") else None,
            "summary": summary,
            "before_state": bs,
            "after_state": as_,
            "diff": json.loads(d["diff"]) if isinstance(d.get("diff"), str) else (d.get("diff") or {}),
            "why": json.loads(d["why"]) if isinstance(d.get("why"), str) else (d.get("why") or {}),
            "request_id": d.get("request_id"),
        })
    return {"items": items, "next_cursor": next_cursor}


def _make_summary(event_type: str, entity_key: Optional[str], before: Dict, after: Dict) -> str:
    """Generate human-readable summary for UI list."""
    if event_type == "skill_level_changed":
        b_level = (before or {}).get("level")
        a_level = (after or {}).get("level")
        skill = entity_key or "skill"
        if b_level is not None and a_level is not None:
            return f"{skill} level: {b_level} -> {a_level}"
        return f"{skill} level updated"
    if event_type == "skill_changed":
        b_label = (before or {}).get("label", "?")
        a_label = (after or {}).get("label", "?")
        skill = entity_key or "skill"
        return f"{skill}: {b_label} -> {a_label}"
    if event_type == "role_readiness_changed":
        b_score = (before or {}).get("score")
        a_score = (after or {}).get("score")
        role = entity_key or "role"
        if b_score is not None and a_score is not None:
            return f"{role} readiness: {float(b_score)*100:.0f}% -> {float(a_score)*100:.0f}%"
        return f"{role} readiness updated"
    if event_type == "consent_withdrawn":
        return "Consent withdrawn"
    if event_type == "document_deleted":
        return "Document deleted"
    if event_type == "actions_changed":
        return "Actions updated"
    if event_type == "human_review_resolved":
        decision = (after or {}).get("decision", "?")
        return f"Review ticket resolved: {decision}"
    return f"{event_type}: {entity_key or 'N/A'}"


def list_change_log_admin(
    engine: Engine,
    subject_id: Optional[str] = None,
    event_type: Optional[str] = None,
    request_id: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    scope: str = "admin",
) -> Dict[str, Any]:
    """List change_log_events for admin search. Applies denylist for staff/programme."""
    limit = max(1, min(limit, 200))
    conditions = ["1=1"]
    params: Dict[str, Any] = {"lim": limit + 1}
    if subject_id:
        conditions.append("subject_id = :subject_id")
        params["subject_id"] = subject_id
    if event_type:
        conditions.append("event_type = :event_type")
        params["event_type"] = event_type
    if request_id:
        conditions.append("request_id = :request_id")
        params["request_id"] = request_id
    if since:
        conditions.append("created_at >= :since::timestamptz")
        params["since"] = since
    if until:
        conditions.append("created_at <= :until::timestamptz")
        params["until"] = until
    cursor_sql = ""
    if cursor:
        cursor_sql = "AND created_at < (SELECT created_at FROM change_log_events WHERE id = :cursor::uuid)"
        params["cursor"] = cursor

    where = " AND ".join(conditions)
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, scope, subject_id, event_type, entity_key, before_state, after_state, diff, why, request_id, actor_role, created_at
                FROM change_log_events
                WHERE {where} {cursor_sql}
                ORDER BY created_at DESC
                LIMIT :lim
            """),
            params,
        ).mappings().all()

    items = []
    next_cursor = None
    for i, r in enumerate(rows):
        if i >= limit:
            next_cursor = str(r["id"])
            break
        d = dict(r)
        bs = d.get("before_state") or {}
        as_ = d.get("after_state") or {}
        df = d.get("diff") or {}
        wh = d.get("why") or {}
        for j, obj in enumerate([bs, as_, df, wh]):
            if isinstance(obj, str):
                try:
                    obj = json.loads(obj)
                except Exception:
                    obj = {}
                if j == 0:
                    bs = obj
                elif j == 1:
                    as_ = obj
                elif j == 2:
                    df = obj
                else:
                    wh = obj
        bs = _sanitize_for_scope(bs, scope)
        as_ = _sanitize_for_scope(as_, scope)
        df = _sanitize_for_scope(df, scope)
        wh = _sanitize_for_scope(wh, scope)
        summary = _make_summary(d["event_type"], d["entity_key"], bs, as_)
        items.append({
            "id": str(d["id"]),
            "scope": d["scope"],
            "subject_id": d.get("subject_id"),
            "event_type": d["event_type"],
            "entity_key": d.get("entity_key"),
            "created_at": d["created_at"].isoformat() if d.get("created_at") else None,
            "summary": summary,
            "before_state": bs,
            "after_state": as_,
            "diff": df,
            "why": wh,
            "request_id": d.get("request_id"),
            "actor_role": d.get("actor_role"),
        })
    return {"items": items, "next_cursor": next_cursor}
