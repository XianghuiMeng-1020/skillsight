import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

def ensure_change_table(engine: Engine):
    ddl = """
    CREATE TABLE IF NOT EXISTS change_logs (
        change_id UUID PRIMARY KEY,
        object_type TEXT NOT NULL,
        doc_id_text TEXT,
        key_text TEXT,
        change_summary JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_change_doc ON change_logs(doc_id_text);
    CREATE INDEX IF NOT EXISTS idx_change_created ON change_logs(created_at);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))

def log_change(engine: Engine, object_type: str, doc_id_text: Optional[str], key_text: Optional[str], change_summary: Dict[str, Any]):
    ensure_change_table(engine)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO change_logs (change_id, object_type, doc_id_text, key_text, change_summary, created_at)
                VALUES ((:cid)::uuid, :object_type, :doc_id_text, :key_text, (:summary)::jsonb, :created_at)
            """),
            {
                "cid": str(uuid.uuid4()),
                "object_type": object_type,
                "doc_id_text": doc_id_text,
                "key_text": key_text,
                "summary": json.dumps(change_summary, default=str),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

def diff_role_readiness(prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
    prev_sum = (prev or {}).get("summary") or {}
    curr_sum = (curr or {}).get("summary") or {}
    summary_changed = prev_sum != curr_sum

    prev_items = {it["skill_id"]: it for it in (prev or {}).get("items") or [] if isinstance(it, dict) and "skill_id" in it}
    curr_items = {it["skill_id"]: it for it in (curr or {}).get("items") or [] if isinstance(it, dict) and "skill_id" in it}

    item_changes = []
    for sid, cur in curr_items.items():
        pre = prev_items.get(sid)
        if not pre:
            item_changes.append({"skill_id": sid, "from": None, "to": cur.get("status")})
        else:
            if pre.get("status") != cur.get("status") or pre.get("observed_level") != cur.get("observed_level") or pre.get("target_level") != cur.get("target_level"):
                item_changes.append({
                    "skill_id": sid,
                    "from": {"status": pre.get("status"), "observed_level": pre.get("observed_level"), "target_level": pre.get("target_level")},
                    "to": {"status": cur.get("status"), "observed_level": cur.get("observed_level"), "target_level": cur.get("target_level")},
                })

    return {
        "summary_changed": summary_changed,
        "summary_from": prev_sum,
        "summary_to": curr_sum,
        "item_changes": item_changes,
        "has_change": summary_changed or len(item_changes) > 0,
    }

def list_changes(engine: Engine, doc_id: Optional[str], limit: int = 20):
    ensure_change_table(engine)
    limit = max(1, min(limit, 200))
    where = ""
    params = {"limit": limit}
    if doc_id:
        where = "WHERE doc_id_text = :doc_id"
        params["doc_id"] = doc_id

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT change_id, object_type, doc_id_text, key_text, change_summary, created_at
                FROM change_logs
                {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            params,
        ).mappings().all()

    return [dict(r) for r in rows]
