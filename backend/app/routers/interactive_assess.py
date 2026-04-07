"""
Interactive Assessment Routes for SkillSight
- Communication Assessment (Kira-style video response)
- Programming Assessment (LeetCode-style coding challenges)
- Writing Assessment (Timed writing with anti-copy protection)
"""
import hashlib
import logging
import os
import json
import random
import re
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from backend.app.db.deps import get_db
    from backend.app.queue import enqueue_assessment_repair
    from backend.app.security import require_auth
except ImportError:
    from app.db.deps import get_db
    from app.queue import enqueue_assessment_repair
    from app.security import require_auth
from backend.app.services.irt_estimator import IRTItemResult, estimate_theta, theta_to_level

router = APIRouter(prefix="/interactive", tags=["interactive-assessment"], dependencies=[Depends(require_auth)])

DEFAULT_MODEL_VERSION = os.getenv("ASSESSMENT_MODEL_VERSION", "heuristic-v1")
DEFAULT_RUBRIC_VERSION = os.getenv("ASSESSMENT_RUBRIC_VERSION", "rubric-v1")
REPAIR_MAX_ATTEMPTS = max(1, int(os.getenv("ASSESSMENT_REPAIR_MAX_ATTEMPTS", "5")))
_log = logging.getLogger(__name__)

def _get_llm_generate():
    """Return (model, prompt, temperature, timeout_s) -> str or None if unavailable."""
    provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if provider == "ollama":
        try:
            from backend.app.ollama_client import ollama_generate
            return ollama_generate
        except ImportError:
            return None
    try:
        from backend.app.openai_client import openai_generate
        return openai_generate
    except ImportError:
        return None

EVAL_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_INPUT_CHARS = 2000

def _llm_evaluate(prompt_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """Load prompt template, format with kwargs, call LLM, parse JSON. Returns None on any failure."""
    import pathlib
    backend_prompts = pathlib.Path(__file__).resolve().parents[2] / "prompts"
    pkg_prompts = pathlib.Path(__file__).resolve().parents[3] / "packages" / "prompts"
    path = backend_prompts / prompt_name
    if not path.exists():
        path = pkg_prompts / prompt_name
    if not path.exists():
        return None
    template = path.read_text(encoding="utf-8")
    # Replace placeholders (do content keys last so user content cannot inject placeholder names)
    content_keys = {"transcript", "content", "code", "analysis", "response", "outline", "question", "dataset_summary", "visualization", "case_description", "topic"}
    order_key = lambda kv: (1 if kv[0] in content_keys else 0, kv[0])
    prompt_text = template
    for k, v in sorted(kwargs.items(), key=order_key):
        if isinstance(v, str) and len(v) > MAX_INPUT_CHARS:
            v = v[:MAX_INPUT_CHARS] + "..."
        else:
            v = v if v is not None else ""
        prompt_text = prompt_text.replace("{" + k + "}", str(v))
    generate = _get_llm_generate()
    if not generate:
        return None
    try:
        raw = generate(EVAL_MODEL, prompt_text, temperature=0.2, timeout_s=60)
    except Exception as e:
        _log.warning("LLM evaluate failed for %s: %s", prompt_name, e)
        return None
    if not raw or not raw.strip():
        return None
    # Strip markdown code block if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    try:
        out = json.loads(raw)
        if not isinstance(out, dict):
            return None
        return out
    except json.JSONDecodeError:
        return None


def _now_utc():
    return datetime.now(timezone.utc)


def _generate_session_token() -> str:
    return secrets.token_urlsafe(32)


# ====================
# Database Models (inline for now)
# ====================
def ensure_assessment_tables(db: Session):
    """Create assessment tables if they don't exist."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS assessment_sessions (
            session_id UUID PRIMARY KEY,
            user_id TEXT NOT NULL,
            assessment_type TEXT NOT NULL,
            skill_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            config JSONB,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        
        CREATE TABLE IF NOT EXISTS assessment_attempts (
            attempt_id UUID PRIMARY KEY,
            session_id UUID NOT NULL REFERENCES assessment_sessions(session_id),
            attempt_number INTEGER NOT NULL DEFAULT 1,
            prompt_data JSONB,
            response_data JSONB,
            evaluation JSONB,
            score FLOAT,
            started_at TIMESTAMPTZ,
            submitted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON assessment_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_attempts_session ON assessment_attempts(session_id);

        CREATE TABLE IF NOT EXISTS assessment_submit_idempotency (
            idem_id UUID PRIMARY KEY,
            session_id UUID NOT NULL,
            endpoint TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            response_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (session_id, endpoint, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS idx_assessment_idem_session ON assessment_submit_idempotency(session_id, endpoint);

        CREATE TABLE IF NOT EXISTS assessment_repair_jobs (
            repair_job_id UUID PRIMARY KEY,
            session_id UUID NOT NULL,
            attempt_id UUID,
            user_id TEXT NOT NULL,
            skill_id TEXT,
            assessment_type TEXT NOT NULL,
            response_text TEXT,
            evaluation JSONB,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            next_retry_at TIMESTAMPTZ,
            dead_lettered_at TIMESTAMPTZ,
            dead_letter_reason TEXT,
            last_error TEXT,
            rq_job_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_assessment_repair_status ON assessment_repair_jobs(status, created_at DESC);
        ALTER TABLE assessment_repair_jobs ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 5;
        ALTER TABLE assessment_repair_jobs ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ;
        ALTER TABLE assessment_repair_jobs ADD COLUMN IF NOT EXISTS dead_lettered_at TIMESTAMPTZ;
        ALTER TABLE assessment_repair_jobs ADD COLUMN IF NOT EXISTS dead_letter_reason TEXT;

        CREATE TABLE IF NOT EXISTS assessment_drift_samples (
            sample_id UUID PRIMARY KEY,
            session_id UUID NOT NULL,
            attempt_id UUID NOT NULL,
            user_id TEXT NOT NULL,
            skill_id TEXT,
            assessment_type TEXT NOT NULL,
            score FLOAT NOT NULL,
            level INTEGER,
            input_hash TEXT,
            model_version TEXT,
            rubric_version TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_assessment_drift_type_ver ON assessment_drift_samples(assessment_type, model_version, rubric_version, created_at DESC);
    """))
    db.commit()


def _table_columns(db: Session, table_name: str) -> List[str]:
    rows = db.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table_name
    """), {"table_name": table_name}).mappings().all()
    return [r["column_name"] for r in rows]


def _payload_hash(payload: Dict[str, Any]) -> str:
    payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", errors="ignore")
    return hashlib.sha256(payload_bytes).hexdigest()


def _load_idempotency_hit(
    db: Session,
    *,
    session_id: str,
    endpoint: str,
    idempotency_key: Optional[str],
    payload_hash: str,
) -> Optional[Dict[str, Any]]:
    if not idempotency_key:
        return None
    row = db.execute(text("""
        SELECT payload_hash, response_json
        FROM assessment_submit_idempotency
        WHERE session_id = :session_id
          AND endpoint = :endpoint
          AND idempotency_key = :idempotency_key
        LIMIT 1
    """), {
        "session_id": session_id,
        "endpoint": endpoint,
        "idempotency_key": idempotency_key,
    }).mappings().first()
    if not row:
        return None
    if row.get("payload_hash") != payload_hash:
        raise HTTPException(status_code=409, detail="Idempotency key already used with different payload")
    cached = row.get("response_json")
    if isinstance(cached, str):
        try:
            cached = json.loads(cached)
        except Exception:
            cached = {"result": cached}
    if isinstance(cached, dict):
        return cached
    return {"result": cached}


def _store_idempotency_hit(
    db: Session,
    *,
    session_id: str,
    endpoint: str,
    idempotency_key: Optional[str],
    payload_hash: str,
    response_payload: Dict[str, Any],
) -> None:
    if not idempotency_key:
        return
    db.execute(text("""
        INSERT INTO assessment_submit_idempotency
        (idem_id, session_id, endpoint, idempotency_key, payload_hash, response_json, created_at)
        VALUES
        (:idem_id, :session_id, :endpoint, :idempotency_key, :payload_hash, :response_json, :created_at)
        ON CONFLICT (session_id, endpoint, idempotency_key) DO NOTHING
    """), {
        "idem_id": str(uuid.uuid4()),
        "session_id": session_id,
        "endpoint": endpoint,
        "idempotency_key": idempotency_key,
        "payload_hash": payload_hash,
        "response_json": json.dumps(response_payload),
        "created_at": _now_utc(),
    })


def _assessment_versions(
    model_version: Optional[str],
    rubric_version: Optional[str],
) -> Dict[str, str]:
    return {
        "model_version": (model_version or DEFAULT_MODEL_VERSION).strip() or DEFAULT_MODEL_VERSION,
        "rubric_version": (rubric_version or DEFAULT_RUBRIC_VERSION).strip() or DEFAULT_RUBRIC_VERSION,
    }


def _enqueue_repair_job(
    db: Session,
    *,
    session_id: str,
    attempt_id: str,
    user_id: str,
    skill_id: str,
    assessment_type: str,
    response_text: str,
    evaluation: Dict[str, Any],
    error_message: str,
) -> Dict[str, Any]:
    repair_job_id = str(uuid.uuid4())
    now = _now_utc()
    db.execute(text("""
        INSERT INTO assessment_repair_jobs
        (repair_job_id, session_id, attempt_id, user_id, skill_id, assessment_type, response_text, evaluation, status, attempts, max_attempts, next_retry_at, last_error, created_at, updated_at)
        VALUES
        (:repair_job_id, :session_id, :attempt_id, :user_id, :skill_id, :assessment_type, :response_text, :evaluation, 'pending', 0, :max_attempts, :next_retry_at, :last_error, :created_at, :updated_at)
    """), {
        "repair_job_id": repair_job_id,
        "session_id": session_id,
        "attempt_id": attempt_id,
        "user_id": user_id,
        "skill_id": skill_id,
        "assessment_type": assessment_type,
        "response_text": response_text,
        "evaluation": json.dumps(evaluation),
        "max_attempts": REPAIR_MAX_ATTEMPTS,
        "next_retry_at": now,
        "last_error": error_message,
        "created_at": now,
        "updated_at": now,
    })
    rq_job_id = enqueue_assessment_repair(session_id=session_id, repair_job_id=repair_job_id, delay_seconds=0)
    db.execute(text("""
        UPDATE assessment_repair_jobs
        SET rq_job_id = :rq_job_id, updated_at = :updated_at
        WHERE repair_job_id = :repair_job_id
    """), {"rq_job_id": rq_job_id, "updated_at": _now_utc(), "repair_job_id": repair_job_id})
    return {
        "updated": False,
        "queued": True,
        "repair_job_id": repair_job_id,
        "rq_job_id": rq_job_id,
        "max_attempts": REPAIR_MAX_ATTEMPTS,
        "reason": "async_repair_enqueued",
    }


def _record_drift_sample(
    db: Session,
    *,
    session_id: str,
    attempt_id: str,
    user_id: str,
    skill_id: str,
    assessment_type: str,
    response_text: str,
    evaluation: Dict[str, Any],
    model_version: str,
    rubric_version: str,
) -> None:
    score = float(evaluation.get("overall_score") or evaluation.get("score") or 0)
    level = evaluation.get("level")
    if isinstance(level, str):
        level = {"novice": 0, "developing": 1, "intermediate": 2, "advanced": 3, "expert": 3}.get(level.lower(), 0)
    if not isinstance(level, (int, float)):
        level = None
    db.execute(text("""
        INSERT INTO assessment_drift_samples
        (sample_id, session_id, attempt_id, user_id, skill_id, assessment_type, score, level, input_hash, model_version, rubric_version, created_at)
        VALUES
        (:sample_id, :session_id, :attempt_id, :user_id, :skill_id, :assessment_type, :score, :level, :input_hash, :model_version, :rubric_version, :created_at)
    """), {
        "sample_id": str(uuid.uuid4()),
        "session_id": session_id,
        "attempt_id": attempt_id,
        "user_id": user_id,
        "skill_id": skill_id,
        "assessment_type": assessment_type,
        "score": score,
        "level": int(level) if isinstance(level, (int, float)) else None,
        "input_hash": hashlib.sha256((response_text or "").encode("utf-8", errors="ignore")).hexdigest(),
        "model_version": model_version,
        "rubric_version": rubric_version,
        "created_at": _now_utc(),
    })


def _ensure_skill_tables(db: Session):
    """Create skill outcome tables when local test DB is empty."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS skill_assessments (
            assessment_id UUID PRIMARY KEY,
            doc_id UUID NOT NULL,
            skill_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
            decision_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS skill_proficiency (
            prof_id UUID PRIMARY KEY,
            doc_id UUID NOT NULL,
            skill_id TEXT NOT NULL,
            level INTEGER NOT NULL,
            label TEXT NOT NULL,
            rationale TEXT NOT NULL,
            best_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            signals JSONB NOT NULL DEFAULT '{}'::jsonb,
            meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """))
    db.commit()


def _resolve_or_create_assessment_doc_id(db: Session, user_id: str, assessment_type: str) -> str:
    """
    Resolve a user-owned consented doc_id for linkage.
    If none exists, create a synthetic assessment document and consent.
    """
    # Try latest consented document first.
    try:
        row = db.execute(text("""
            SELECT c.doc_id
            FROM consents c
            WHERE c.user_id = :user_id AND c.status = 'granted'
            ORDER BY c.created_at DESC
            LIMIT 1
        """), {"user_id": user_id}).mappings().first()
        if row and row.get("doc_id"):
            return str(row["doc_id"])
    except Exception as exc:
        _log.warning("consent doc lookup rollback: %s", exc)
        db.rollback()

    doc_id = str(uuid.uuid4())
    now = _now_utc()
    filename = f"interactive_{assessment_type}_{now.strftime('%Y%m%d_%H%M%S')}.txt"
    stored_path = f"upload://{doc_id}/{filename}"

    doc_cols = set(_table_columns(db, "documents"))
    if doc_cols:
        doc_payload: Dict[str, Any] = {}
        if "doc_id" in doc_cols:
            doc_payload["doc_id"] = doc_id
        if "filename" in doc_cols:
            doc_payload["filename"] = filename
        if "stored_path" in doc_cols:
            doc_payload["stored_path"] = stored_path
        if "doc_type" in doc_cols:
            doc_payload["doc_type"] = "assessment"
        if "created_at" in doc_cols:
            doc_payload["created_at"] = now
        if "title" in doc_cols:
            doc_payload["title"] = f"Interactive {assessment_type} assessment"
        if "source_type" in doc_cols:
            doc_payload["source_type"] = "interactive_assessment"
        if "storage_uri" in doc_cols:
            doc_payload["storage_uri"] = stored_path
        if "metadata_json" in doc_cols:
            doc_payload["metadata_json"] = json.dumps({"source": "interactive_assessment", "user_id": user_id})

        keys = list(doc_payload.keys())
        db.execute(
            text(f"INSERT INTO documents ({', '.join(keys)}) VALUES ({', '.join(f':{k}' for k in keys)})"),
            doc_payload,
        )

    consent_cols = set(_table_columns(db, "consents"))
    if consent_cols:
        consent_payload: Dict[str, Any] = {}
        if "consent_id" in consent_cols:
            consent_payload["consent_id"] = str(uuid.uuid4())
        if "doc_id" in consent_cols:
            consent_payload["doc_id"] = doc_id
        if "status" in consent_cols:
            consent_payload["status"] = "granted"
        if "created_at" in consent_cols:
            consent_payload["created_at"] = now
        if "user_id" in consent_cols:
            consent_payload["user_id"] = user_id
        if "subject_id" in consent_cols:
            consent_payload["subject_id"] = user_id
        if "scope" in consent_cols:
            consent_payload["scope"] = "skill_assessment:full"

        if consent_payload:
            keys = list(consent_payload.keys())
            db.execute(
                text(f"INSERT INTO consents ({', '.join(keys)}) VALUES ({', '.join(f':{k}' for k in keys)})"),
                consent_payload,
            )

    db.commit()
    return doc_id


def _persist_skill_outcome(
    db: Session,
    *,
    user_id: str,
    skill_id: str,
    assessment_type: str,
    response_text: str,
    evaluation: Dict[str, Any],
    session_id: Optional[str] = None,
    attempt_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persist interactive result to skill_assessments + skill_proficiency.
    This keeps student profile and role readiness in sync with assessment outcomes.
    """
    _ensure_skill_tables(db)
    doc_id = _resolve_or_create_assessment_doc_id(db, user_id, assessment_type)
    now = _now_utc()

    score = float(evaluation.get("overall_score") or evaluation.get("score") or 0)
    raw_level = evaluation.get("level")
    level_map = {"novice": 0, "developing": 1, "intermediate": 2, "advanced": 3, "expert": 3}
    if isinstance(raw_level, str):
        level = level_map.get(raw_level.lower(), 0)
    elif isinstance(raw_level, (int, float)):
        level = max(0, min(3, int(raw_level)))
    else:
        # Fallback from score bands.
        level = 3 if score >= 85 else 2 if score >= 70 else 1 if score >= 50 else 0

    # IRT upgrade: estimate ability theta from recent attempts with type-based difficulty.
    diff_map = {"communication": -0.2, "writing": 0.1, "programming": 0.8, "data_analysis": 0.6, "problem_solving": 0.7}
    recent_rows = db.execute(
        text(
            """
            SELECT score
            FROM assessment_attempts
            WHERE session_id = :session_id
            ORDER BY submitted_at DESC
            LIMIT 5
            """
        ),
        {"session_id": session_id},
    ).mappings().all() if session_id else []
    irt_items = [IRTItemResult(score=min(1.0, max(0.0, float((r.get("score") or 0) / 100.0))), difficulty=diff_map.get(assessment_type, 0.3)) for r in recent_rows]
    irt_items.append(IRTItemResult(score=min(1.0, max(0.0, score / 100.0)), difficulty=diff_map.get(assessment_type, 0.3)))
    theta = estimate_theta(irt_items)
    level = max(level, theta_to_level(theta))

    decision = "demonstrated" if score >= 75 or level >= 2 else "mentioned" if score >= 55 else "not_enough_information"
    proficiency_label = "strong_match" if level >= 3 else "match" if level == 2 else "weak_match" if level == 1 else "no_match"
    rationale = evaluation.get("feedback") or f"Interactive {assessment_type} assessment score={score:.1f}, level={level}."

    # Create evidence chunk from response text so student profile can show pointers.
    chunk_id = str(uuid.uuid4())
    text_body = (response_text or "").strip()
    snippet = text_body[:300] if text_body else f"{assessment_type} assessment submission"
    quote_hash = hashlib.sha256((text_body or snippet).encode("utf-8", errors="ignore")).hexdigest()
    chunk_cols = set(_table_columns(db, "chunks"))
    if chunk_cols:
        chunk_payload: Dict[str, Any] = {}
        if "chunk_id" in chunk_cols:
            chunk_payload["chunk_id"] = chunk_id
        if "doc_id" in chunk_cols:
            chunk_payload["doc_id"] = doc_id
        if "idx" in chunk_cols:
            max_idx = db.execute(
                text("SELECT COALESCE(MAX(idx), -1) AS m FROM chunks WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            ).mappings().first()
            chunk_payload["idx"] = int((max_idx or {}).get("m", -1)) + 1
        if "char_start" in chunk_cols:
            chunk_payload["char_start"] = 0
        if "char_end" in chunk_cols:
            chunk_payload["char_end"] = len(text_body or snippet)
        if "snippet" in chunk_cols:
            chunk_payload["snippet"] = snippet
        if "quote_hash" in chunk_cols:
            chunk_payload["quote_hash"] = quote_hash
        if "created_at" in chunk_cols:
            chunk_payload["created_at"] = now
        if "chunk_text" in chunk_cols:
            chunk_payload["chunk_text"] = text_body or snippet
        if "section_path" in chunk_cols:
            chunk_payload["section_path"] = f"interactive/{assessment_type}"
        if "page_start" in chunk_cols:
            chunk_payload["page_start"] = 1
        if "page_end" in chunk_cols:
            chunk_payload["page_end"] = 1

        keys = list(chunk_payload.keys())
        db.execute(
            text(f"INSERT INTO chunks ({', '.join(keys)}) VALUES ({', '.join(f':{k}' for k in keys)})"),
            chunk_payload,
        )

    evidence = [{"chunk_id": chunk_id, "snippet": snippet}] if chunk_cols else []

    assessment_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO skill_assessments
        (assessment_id, doc_id, skill_id, decision, evidence, decision_meta, created_at)
        VALUES (:assessment_id, :doc_id, :skill_id, :decision, :evidence, :decision_meta, :created_at)
    """), {
        "assessment_id": assessment_id,
        "doc_id": doc_id,
        "skill_id": skill_id,
        "decision": decision,
        "evidence": json.dumps(evidence),
        "decision_meta": json.dumps({
            "source": "interactive_assessment",
            "assessment_type": assessment_type,
            "score": score,
            "level": level,
            "irt_theta": theta,
            "user_id": user_id,
            "session_id": session_id,
            "attempt_id": attempt_id,
        }),
        "created_at": now,
    })

    prof_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO skill_proficiency
        (prof_id, doc_id, skill_id, level, label, rationale, best_evidence, signals, meta, created_at)
        VALUES
        (:prof_id, :doc_id, :skill_id, :level, :label, :rationale, :best_evidence, :signals, :meta, :created_at)
    """), {
        "prof_id": prof_id,
        "doc_id": doc_id,
        "skill_id": skill_id,
        "level": level,
        "label": proficiency_label,
        "rationale": rationale,
        "best_evidence": json.dumps(evidence[0] if evidence else {}),
        "signals": json.dumps({"score": score, "assessment_type": assessment_type, "irt_theta": theta}),
        "meta": json.dumps({"source": "interactive_assessment", "decision": decision, "irt_theta": theta}),
        "created_at": now,
    })
    return {
        "updated": True,
        "doc_id": doc_id,
        "skill_id": skill_id,
        "decision": decision,
        "level": level,
        "score": score,
        "irt_theta": theta,
        "assessment_id": assessment_id,
        "prof_id": prof_id,
    }


class AgentSyncRequest(BaseModel):
    user_id: str
    skill_id: str
    session_id: Optional[str] = None
    attempt_id: Optional[str] = None
    assessment_type: str = "agent_dialogue"
    response_text: str = ""
    evaluation: Dict[str, Any]


@router.post("/agent/sync-result")
def sync_agent_result(
    req: AgentSyncRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Sync worker-agent result into skill_assessments/skill_proficiency."""
    return _persist_skill_outcome(
        db,
        user_id=req.user_id,
        skill_id=req.skill_id,
        assessment_type=req.assessment_type,
        response_text=req.response_text,
        evaluation=req.evaluation,
        session_id=req.session_id,
        attempt_id=req.attempt_id,
    )


# ====================
# Communication Assessment (Kira-style)
# ====================
COMMUNICATION_TOPICS = [
    "Describe a challenging project you worked on and how you overcame obstacles.",
    "Explain a complex technical concept to someone without a technical background.",
    "Tell us about a time when you had to work with a difficult team member.",
    "What is the most innovative idea you've had, and how did you try to implement it?",
    "Describe your approach to learning a new skill or technology.",
    "How would you handle a situation where you disagree with your manager's decision?",
    "Tell us about a time you failed and what you learned from it.",
    "Explain why you are passionate about your field of study.",
    "How do you prioritize tasks when everything seems urgent?",
    "Describe a situation where you had to adapt quickly to change.",
    "What makes effective communication in a professional setting?",
    "Tell us about a time you led a team or initiative.",
    "How do you approach problem-solving when you don't know the answer?",
    "Describe your experience working in diverse teams.",
    "What do you consider your greatest professional achievement?",
]


class CommunicationSessionRequest(BaseModel):
    """Request to start a communication assessment session."""
    user_id: str
    skill_id: str = "HKU.SKILL.COMMUNICATION.v1"
    duration_seconds: int = Field(default=60, ge=30, le=180)
    topic_count: int = Field(default=1, ge=1, le=5)
    allow_retries: bool = True
    max_retries: int = Field(default=3, ge=1, le=5)


class CommunicationSessionResponse(BaseModel):
    session_id: str
    topic: str
    duration_seconds: int
    preparation_seconds: int
    attempt_number: int
    max_attempts: int
    instructions: str


@router.post("/communication/start", response_model=CommunicationSessionResponse)
def start_communication_session(
    req: CommunicationSessionRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Start a Kira-style communication assessment session.
    
    Flow:
    1. Generate random topic
    2. Give student preparation time (30 seconds)
    3. Student speaks for specified duration (30/60/90 seconds)
    4. Submit recording for evaluation
    5. Allow retries if enabled
    """
    ensure_assessment_tables(db)
    
    session_id = str(uuid.uuid4())
    topic = random.choice(COMMUNICATION_TOPICS)
    
    config = {
        "duration_seconds": req.duration_seconds,
        "preparation_seconds": 30,
        "max_attempts": req.max_retries + 1 if req.allow_retries else 1,
        "topic": topic,
    }
    
    db.execute(text("""
        INSERT INTO assessment_sessions (session_id, user_id, assessment_type, skill_id, status, config, created_at)
        VALUES (:session_id, :user_id, 'communication', :skill_id, 'pending', :config, :now)
    """), {
        "session_id": session_id,
        "user_id": req.user_id,
        "skill_id": req.skill_id,
        "config": json.dumps(config),
        "now": _now_utc(),
    })
    db.commit()
    
    return {
        "session_id": session_id,
        "topic": topic,
        "duration_seconds": req.duration_seconds,
        "preparation_seconds": 30,
        "attempt_number": 1,
        "max_attempts": config["max_attempts"],
        "instructions": f"""
Communication Assessment Instructions:

1. PREPARATION (30 seconds):
   - Read the topic carefully
   - Organize your thoughts
   - Think about structure: introduction, main points, conclusion

2. RECORDING ({req.duration_seconds} seconds):
   - Speak clearly and confidently
   - Address the topic directly
   - Use specific examples when possible

3. EVALUATION CRITERIA:
   - Clarity and articulation
   - Content relevance and depth
   - Structure and organization
   - Professional communication style
   - Confidence and engagement

Topic: {topic}
        """.strip(),
    }


class CommunicationSubmitRequest(BaseModel):
    session_id: str
    transcript: str = Field(..., description="Speech transcript (from Whisper or manual)")
    audio_duration_seconds: float = Field(..., description="Actual recording duration")
    audio_file_id: Optional[str] = Field(default=None, description="Reference to stored audio file")


@router.post("/communication/submit")
def submit_communication_response(
    req: CommunicationSubmitRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    model_version: Optional[str] = Header(default=None, alias="X-Model-Version"),
    rubric_version: Optional[str] = Header(default=None, alias="X-Rubric-Version"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Submit a communication assessment response for evaluation.
    """
    payload_hash = _payload_hash(req.model_dump(mode="json"))
    cached = _load_idempotency_hit(
        db,
        session_id=req.session_id,
        endpoint="communication_submit",
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
    )
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    versions = _assessment_versions(model_version, rubric_version)

    # Get session
    session = db.execute(text("""
        SELECT * FROM assessment_sessions WHERE session_id = :session_id
    """), {"session_id": req.session_id}).mappings().first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    config = json.loads(session["config"]) if isinstance(session["config"], str) else session["config"]
    
    # Count existing attempts
    attempts = db.execute(text("""
        SELECT COUNT(*) as count FROM assessment_attempts WHERE session_id = :session_id
    """), {"session_id": req.session_id}).first()
    attempt_number = (attempts[0] or 0) + 1
    
    if attempt_number > config.get("max_attempts", 1):
        raise HTTPException(status_code=400, detail="Maximum attempts exceeded")
    
    # Evaluate the response
    evaluation = _evaluate_communication(
        transcript=req.transcript,
        topic=config.get("topic", ""),
        duration=req.audio_duration_seconds,
        expected_duration=config.get("duration_seconds", 60),
    )
    
    # Store attempt
    attempt_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO assessment_attempts 
        (attempt_id, session_id, attempt_number, prompt_data, response_data, evaluation, score, submitted_at, created_at)
        VALUES (:attempt_id, :session_id, :attempt_number, :prompt_data, :response_data, :evaluation, :score, :now, :now)
    """), {
        "attempt_id": attempt_id,
        "session_id": req.session_id,
        "attempt_number": attempt_number,
        "prompt_data": json.dumps({"topic": config.get("topic")}),
        "response_data": json.dumps({
            "transcript": req.transcript,
            "duration": req.audio_duration_seconds,
            "audio_file_id": req.audio_file_id,
        }),
        "evaluation": json.dumps(evaluation),
        "score": evaluation.get("overall_score", 0),
        "now": _now_utc(),
    })
    
    # Update session status if max attempts reached
    if attempt_number >= config.get("max_attempts", 1):
        db.execute(text("""
            UPDATE assessment_sessions SET status = 'completed', completed_at = :now
            WHERE session_id = :session_id
        """), {"session_id": req.session_id, "now": _now_utc()})

    # Sync interactive assessment result into student skill profile tables.
    skill_update = None
    if attempt_number >= config.get("max_attempts", 1):
        try:
            skill_update = _persist_skill_outcome(
                db,
                user_id=str(session["user_id"]),
                skill_id=str(session["skill_id"] or "HKU.SKILL.COMMUNICATION.v1"),
                assessment_type="communication",
                response_text=req.transcript,
                evaluation=evaluation,
                session_id=str(req.session_id),
                attempt_id=attempt_id,
            )
        except Exception as e:
            skill_update = _enqueue_repair_job(
                db,
                session_id=str(req.session_id),
                attempt_id=attempt_id,
                user_id=str(session["user_id"]),
                skill_id=str(session["skill_id"] or "HKU.SKILL.COMMUNICATION.v1"),
                assessment_type="communication",
                response_text=req.transcript,
                evaluation=evaluation,
                error_message=f"{type(e).__name__}: {e}",
            )

    _record_drift_sample(
        db,
        session_id=str(req.session_id),
        attempt_id=attempt_id,
        user_id=str(session["user_id"]),
        skill_id=str(session["skill_id"] or "HKU.SKILL.COMMUNICATION.v1"),
        assessment_type="communication",
        response_text=req.transcript,
        evaluation=evaluation,
        model_version=versions["model_version"],
        rubric_version=versions["rubric_version"],
    )

    can_retry = attempt_number < config.get("max_attempts", 1)
    response_payload = {
        "attempt_id": attempt_id,
        "attempt_number": attempt_number,
        "evaluation": evaluation,
        "skill_update": skill_update,
        "model_version": versions["model_version"],
        "rubric_version": versions["rubric_version"],
        "idempotent_replay": False,
        "can_retry": can_retry,
        "remaining_attempts": config.get("max_attempts", 1) - attempt_number if can_retry else 0,
    }
    _store_idempotency_hit(
        db,
        session_id=str(req.session_id),
        endpoint="communication_submit",
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        response_payload=response_payload,
    )
    db.commit()
    return response_payload


def _evaluate_communication_heuristic(
    transcript: str,
    topic: str,
    duration: float,
    expected_duration: float,
) -> Dict[str, Any]:
    """Heuristic-only evaluation (fallback when LLM unavailable or fails)."""
    word_count = len(transcript.split())
    words_per_minute = (word_count / duration) * 60 if duration > 0 else 0
    duration_ratio = duration / expected_duration
    if 0.8 <= duration_ratio <= 1.1:
        duration_score = 100
    elif 0.5 <= duration_ratio < 0.8:
        duration_score = 70
    elif duration_ratio > 1.1:
        duration_score = 80
    else:
        duration_score = 50
    if word_count >= 100:
        content_score = 90
    elif word_count >= 50:
        content_score = 70
    else:
        content_score = 50
    if 120 <= words_per_minute <= 150:
        pace_score = 100
    elif 100 <= words_per_minute < 120 or 150 < words_per_minute <= 180:
        pace_score = 80
    else:
        pace_score = 60
    overall_score = (duration_score * 0.2 + content_score * 0.5 + pace_score * 0.3)
    if overall_score >= 85:
        level, label = 3, "Advanced"
    elif overall_score >= 70:
        level, label = 2, "Intermediate"
    elif overall_score >= 50:
        level, label = 1, "Developing"
    else:
        level, label = 0, "Novice"
    return {
        "overall_score": round(overall_score, 1),
        "level": level,
        "level_label": label,
        "metrics": {
            "word_count": word_count,
            "words_per_minute": round(words_per_minute, 1),
            "duration_seconds": round(duration, 1),
            "duration_score": duration_score,
            "content_score": content_score,
            "pace_score": pace_score,
        },
        "feedback": _generate_communication_feedback(overall_score, word_count, words_per_minute),
    }


def _evaluate_communication(
    transcript: str,
    topic: str,
    duration: float,
    expected_duration: float,
) -> Dict[str, Any]:
    """Evaluate communication response. Tries LLM first, falls back to heuristic."""
    word_count = len(transcript.split())
    llm_out = _llm_evaluate(
        "eval_communication_v1.txt",
        topic=topic or "",
        expected_duration=int(expected_duration),
        duration=round(duration, 1),
        word_count=word_count,
        transcript=(transcript or "")[:MAX_INPUT_CHARS],
    )
    if llm_out and isinstance(llm_out.get("overall_score"), (int, float)) and 0 <= llm_out.get("level", -1) <= 3:
        feedback = llm_out.get("feedback")
        if isinstance(feedback, list):
            feedback = " ".join(str(x) for x in feedback)
        if not isinstance(feedback, str):
            feedback = str(feedback) if feedback else ""
        metrics = llm_out.get("metrics") or {}
        if "words_per_minute" not in metrics and duration > 0:
            metrics["words_per_minute"] = round((word_count / duration) * 60, 1)
        if "duration_seconds" not in metrics:
            metrics["duration_seconds"] = round(duration, 1)
        return {
            "overall_score": round(float(llm_out["overall_score"]), 1),
            "level": int(llm_out.get("level", 0)),
            "level_label": str(llm_out.get("level_label") or "Developing"),
            "metrics": {**{"word_count": word_count}, **metrics},
            "feedback": feedback or "Assessment complete.",
        }
    return _evaluate_communication_heuristic(transcript, topic, duration, expected_duration)


def _generate_communication_feedback(score: float, word_count: int, wpm: float) -> str:
    """Generate personalized feedback for communication assessment."""
    feedback_parts = []
    
    if score >= 85:
        feedback_parts.append("Excellent communication! Your response was well-structured and engaging.")
    elif score >= 70:
        feedback_parts.append("Good communication skills demonstrated. There's room for improvement in some areas.")
    else:
        feedback_parts.append("Your response shows developing communication skills. Consider practicing more structured responses.")
    
    if wpm < 100:
        feedback_parts.append("Try to speak a bit faster to convey more information.")
    elif wpm > 180:
        feedback_parts.append("Consider slowing down slightly for clarity.")
    
    if word_count < 50:
        feedback_parts.append("Try to provide more detail and examples in your response.")
    
    return " ".join(feedback_parts)


# ====================
# Programming Assessment (LeetCode-style)
# ====================
PROGRAMMING_PROBLEMS = {
    "easy": [
        {
            "id": "two_sum",
            "title": "Two Sum",
            "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
            "examples": [
                {"input": "nums = [2,7,11,15], target = 9", "output": "[0,1]", "explanation": "Because nums[0] + nums[1] == 9, we return [0, 1]."},
            ],
            "constraints": ["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9"],
            "function_signature": "def two_sum(nums: List[int], target: int) -> List[int]:",
            "test_cases": [
                {"input": {"nums": [2, 7, 11, 15], "target": 9}, "expected": [0, 1]},
                {"input": {"nums": [3, 2, 4], "target": 6}, "expected": [1, 2]},
            ],
            "time_limit_seconds": 900,  # 15 minutes
        },
        {
            "id": "palindrome_number",
            "title": "Palindrome Number",
            "description": "Given an integer x, return true if x is a palindrome, and false otherwise.",
            "examples": [
                {"input": "x = 121", "output": "true", "explanation": "121 reads as 121 from left to right and from right to left."},
            ],
            "constraints": ["-2^31 <= x <= 2^31 - 1"],
            "function_signature": "def is_palindrome(x: int) -> bool:",
            "test_cases": [
                {"input": {"x": 121}, "expected": True},
                {"input": {"x": -121}, "expected": False},
                {"input": {"x": 10}, "expected": False},
            ],
            "time_limit_seconds": 600,  # 10 minutes
        },
    ],
    "medium": [
        {
            "id": "longest_substring",
            "title": "Longest Substring Without Repeating Characters",
            "description": "Given a string s, find the length of the longest substring without repeating characters.",
            "examples": [
                {"input": 's = "abcabcbb"', "output": "3", "explanation": "The answer is 'abc', with the length of 3."},
            ],
            "constraints": ["0 <= s.length <= 5 * 10^4"],
            "function_signature": "def length_of_longest_substring(s: str) -> int:",
            "test_cases": [
                {"input": {"s": "abcabcbb"}, "expected": 3},
                {"input": {"s": "bbbbb"}, "expected": 1},
                {"input": {"s": "pwwkew"}, "expected": 3},
            ],
            "time_limit_seconds": 1200,  # 20 minutes
        },
    ],
    "hard": [
        {
            "id": "merge_k_lists",
            "title": "Merge k Sorted Lists",
            "description": "You are given an array of k linked-lists lists, each linked-list is sorted in ascending order. Merge all the linked-lists into one sorted linked-list and return it.",
            "examples": [
                {"input": "lists = [[1,4,5],[1,3,4],[2,6]]", "output": "[1,1,2,3,4,4,5,6]"},
            ],
            "constraints": ["k == lists.length", "0 <= k <= 10^4"],
            "function_signature": "def merge_k_lists(lists: List[List[int]]) -> List[int]:",
            "test_cases": [
                {"input": {"lists": [[1, 4, 5], [1, 3, 4], [2, 6]]}, "expected": [1, 1, 2, 3, 4, 4, 5, 6]},
                {"input": {"lists": []}, "expected": []},
            ],
            "time_limit_seconds": 1800,  # 30 minutes
        },
    ],
}


class ProgrammingSessionRequest(BaseModel):
    user_id: str
    skill_id: str = "HKU.SKILL.CODING.v1"
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    language: str = Field(default="python", pattern="^(python|javascript|java|cpp)$")


@router.post("/programming/start")
def start_programming_session(
    req: ProgrammingSessionRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Start a programming assessment session.
    """
    ensure_assessment_tables(db)
    
    # Select random problem
    problems = PROGRAMMING_PROBLEMS.get(req.difficulty, PROGRAMMING_PROBLEMS["medium"])
    problem = random.choice(problems)
    
    session_id = str(uuid.uuid4())
    config = {
        "problem_id": problem["id"],
        "difficulty": req.difficulty,
        "language": req.language,
        "time_limit_seconds": problem["time_limit_seconds"],
    }
    
    db.execute(text("""
        INSERT INTO assessment_sessions (session_id, user_id, assessment_type, skill_id, status, config, started_at, created_at)
        VALUES (:session_id, :user_id, 'programming', :skill_id, 'in_progress', :config, :now, :now)
    """), {
        "session_id": session_id,
        "user_id": req.user_id,
        "skill_id": req.skill_id,
        "config": json.dumps(config),
        "now": _now_utc(),
    })
    db.commit()
    
    # Return problem without test case expected values
    problem_display = {
        "id": problem["id"],
        "title": problem["title"],
        "description": problem["description"],
        "examples": problem["examples"],
        "constraints": problem["constraints"],
        "function_signature": problem["function_signature"],
    }
    
    return {
        "session_id": session_id,
        "problem": problem_display,
        "time_limit_seconds": problem["time_limit_seconds"],
        "language": req.language,
        "started_at": _now_utc().isoformat(),
        "deadline": (_now_utc() + timedelta(seconds=problem["time_limit_seconds"])).isoformat(),
    }


class ProgrammingSubmitRequest(BaseModel):
    session_id: str
    code: str
    language: str = "python"


@router.post("/programming/submit")
def submit_programming_solution(
    req: ProgrammingSubmitRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    model_version: Optional[str] = Header(default=None, alias="X-Model-Version"),
    rubric_version: Optional[str] = Header(default=None, alias="X-Rubric-Version"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Submit and evaluate a programming solution.
    """
    payload_hash = _payload_hash(req.model_dump(mode="json"))
    cached = _load_idempotency_hit(
        db,
        session_id=req.session_id,
        endpoint="programming_submit",
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
    )
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    versions = _assessment_versions(model_version, rubric_version)

    # Get session
    session = db.execute(text("""
        SELECT * FROM assessment_sessions WHERE session_id = :session_id
    """), {"session_id": req.session_id}).mappings().first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")
    
    config = json.loads(session["config"]) if isinstance(session["config"], str) else session["config"]
    
    # Check time limit
    started_at = session["started_at"]
    if started_at:
        elapsed = (_now_utc() - started_at).total_seconds()
        if elapsed > config.get("time_limit_seconds", 1800) + 60:  # 1 minute grace
            raise HTTPException(status_code=400, detail="Time limit exceeded")
    
    # Get problem and run tests
    problem_id = config.get("problem_id")
    problem = None
    for diff_problems in PROGRAMMING_PROBLEMS.values():
        for p in diff_problems:
            if p["id"] == problem_id:
                problem = p
                break
    
    if not problem:
        raise HTTPException(status_code=500, detail="Problem not found")
    
    # Evaluate code
    evaluation = _evaluate_code(req.code, problem, req.language)
    
    # Store attempt
    attempt_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO assessment_attempts 
        (attempt_id, session_id, attempt_number, prompt_data, response_data, evaluation, score, submitted_at, created_at)
        VALUES (:attempt_id, :session_id, 1, :prompt_data, :response_data, :evaluation, :score, :now, :now)
    """), {
        "attempt_id": attempt_id,
        "session_id": req.session_id,
        "prompt_data": json.dumps({"problem_id": problem_id}),
        "response_data": json.dumps({"code": req.code, "language": req.language}),
        "evaluation": json.dumps(evaluation),
        "score": evaluation.get("score", 0),
        "now": _now_utc(),
    })
    
    # Update session
    db.execute(text("""
        UPDATE assessment_sessions SET status = 'completed', completed_at = :now
        WHERE session_id = :session_id
    """), {"session_id": req.session_id, "now": _now_utc()})

    try:
        skill_update = _persist_skill_outcome(
            db,
            user_id=str(session["user_id"]),
            skill_id=str(session["skill_id"] or "HKU.SKILL.CODING.v1"),
            assessment_type="programming",
            response_text=req.code,
            evaluation=evaluation,
            session_id=str(req.session_id),
            attempt_id=attempt_id,
        )
    except Exception as e:
        skill_update = _enqueue_repair_job(
            db,
            session_id=str(req.session_id),
            attempt_id=attempt_id,
            user_id=str(session["user_id"]),
            skill_id=str(session["skill_id"] or "HKU.SKILL.CODING.v1"),
            assessment_type="programming",
            response_text=req.code,
            evaluation=evaluation,
            error_message=f"{type(e).__name__}: {e}",
        )

    _record_drift_sample(
        db,
        session_id=str(req.session_id),
        attempt_id=attempt_id,
        user_id=str(session["user_id"]),
        skill_id=str(session["skill_id"] or "HKU.SKILL.CODING.v1"),
        assessment_type="programming",
        response_text=req.code,
        evaluation=evaluation,
        model_version=versions["model_version"],
        rubric_version=versions["rubric_version"],
    )

    response_payload = {
        "attempt_id": attempt_id,
        "evaluation": evaluation,
        "skill_update": skill_update,
        "model_version": versions["model_version"],
        "rubric_version": versions["rubric_version"],
        "idempotent_replay": False,
    }
    _store_idempotency_hit(
        db,
        session_id=str(req.session_id),
        endpoint="programming_submit",
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        response_payload=response_payload,
    )
    db.commit()
    return response_payload


def _safe_exec_python(code: str, test_input: str, timeout_s: int = 5) -> Dict[str, Any]:
    """Run Python code in a restricted subprocess with timeout."""
    import subprocess, json as _json
    wrapper = (
        "import sys, json\n"
        "sys.stdin = __import__('io').StringIO(json.loads(sys.argv[1]))\n"
        f"{code}\n"
    )
    func_match = re.search(r"def\s+(\w+)\s*\(", code)
    if func_match:
        fname = func_match.group(1)
        wrapper += f"\nprint(json.dumps({fname}(*json.loads(sys.argv[1]))))"
    try:
        proc = subprocess.run(
            ["python3", "-c", wrapper, _json.dumps(test_input)],
            capture_output=True, text=True, timeout=timeout_s,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr.strip()[:500]}
        return {"ok": True, "output": proc.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Time limit exceeded"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def _evaluate_code(code: str, problem: Dict, language: str) -> Dict[str, Any]:
    """
    Evaluate submitted code. Runs tests first, then tries LLM for score/feedback; falls back to heuristic.
    """
    test_cases = problem.get("test_cases", [])
    passed = 0
    results = []
    can_execute = language.lower() in ("python", "python3", "py")

    for i, tc in enumerate(test_cases):
        tc_input = tc.get("input", "")
        tc_expected = str(tc.get("expected", ""))

        if can_execute:
            run = _safe_exec_python(code, tc_input)
            if run["ok"]:
                actual = run["output"]
                is_pass = actual.strip() == tc_expected.strip()
                results.append({
                    "test_case": i + 1,
                    "input": str(tc_input),
                    "expected": tc_expected,
                    "actual": actual,
                    "status": "passed" if is_pass else "failed",
                    "message": "" if is_pass else f"Expected {tc_expected}, got {actual}",
                })
                if is_pass:
                    passed += 1
            else:
                results.append({
                    "test_case": i + 1,
                    "input": str(tc_input),
                    "expected": tc_expected,
                    "actual": "",
                    "status": "error",
                    "message": run["error"],
                })
        else:
            results.append({
                "test_case": i + 1,
                "input": str(tc_input),
                "expected": tc_expected,
                "status": "skipped",
                "message": f"Execution not supported for {language}; scored by static analysis",
            })

    score = 0
    feedback = []

    if can_execute and test_cases:
        ratio = passed / len(test_cases)
        score = int(ratio * 70) + 10
        feedback.append(f"✓ {passed}/{len(test_cases)} test cases passed")
    else:
        if problem.get("function_signature", "").split("(")[0] in code:
            score += 20
            feedback.append("✓ Correct function name used")
        else:
            feedback.append("✗ Function signature doesn't match expected")
        if "return" in code:
            score += 10
            feedback.append("✓ Return statement present")
        if len(code.split("\n")) >= 3:
            score += 10
            feedback.append("✓ Solution has multiple lines")

    loc = len([l for l in code.split("\n") if l.strip() and not l.strip().startswith("#")])
    if loc >= 5:
        score = max(score, score + 5)
        feedback.append(f"✓ {loc} lines of logic")

    if score >= 65:
        level, label = 3, "Advanced"
    elif score >= 45:
        level, label = 2, "Intermediate"
    elif score >= 25:
        level, label = 1, "Developing"
    else:
        level, label = 0, "Novice"

    heuristic_result = {
        "score": min(score, 100),
        "level": level,
        "level_label": label,
        "test_results": results,
        "tests_passed": passed,
        "tests_total": len(test_cases),
        "feedback": feedback,
    }

    llm_out = _llm_evaluate(
        "eval_programming_v1.txt",
        problem_title=problem.get("title") or "Coding",
        problem_description=(problem.get("description") or "")[:800],
        tests_passed=passed,
        tests_total=len(test_cases),
        code=(code or "")[:MAX_INPUT_CHARS],
    )
    if llm_out and isinstance(llm_out.get("score"), (int, float)) and 0 <= llm_out.get("level", -1) <= 3:
        fb = llm_out.get("feedback")
        if isinstance(fb, list):
            feedback = [str(x) for x in fb]
        else:
            feedback = [str(fb)] if fb else feedback
        return {
            "score": min(100, round(float(llm_out["score"]), 1)),
            "level": int(llm_out.get("level", level)),
            "level_label": str(llm_out.get("level_label") or label),
            "test_results": results,
            "tests_passed": passed,
            "tests_total": len(test_cases),
            "feedback": feedback,
        }
    return heuristic_result


# ====================
# Writing Assessment
# ====================
WRITING_PROMPTS = [
    {
        "id": "tech_impact",
        "title": "Technology's Impact on Society",
        "prompt": "Discuss how a specific technology has changed the way people live, work, or communicate. Use concrete examples to support your argument.",
        "word_range": [300, 500],
        "time_limit_minutes": 30,
    },
    {
        "id": "problem_solution",
        "title": "Problem and Solution",
        "prompt": "Identify a problem in your community or field of study and propose a practical solution. Explain why this solution would be effective.",
        "word_range": [300, 500],
        "time_limit_minutes": 30,
    },
    {
        "id": "opinion_essay",
        "title": "Opinion Essay",
        "prompt": "Some people believe that artificial intelligence will create more jobs than it eliminates. Others disagree. What is your opinion? Support your view with reasons and examples.",
        "word_range": [300, 500],
        "time_limit_minutes": 30,
    },
]


class WritingSessionRequest(BaseModel):
    user_id: str
    skill_id: str = "HKU.SKILL.TECHNICAL_WRITING.v1"
    time_limit_minutes: int = Field(default=30, ge=15, le=60)
    min_words: int = Field(default=300, ge=100, le=500)
    max_words: int = Field(default=500, ge=200, le=1000)


class WritingSessionResponse(BaseModel):
    session_id: str
    prompt: Dict[str, Any]
    time_limit_minutes: int
    word_range: List[int]
    started_at: str
    deadline: str
    instructions: str
    anti_copy_token: str


@router.post("/writing/start", response_model=WritingSessionResponse)
def start_writing_session(
    req: WritingSessionRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Start a timed writing assessment session.
    
    Features:
    - Random prompt generation
    - Strict time limit
    - Anti-copy-paste protection (via keystroke tracking token)
    - Word count requirements
    """
    ensure_assessment_tables(db)
    
    session_id = str(uuid.uuid4())
    prompt = random.choice(WRITING_PROMPTS)
    anti_copy_token = _generate_session_token()
    
    config = {
        "prompt_id": prompt["id"],
        "time_limit_minutes": req.time_limit_minutes,
        "min_words": req.min_words,
        "max_words": req.max_words,
        "anti_copy_token": anti_copy_token,
    }
    
    started_at = _now_utc()
    deadline = started_at + timedelta(minutes=req.time_limit_minutes)
    
    db.execute(text("""
        INSERT INTO assessment_sessions (session_id, user_id, assessment_type, skill_id, status, config, started_at, created_at)
        VALUES (:session_id, :user_id, 'writing', :skill_id, 'in_progress', :config, :now, :now)
    """), {
        "session_id": session_id,
        "user_id": req.user_id,
        "skill_id": req.skill_id,
        "config": json.dumps(config),
        "now": started_at,
    })
    db.commit()
    
    return {
        "session_id": session_id,
        "prompt": {
            "id": prompt["id"],
            "title": prompt["title"],
            "prompt": prompt["prompt"],
        },
        "time_limit_minutes": req.time_limit_minutes,
        "word_range": [req.min_words, req.max_words],
        "started_at": started_at.isoformat(),
        "deadline": deadline.isoformat(),
        "anti_copy_token": anti_copy_token,
        "instructions": f"""
Writing Assessment Instructions:

1. TIME LIMIT: {req.time_limit_minutes} minutes
2. WORD COUNT: {req.min_words}-{req.max_words} words

IMPORTANT RULES:
- Type your response directly - DO NOT copy and paste
- Your keystrokes are being monitored for authenticity
- The timer starts immediately
- Submit before the deadline

EVALUATION CRITERIA:
- Content relevance and depth
- Organization and structure
- Grammar and mechanics
- Vocabulary and word choice
- Style and voice

Good luck!
        """.strip(),
    }


class WritingSubmitRequest(BaseModel):
    session_id: str
    content: str
    keystroke_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Keystroke timing data for anti-copy verification"
    )
    anti_copy_token: str


@router.post("/writing/submit")
def submit_writing_response(
    req: WritingSubmitRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    model_version: Optional[str] = Header(default=None, alias="X-Model-Version"),
    rubric_version: Optional[str] = Header(default=None, alias="X-Rubric-Version"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Submit a writing assessment response.
    """
    payload_hash = _payload_hash(req.model_dump(mode="json"))
    cached = _load_idempotency_hit(
        db,
        session_id=req.session_id,
        endpoint="writing_submit",
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
    )
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    versions = _assessment_versions(model_version, rubric_version)

    # Get session
    session = db.execute(text("""
        SELECT * FROM assessment_sessions WHERE session_id = :session_id
    """), {"session_id": req.session_id}).mappings().first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")
    
    config = json.loads(session["config"]) if isinstance(session["config"], str) else session["config"]
    
    # Verify anti-copy token
    if req.anti_copy_token != config.get("anti_copy_token"):
        raise HTTPException(status_code=400, detail="Invalid session token")
    
    # Check time limit
    started_at = session["started_at"]
    if started_at:
        elapsed_minutes = (_now_utc() - started_at).total_seconds() / 60
        if elapsed_minutes > config.get("time_limit_minutes", 30) + 2:  # 2 minute grace
            raise HTTPException(status_code=400, detail="Time limit exceeded")
    
    # Evaluate writing
    evaluation = _evaluate_writing(
        content=req.content,
        min_words=config.get("min_words", 300),
        max_words=config.get("max_words", 500),
        keystroke_data=req.keystroke_data,
    )
    
    # Store attempt
    attempt_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO assessment_attempts 
        (attempt_id, session_id, attempt_number, prompt_data, response_data, evaluation, score, submitted_at, created_at)
        VALUES (:attempt_id, :session_id, 1, :prompt_data, :response_data, :evaluation, :score, :now, :now)
    """), {
        "attempt_id": attempt_id,
        "session_id": req.session_id,
        "prompt_data": json.dumps({"prompt_id": config.get("prompt_id")}),
        "response_data": json.dumps({
            "content": req.content,
            "word_count": len(req.content.split()),
        }),
        "evaluation": json.dumps(evaluation),
        "score": evaluation.get("overall_score", 0),
        "now": _now_utc(),
    })
    
    # Update session
    db.execute(text("""
        UPDATE assessment_sessions SET status = 'completed', completed_at = :now
        WHERE session_id = :session_id
    """), {"session_id": req.session_id, "now": _now_utc()})

    try:
        skill_update = _persist_skill_outcome(
            db,
            user_id=str(session["user_id"]),
            skill_id=str(session["skill_id"] or "HKU.SKILL.TECHNICAL_WRITING.v1"),
            assessment_type="writing",
            response_text=req.content,
            evaluation=evaluation,
            session_id=str(req.session_id),
            attempt_id=attempt_id,
        )
    except Exception as e:
        skill_update = _enqueue_repair_job(
            db,
            session_id=str(req.session_id),
            attempt_id=attempt_id,
            user_id=str(session["user_id"]),
            skill_id=str(session["skill_id"] or "HKU.SKILL.TECHNICAL_WRITING.v1"),
            assessment_type="writing",
            response_text=req.content,
            evaluation=evaluation,
            error_message=f"{type(e).__name__}: {e}",
        )

    _record_drift_sample(
        db,
        session_id=str(req.session_id),
        attempt_id=attempt_id,
        user_id=str(session["user_id"]),
        skill_id=str(session["skill_id"] or "HKU.SKILL.TECHNICAL_WRITING.v1"),
        assessment_type="writing",
        response_text=req.content,
        evaluation=evaluation,
        model_version=versions["model_version"],
        rubric_version=versions["rubric_version"],
    )

    response_payload = {
        "attempt_id": attempt_id,
        "evaluation": evaluation,
        "skill_update": skill_update,
        "model_version": versions["model_version"],
        "rubric_version": versions["rubric_version"],
        "idempotent_replay": False,
    }
    _store_idempotency_hit(
        db,
        session_id=str(req.session_id),
        endpoint="writing_submit",
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        response_payload=response_payload,
    )
    db.commit()
    return response_payload


def _evaluate_writing_heuristic(
    content: str,
    min_words: int,
    max_words: int,
    keystroke_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Heuristic-only writing evaluation (fallback)."""
    word_count = len(content.split())
    sentence_count = len([s for s in content.split('.') if s.strip()])
    paragraph_count = len([p for p in content.split('\n\n') if p.strip()])
    if min_words <= word_count <= max_words:
        length_score = 100
    elif word_count < min_words:
        length_score = max(50, (word_count / min_words) * 100)
    else:
        length_score = max(70, 100 - ((word_count - max_words) / 50) * 10)
    if paragraph_count >= 3:
        structure_score = 90
    elif paragraph_count >= 2:
        structure_score = 70
    else:
        structure_score = 50
    avg_sentence_length = word_count / max(sentence_count, 1)
    if 15 <= avg_sentence_length <= 25:
        variety_score = 90
    elif 10 <= avg_sentence_length < 15 or 25 < avg_sentence_length <= 35:
        variety_score = 70
    else:
        variety_score = 50
    authenticity_score = 100
    authenticity_flags = []
    if keystroke_data:
        if keystroke_data.get("chars_per_minute", 0) > 500:
            authenticity_score = 50
            authenticity_flags.append("Unusually fast typing detected")
        if keystroke_data.get("paste_count", 0) > 2:
            authenticity_score = min(authenticity_score, 60)
            authenticity_flags.append("Paste events detected")
    overall_score = (
        length_score * 0.25 + structure_score * 0.25 + variety_score * 0.25 + authenticity_score * 0.25
    )
    if overall_score >= 85:
        level, label = 3, "Advanced"
    elif overall_score >= 70:
        level, label = 2, "Intermediate"
    elif overall_score >= 50:
        level, label = 1, "Developing"
    else:
        level, label = 0, "Novice"
    return {
        "overall_score": round(overall_score, 1),
        "level": level,
        "level_label": label,
        "metrics": {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "paragraph_count": paragraph_count,
            "avg_sentence_length": round(avg_sentence_length, 1),
            "length_score": round(length_score, 1),
            "structure_score": round(structure_score, 1),
            "variety_score": round(variety_score, 1),
            "authenticity_score": round(authenticity_score, 1),
        },
        "authenticity_flags": authenticity_flags,
        "feedback": _generate_writing_feedback(
            word_count, min_words, max_words, paragraph_count, avg_sentence_length
        ),
    }


def _evaluate_writing(
    content: str,
    min_words: int,
    max_words: int,
    keystroke_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Evaluate written response. Tries LLM first, falls back to heuristic."""
    word_count = len(content.split())
    llm_out = _llm_evaluate(
        "eval_writing_v1.txt",
        min_words=min_words,
        max_words=max_words,
        word_count=word_count,
        content=(content or "")[:MAX_INPUT_CHARS],
    )
    if llm_out and isinstance(llm_out.get("overall_score"), (int, float)) and 0 <= llm_out.get("level", -1) <= 3:
        fb = llm_out.get("feedback")
        if isinstance(fb, list):
            feedback_list = [str(x) for x in fb]
        else:
            feedback_list = [str(fb)] if fb else []
        metrics = llm_out.get("metrics") or {}
        if "word_count" not in metrics:
            metrics["word_count"] = word_count
        return {
            "overall_score": round(float(llm_out["overall_score"]), 1),
            "level": int(llm_out.get("level", 0)),
            "level_label": str(llm_out.get("level_label") or "Developing"),
            "metrics": metrics,
            "authenticity_flags": [],
            "feedback": feedback_list,
        }
    return _evaluate_writing_heuristic(content, min_words, max_words, keystroke_data)


def _generate_writing_feedback(
    word_count: int,
    min_words: int,
    max_words: int,
    paragraphs: int,
    avg_sentence_len: float,
) -> List[str]:
    """Generate feedback for writing assessment."""
    feedback = []
    
    if word_count < min_words:
        feedback.append(f"Your response is under the minimum word count ({word_count}/{min_words}). Try to develop your ideas more fully.")
    elif word_count > max_words:
        feedback.append(f"Your response exceeds the word limit ({word_count}/{max_words}). Consider being more concise.")
    else:
        feedback.append(f"Good job meeting the word count requirement ({word_count} words).")
    
    if paragraphs < 3:
        feedback.append("Consider organizing your response into more paragraphs for better readability.")
    
    if avg_sentence_len < 10:
        feedback.append("Try varying your sentence length - some sentences feel too short.")
    elif avg_sentence_len > 30:
        feedback.append("Some sentences are quite long. Consider breaking them up for clarity.")
    
    return feedback


# ====================
# Data Analysis Assessment
# ====================
DATA_ANALYSIS_DATASETS = [
    {
        "id": "sales_q1",
        "title": "Q1 Regional Sales",
        "summary": "Table: region, product, units_sold, revenue. 5 regions, 3 products. Revenue in USD.",
        "columns": ["region", "product", "units_sold", "revenue"],
        "rows": [
            ["North", "A", 120, 24000],
            ["North", "B", 85, 17000],
            ["North", "C", 90, 27000],
            ["South", "A", 95, 19000],
            ["South", "B", 110, 22000],
            ["South", "C", 70, 21000],
            ["East", "A", 130, 26000],
            ["East", "B", 75, 15000],
            ["East", "C", 100, 30000],
            ["West", "A", 80, 16000],
            ["West", "B", 120, 24000],
            ["West", "C", 60, 18000],
        ],
        "question": "Which region had the highest total revenue? What would you recommend to improve the lowest-performing product in the weakest region?",
        "time_limit_minutes": 25,
    },
    {
        "id": "survey_scores",
        "title": "Student Survey Scores",
        "summary": "Table: course_id, satisfaction_avg, completion_rate_pct, n_responses. 6 courses.",
        "columns": ["course_id", "satisfaction_avg", "completion_rate_pct", "n_responses"],
        "rows": [
            ["CS101", 4.2, 88, 120],
            ["CS102", 3.8, 72, 95],
            ["DS201", 4.5, 92, 80],
            ["DS202", 4.0, 85, 110],
            ["MGMT301", 3.5, 68, 75],
            ["MGMT302", 4.1, 90, 88],
        ],
        "question": "Identify the course with the lowest completion rate and suggest two data-driven improvements. Which visualization would best show the relationship between satisfaction and completion?",
        "time_limit_minutes": 25,
    },
]


class DataAnalysisSessionRequest(BaseModel):
    user_id: str
    skill_id: str = "HKU.SKILL.DATA_ANALYSIS.v1"


class DataAnalysisSubmitRequest(BaseModel):
    session_id: str
    analysis: str = Field(..., description="Student's written analysis and insights")
    visualization: str = Field(default="", description="Recommended chart type, e.g. bar, line, scatter, pie")


@router.post("/data_analysis/start")
def start_data_analysis_session(
    req: DataAnalysisSessionRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Start a data analysis assessment session with an embedded dataset."""
    ensure_assessment_tables(db)
    dataset = random.choice(DATA_ANALYSIS_DATASETS)
    session_id = str(uuid.uuid4())
    config = {
        "dataset_id": dataset["id"],
        "time_limit_minutes": dataset["time_limit_minutes"],
    }
    started_at = _now_utc()
    deadline = started_at + timedelta(minutes=dataset["time_limit_minutes"])
    db.execute(
        text("""
            INSERT INTO assessment_sessions (session_id, user_id, assessment_type, skill_id, status, config, started_at, created_at)
            VALUES (:session_id, :user_id, 'data_analysis', :skill_id, 'in_progress', :config, :now, :now)
        """),
        {
            "session_id": session_id,
            "user_id": req.user_id,
            "skill_id": req.skill_id,
            "config": json.dumps(config),
            "now": started_at,
        },
    )
    db.commit()
    return {
        "session_id": session_id,
        "dataset": {
            "id": dataset["id"],
            "title": dataset["title"],
            "summary": dataset["summary"],
            "columns": dataset["columns"],
            "rows": dataset["rows"],
            "question": dataset["question"],
        },
        "time_limit_minutes": dataset["time_limit_minutes"],
        "started_at": started_at.isoformat(),
        "deadline": deadline.isoformat(),
    }


@router.post("/data_analysis/submit")
def submit_data_analysis(
    req: DataAnalysisSubmitRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    model_version: Optional[str] = Header(default=None, alias="X-Model-Version"),
    rubric_version: Optional[str] = Header(default=None, alias="X-Rubric-Version"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Submit data analysis response for evaluation."""
    payload_hash = _payload_hash(req.model_dump(mode="json"))
    cached = _load_idempotency_hit(
        db, session_id=req.session_id, endpoint="data_analysis_submit",
        idempotency_key=idempotency_key, payload_hash=payload_hash,
    )
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    versions = _assessment_versions(model_version, rubric_version)
    session = db.execute(
        text("SELECT * FROM assessment_sessions WHERE session_id = :session_id"),
        {"session_id": req.session_id},
    ).mappings().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")
    config = json.loads(session["config"]) if isinstance(session["config"], str) else session["config"]
    dataset_id = config.get("dataset_id")
    dataset = next((d for d in DATA_ANALYSIS_DATASETS if d["id"] == dataset_id), None)
    if not dataset:
        raise HTTPException(status_code=500, detail="Dataset not found")
    evaluation = _evaluate_data_analysis(
        dataset_summary=dataset["summary"],
        question=dataset["question"],
        analysis=req.analysis,
        visualization=req.visualization,
    )
    attempt_id = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO assessment_attempts
            (attempt_id, session_id, attempt_number, prompt_data, response_data, evaluation, score, submitted_at, created_at)
            VALUES (:attempt_id, :session_id, 1, :prompt_data, :response_data, :evaluation, :score, :now, :now)
        """),
        {
            "attempt_id": attempt_id,
            "session_id": req.session_id,
            "prompt_data": json.dumps({"dataset_id": dataset_id}),
            "response_data": json.dumps({"analysis": req.analysis, "visualization": req.visualization}),
            "evaluation": json.dumps(evaluation),
            "score": evaluation.get("overall_score", 0),
            "now": _now_utc(),
        },
    )
    db.execute(
        text("UPDATE assessment_sessions SET status = 'completed', completed_at = :now WHERE session_id = :session_id"),
        {"session_id": req.session_id, "now": _now_utc()},
    )
    try:
        skill_update = _persist_skill_outcome(
            db,
            user_id=str(session["user_id"]),
            skill_id=str(session["skill_id"] or "HKU.SKILL.DATA_ANALYSIS.v1"),
            assessment_type="data_analysis",
            response_text=req.analysis,
            evaluation=evaluation,
            session_id=str(req.session_id),
            attempt_id=attempt_id,
        )
    except Exception as e:
        skill_update = _enqueue_repair_job(
            db, session_id=str(req.session_id), attempt_id=attempt_id,
            user_id=str(session["user_id"]), skill_id=str(session["skill_id"] or "HKU.SKILL.DATA_ANALYSIS.v1"),
            assessment_type="data_analysis", response_text=req.analysis, evaluation=evaluation,
            error_message=f"{type(e).__name__}: {e}",
        )
    _record_drift_sample(
        db, session_id=str(req.session_id), attempt_id=attempt_id,
        user_id=str(session["user_id"]), skill_id=str(session["skill_id"] or "HKU.SKILL.DATA_ANALYSIS.v1"),
        assessment_type="data_analysis", response_text=req.analysis, evaluation=evaluation,
        model_version=versions["model_version"], rubric_version=versions["rubric_version"],
    )
    response_payload = {
        "attempt_id": attempt_id,
        "evaluation": evaluation,
        "skill_update": skill_update,
        "model_version": versions["model_version"],
        "rubric_version": versions["rubric_version"],
        "idempotent_replay": False,
    }
    _store_idempotency_hit(db, session_id=req.session_id, endpoint="data_analysis_submit",
                           idempotency_key=idempotency_key, payload_hash=payload_hash, response_payload=response_payload)
    db.commit()
    return response_payload


def _evaluate_data_analysis(
    dataset_summary: str,
    question: str,
    analysis: str,
    visualization: str,
) -> Dict[str, Any]:
    """Evaluate data analysis response. LLM with heuristic fallback."""
    llm_out = _llm_evaluate(
        "eval_data_analysis_v1.txt",
        dataset_summary=(dataset_summary or "")[:500],
        question=(question or "")[:500],
        analysis=(analysis or "")[:MAX_INPUT_CHARS],
        visualization=(visualization or "none")[:200],
    )
    if llm_out and isinstance(llm_out.get("overall_score"), (int, float)) and 0 <= llm_out.get("level", -1) <= 3:
        feedback = llm_out.get("feedback")
        return {
            "overall_score": round(float(llm_out["overall_score"]), 1),
            "level": int(llm_out.get("level", 0)),
            "level_label": str(llm_out.get("level_label") or "Developing"),
            "metrics": llm_out.get("metrics") or {},
            "feedback": feedback if isinstance(feedback, str) else " ".join(str(x) for x in (feedback or [])),
        }
    # Heuristic fallback
    word_count = len((analysis or "").split())
    score = min(100, 40 + min(50, word_count // 5) + (20 if (visualization or "").strip() else 0))
    level = 3 if score >= 85 else 2 if score >= 70 else 1 if score >= 50 else 0
    label = "Advanced" if level == 3 else "Intermediate" if level == 2 else "Developing" if level == 1 else "Novice"
    return {
        "overall_score": round(score, 1),
        "level": level,
        "level_label": label,
        "metrics": {"insight_score": score, "visualization_score": 80 if visualization else 50},
        "feedback": "Assessment complete. Consider adding a clear visualization recommendation.",
    }


# ====================
# Problem Solving / Case Study Assessment
# ====================
PROBLEM_SOLVING_CASES = [
    {
        "id": "supply_chain",
        "title": "Supply Chain Disruption",
        "description": "A mid-sized retailer relies on a single supplier for 40% of its best-selling product. The supplier announces a 3-month shutdown due to a natural disaster. Inventory will run out in 6 weeks. How would you approach this problem? Provide: (1) Problem definition, (2) Analysis of options, (3) Recommended solution, (4) How you would evaluate success.",
        "time_limit_minutes": 25,
    },
    {
        "id": "team_conflict",
        "title": "Team Conflict",
        "description": "Two senior developers on your project disagree on the technical architecture. One prefers microservices; the other a monolith. Deadlines are in 8 weeks. Outline your approach: (1) How you would frame the problem, (2) What information you would gather, (3) How you would decide or facilitate a decision, (4) How you would prevent similar conflicts.",
        "time_limit_minutes": 25,
    },
    {
        "id": "declining_engagement",
        "title": "Declining User Engagement",
        "description": "A mobile app's daily active users have dropped 25% over the last quarter. Revenue is flat. Describe your problem-solving process: (1) How you would define and scope the problem, (2) What data or evidence you would analyze, (3) Two possible solutions with pros/cons, (4) How you would measure impact.",
        "time_limit_minutes": 25,
    },
]


class ProblemSolvingSessionRequest(BaseModel):
    user_id: str
    skill_id: str = "HKU.SKILL.CRITICAL_THINKING.v1"


class ProblemSolvingSubmitRequest(BaseModel):
    session_id: str
    response: str = Field(..., description="Structured analysis: problem definition, analysis, solution, evaluation")


@router.post("/problem_solving/start")
def start_problem_solving_session(
    req: ProblemSolvingSessionRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Start a problem-solving / case study assessment."""
    ensure_assessment_tables(db)
    case = random.choice(PROBLEM_SOLVING_CASES)
    session_id = str(uuid.uuid4())
    config = {"case_id": case["id"], "time_limit_minutes": case["time_limit_minutes"]}
    started_at = _now_utc()
    deadline = started_at + timedelta(minutes=case["time_limit_minutes"])
    db.execute(
        text("""
            INSERT INTO assessment_sessions (session_id, user_id, assessment_type, skill_id, status, config, started_at, created_at)
            VALUES (:session_id, :user_id, 'problem_solving', :skill_id, 'in_progress', :config, :now, :now)
        """),
        {"session_id": session_id, "user_id": req.user_id, "skill_id": req.skill_id, "config": json.dumps(config), "now": started_at},
    )
    db.commit()
    return {
        "session_id": session_id,
        "case": {"id": case["id"], "title": case["title"], "description": case["description"]},
        "time_limit_minutes": case["time_limit_minutes"],
        "started_at": started_at.isoformat(),
        "deadline": deadline.isoformat(),
    }


@router.post("/problem_solving/submit")
def submit_problem_solving(
    req: ProblemSolvingSubmitRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    model_version: Optional[str] = Header(default=None, alias="X-Model-Version"),
    rubric_version: Optional[str] = Header(default=None, alias="X-Rubric-Version"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Submit problem-solving response for evaluation."""
    payload_hash = _payload_hash(req.model_dump(mode="json"))
    cached = _load_idempotency_hit(db, session_id=req.session_id, endpoint="problem_solving_submit", idempotency_key=idempotency_key, payload_hash=payload_hash)
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    versions = _assessment_versions(model_version, rubric_version)
    session = db.execute(text("SELECT * FROM assessment_sessions WHERE session_id = :session_id"), {"session_id": req.session_id}).mappings().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")
    config = json.loads(session["config"]) if isinstance(session["config"], str) else session["config"]
    case_id = config.get("case_id")
    case = next((c for c in PROBLEM_SOLVING_CASES if c["id"] == case_id), None)
    if not case:
        raise HTTPException(status_code=500, detail="Case not found")
    evaluation = _evaluate_problem_solving(case_description=case["description"], response=req.response)
    attempt_id = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO assessment_attempts (attempt_id, session_id, attempt_number, prompt_data, response_data, evaluation, score, submitted_at, created_at)
            VALUES (:attempt_id, :session_id, 1, :prompt_data, :response_data, :evaluation, :score, :now, :now)
        """),
        {"attempt_id": attempt_id, "session_id": req.session_id, "prompt_data": json.dumps({"case_id": case_id}), "response_data": json.dumps({"response": req.response}), "evaluation": json.dumps(evaluation), "score": evaluation.get("overall_score", 0), "now": _now_utc()},
    )
    db.execute(text("UPDATE assessment_sessions SET status = 'completed', completed_at = :now WHERE session_id = :session_id"), {"session_id": req.session_id, "now": _now_utc()})
    try:
        skill_update = _persist_skill_outcome(db, user_id=str(session["user_id"]), skill_id=str(session["skill_id"] or "HKU.SKILL.CRITICAL_THINKING.v1"), assessment_type="problem_solving", response_text=req.response, evaluation=evaluation, session_id=str(req.session_id), attempt_id=attempt_id)
    except Exception as e:
        skill_update = _enqueue_repair_job(db, session_id=str(req.session_id), attempt_id=attempt_id, user_id=str(session["user_id"]), skill_id=str(session["skill_id"] or "HKU.SKILL.CRITICAL_THINKING.v1"), assessment_type="problem_solving", response_text=req.response, evaluation=evaluation, error_message=f"{type(e).__name__}: {e}")
    _record_drift_sample(db, session_id=str(req.session_id), attempt_id=attempt_id, user_id=str(session["user_id"]), skill_id=str(session["skill_id"] or "HKU.SKILL.CRITICAL_THINKING.v1"), assessment_type="problem_solving", response_text=req.response, evaluation=evaluation, model_version=versions["model_version"], rubric_version=versions["rubric_version"])
    response_payload = {"attempt_id": attempt_id, "evaluation": evaluation, "skill_update": skill_update, "model_version": versions["model_version"], "rubric_version": versions["rubric_version"], "idempotent_replay": False}
    _store_idempotency_hit(db, session_id=req.session_id, endpoint="problem_solving_submit", idempotency_key=idempotency_key, payload_hash=payload_hash, response_payload=response_payload)
    db.commit()
    return response_payload


def _evaluate_problem_solving(case_description: str, response: str) -> Dict[str, Any]:
    """Evaluate problem-solving response. LLM with heuristic fallback."""
    llm_out = _llm_evaluate(
        "eval_problem_solving_v1.txt",
        case_description=(case_description or "")[:1500],
        response=(response or "")[:MAX_INPUT_CHARS],
    )
    if llm_out and isinstance(llm_out.get("overall_score"), (int, float)) and 0 <= llm_out.get("level", -1) <= 3:
        feedback = llm_out.get("feedback")
        return {
            "overall_score": round(float(llm_out["overall_score"]), 1),
            "level": int(llm_out.get("level", 0)),
            "level_label": str(llm_out.get("level_label") or "Developing"),
            "metrics": llm_out.get("metrics") or {},
            "feedback": feedback if isinstance(feedback, str) else " ".join(str(x) for x in (feedback or [])),
        }
    word_count = len((response or "").split())
    score = min(100, 30 + min(60, word_count // 4))
    level = 3 if score >= 85 else 2 if score >= 70 else 1 if score >= 50 else 0
    label = "Advanced" if level == 3 else "Intermediate" if level == 2 else "Developing" if level == 1 else "Novice"
    return {"overall_score": round(score, 1), "level": level, "level_label": label, "metrics": {}, "feedback": "Assessment complete."}


# ====================
# Presentation / Pitch Assessment
# ====================
PRESENTATION_TOPICS = [
    {"id": "product_pitch", "title": "Product Pitch", "topic": "Pitch a product or service idea to a potential investor. Structure: hook, problem, solution, market, ask. 8-10 minutes.", "time_limit_minutes": 10},
    {"id": "project_retro", "title": "Project Retrospective", "topic": "Present a short retrospective of a project (real or hypothetical): what went well, what didn't, and what you would do differently. 8-10 minutes.", "time_limit_minutes": 10},
    {"id": "persuasive_talk", "title": "Persuasive Talk", "topic": "Convince your audience of a specific policy or practice change (e.g. remote work, sustainability). Use clear structure and evidence. 8-10 minutes.", "time_limit_minutes": 10},
]


class PresentationSessionRequest(BaseModel):
    user_id: str
    skill_id: str = "HKU.SKILL.COMMUNICATION.v1"


class PresentationSubmitRequest(BaseModel):
    session_id: str
    transcript: str = Field(..., description="Speech transcript from recording")
    outline: str = Field(default="", description="Presentation outline (intro, main points, conclusion)")
    audio_duration_seconds: float = Field(default=0, description="Recording duration")


@router.post("/presentation/start")
def start_presentation_session(
    req: PresentationSessionRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Start a presentation / pitch assessment."""
    ensure_assessment_tables(db)
    topic = random.choice(PRESENTATION_TOPICS)
    session_id = str(uuid.uuid4())
    config = {"topic_id": topic["id"], "time_limit_minutes": topic["time_limit_minutes"]}
    started_at = _now_utc()
    deadline = started_at + timedelta(minutes=topic["time_limit_minutes"])
    db.execute(
        text("""
            INSERT INTO assessment_sessions (session_id, user_id, assessment_type, skill_id, status, config, started_at, created_at)
            VALUES (:session_id, :user_id, 'presentation', :skill_id, 'in_progress', :config, :now, :now)
        """),
        {"session_id": session_id, "user_id": req.user_id, "skill_id": req.skill_id, "config": json.dumps(config), "now": started_at},
    )
    db.commit()
    return {
        "session_id": session_id,
        "topic": {"id": topic["id"], "title": topic["title"], "topic": topic["topic"]},
        "time_limit_minutes": topic["time_limit_minutes"],
        "started_at": started_at.isoformat(),
        "deadline": deadline.isoformat(),
    }


@router.post("/presentation/submit")
def submit_presentation(
    req: PresentationSubmitRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    model_version: Optional[str] = Header(default=None, alias="X-Model-Version"),
    rubric_version: Optional[str] = Header(default=None, alias="X-Rubric-Version"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Submit presentation (transcript + outline) for evaluation."""
    payload_hash = _payload_hash(req.model_dump(mode="json"))
    cached = _load_idempotency_hit(db, session_id=req.session_id, endpoint="presentation_submit", idempotency_key=idempotency_key, payload_hash=payload_hash)
    if cached is not None:
        return {**cached, "idempotent_replay": True}
    versions = _assessment_versions(model_version, rubric_version)
    session = db.execute(text("SELECT * FROM assessment_sessions WHERE session_id = :session_id"), {"session_id": req.session_id}).mappings().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")
    config = json.loads(session["config"]) if isinstance(session["config"], str) else session["config"]
    topic_id = config.get("topic_id")
    topic_obj = next((t for t in PRESENTATION_TOPICS if t["id"] == topic_id), None)
    topic_text = topic_obj["topic"] if topic_obj else ""
    evaluation = _evaluate_presentation(topic=topic_text, outline=req.outline, transcript=req.transcript)
    attempt_id = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO assessment_attempts (attempt_id, session_id, attempt_number, prompt_data, response_data, evaluation, score, submitted_at, created_at)
            VALUES (:attempt_id, :session_id, 1, :prompt_data, :response_data, :evaluation, :score, :now, :now)
        """),
        {"attempt_id": attempt_id, "session_id": req.session_id, "prompt_data": json.dumps({"topic_id": topic_id}), "response_data": json.dumps({"transcript": req.transcript, "outline": req.outline, "audio_duration_seconds": req.audio_duration_seconds}), "evaluation": json.dumps(evaluation), "score": evaluation.get("overall_score", 0), "now": _now_utc()},
    )
    db.execute(text("UPDATE assessment_sessions SET status = 'completed', completed_at = :now WHERE session_id = :session_id"), {"session_id": req.session_id, "now": _now_utc()})
    try:
        skill_update = _persist_skill_outcome(db, user_id=str(session["user_id"]), skill_id=str(session["skill_id"] or "HKU.SKILL.COMMUNICATION.v1"), assessment_type="presentation", response_text=req.transcript + "\n\nOutline:\n" + req.outline, evaluation=evaluation, session_id=str(req.session_id), attempt_id=attempt_id)
    except Exception as e:
        skill_update = _enqueue_repair_job(db, session_id=str(req.session_id), attempt_id=attempt_id, user_id=str(session["user_id"]), skill_id=str(session["skill_id"] or "HKU.SKILL.COMMUNICATION.v1"), assessment_type="presentation", response_text=req.transcript, evaluation=evaluation, error_message=f"{type(e).__name__}: {e}")
    _record_drift_sample(db, session_id=str(req.session_id), attempt_id=attempt_id, user_id=str(session["user_id"]), skill_id=str(session["skill_id"] or "HKU.SKILL.COMMUNICATION.v1"), assessment_type="presentation", response_text=req.transcript, evaluation=evaluation, model_version=versions["model_version"], rubric_version=versions["rubric_version"])
    response_payload = {"attempt_id": attempt_id, "evaluation": evaluation, "skill_update": skill_update, "model_version": versions["model_version"], "rubric_version": versions["rubric_version"], "idempotent_replay": False}
    _store_idempotency_hit(db, session_id=req.session_id, endpoint="presentation_submit", idempotency_key=idempotency_key, payload_hash=payload_hash, response_payload=response_payload)
    db.commit()
    return response_payload


def _evaluate_presentation(topic: str, outline: str, transcript: str) -> Dict[str, Any]:
    """Evaluate presentation. LLM with heuristic fallback."""
    llm_out = _llm_evaluate(
        "eval_presentation_v1.txt",
        topic=(topic or "")[:500],
        outline=(outline or "")[:1500],
        transcript=(transcript or "")[:MAX_INPUT_CHARS],
    )
    if llm_out and isinstance(llm_out.get("overall_score"), (int, float)) and 0 <= llm_out.get("level", -1) <= 3:
        feedback = llm_out.get("feedback")
        return {
            "overall_score": round(float(llm_out["overall_score"]), 1),
            "level": int(llm_out.get("level", 0)),
            "level_label": str(llm_out.get("level_label") or "Developing"),
            "metrics": llm_out.get("metrics") or {},
            "feedback": feedback if isinstance(feedback, str) else " ".join(str(x) for x in (feedback or [])),
        }
    word_count = len((transcript or "").split())
    score = min(100, 40 + min(50, word_count // 3) + (15 if (outline or "").strip() else 0))
    level = 3 if score >= 85 else 2 if score >= 70 else 1 if score >= 50 else 0
    label = "Advanced" if level == 3 else "Intermediate" if level == 2 else "Developing" if level == 1 else "Novice"
    return {"overall_score": round(score, 1), "level": level, "level_label": label, "metrics": {}, "feedback": "Assessment complete."}


# ====================
# Session Management
# ====================
@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get assessment session details."""
    session = db.execute(text("""
        SELECT * FROM assessment_sessions WHERE session_id = :session_id
    """), {"session_id": session_id}).mappings().first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get attempts
    attempts = db.execute(text("""
        SELECT * FROM assessment_attempts 
        WHERE session_id = :session_id 
        ORDER BY attempt_number ASC
    """), {"session_id": session_id}).mappings().all()
    
    return {
        "session": dict(session),
        "attempts": [dict(a) for a in attempts],
    }


class ReplaySyncRequest(BaseModel):
    force: bool = False


@router.post("/sessions/{session_id}/replay_sync")
def replay_session_skill_sync(
    session_id: str,
    req: ReplaySyncRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Replay latest attempt of one session to repair skill sync.
    """
    session = db.execute(text("""
        SELECT * FROM assessment_sessions WHERE session_id = :session_id
    """), {"session_id": session_id}).mappings().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    attempt = db.execute(text("""
        SELECT * FROM assessment_attempts
        WHERE session_id = :session_id
        ORDER BY submitted_at DESC NULLS LAST, created_at DESC
        LIMIT 1
    """), {"session_id": session_id}).mappings().first()
    if not attempt:
        raise HTTPException(status_code=404, detail="No attempts found for session")

    attempt_id = str(attempt["attempt_id"])
    existing = db.execute(text("""
        SELECT assessment_id
        FROM skill_assessments
        WHERE decision_meta ->> 'session_id' = :session_id
          AND decision_meta ->> 'attempt_id' = :attempt_id
        ORDER BY created_at DESC
        LIMIT 1
    """), {"session_id": session_id, "attempt_id": attempt_id}).mappings().first()
    if existing and not req.force:
        return {
            "replayed": False,
            "reason": "already_synced",
            "session_id": session_id,
            "attempt_id": attempt_id,
            "assessment_id": str(existing["assessment_id"]),
        }

    response_data = attempt.get("response_data") or {}
    if isinstance(response_data, str):
        try:
            response_data = json.loads(response_data)
        except Exception:
            response_data = {}
    if not isinstance(response_data, dict):
        response_data = {}

    evaluation = attempt.get("evaluation") or {}
    if isinstance(evaluation, str):
        try:
            evaluation = json.loads(evaluation)
        except Exception:
            evaluation = {}
    if not isinstance(evaluation, dict):
        evaluation = {}

    assessment_type = str(session.get("assessment_type") or "")
    if assessment_type == "communication":
        response_text = str(response_data.get("transcript") or "")
    elif assessment_type == "programming":
        response_text = str(response_data.get("code") or "")
    elif assessment_type == "writing":
        response_text = str(response_data.get("content") or "")
    else:
        response_text = json.dumps(response_data, ensure_ascii=False)

    skill_update = _persist_skill_outcome(
        db,
        user_id=str(session["user_id"]),
        skill_id=str(session.get("skill_id") or ""),
        assessment_type=assessment_type,
        response_text=response_text,
        evaluation=evaluation,
        session_id=session_id,
        attempt_id=attempt_id,
    )
    db.commit()
    return {
        "replayed": True,
        "session_id": session_id,
        "attempt_id": attempt_id,
        "skill_update": skill_update,
    }


@router.get("/repair_jobs")
def list_assessment_repair_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 200))
    where_sql = "WHERE status = :status" if status else ""
    rows = db.execute(text(f"""
        SELECT repair_job_id, session_id, attempt_id, user_id, skill_id, assessment_type, status,
               attempts, max_attempts, next_retry_at, dead_lettered_at, dead_letter_reason,
               last_error, rq_job_id, created_at, updated_at
        FROM assessment_repair_jobs
        {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"status": status, "limit": safe_limit}).mappings().all()
    items = []
    for r in rows:
        d = dict(r)
        for id_key in ("repair_job_id", "session_id", "attempt_id"):
            if d.get(id_key) is not None:
                d[id_key] = str(d[id_key])
        items.append(d)
    return {"count": len(items), "items": items}


@router.get("/drift/summary")
def get_assessment_drift_summary(
    assessment_type: Optional[str] = None,
    window_hours: int = 24,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    safe_window = max(1, min(window_hours, 24 * 30))
    params: Dict[str, Any] = {"window_hours": safe_window}
    where_parts = ["created_at >= now() - make_interval(hours => :window_hours)"]
    if assessment_type:
        where_parts.append("assessment_type = :assessment_type")
        params["assessment_type"] = assessment_type
    where_sql = " AND ".join(where_parts)
    rows = db.execute(text(f"""
        SELECT assessment_type, model_version, rubric_version,
               COUNT(*) AS sample_count,
               AVG(score) AS avg_score,
               STDDEV_POP(score) AS score_stddev,
               MIN(score) AS min_score,
               MAX(score) AS max_score
        FROM assessment_drift_samples
        WHERE {where_sql}
        GROUP BY assessment_type, model_version, rubric_version
        ORDER BY sample_count DESC, assessment_type ASC
    """), params).mappings().all()
    items = []
    for r in rows:
        d = dict(r)
        for k in ("avg_score", "score_stddev", "min_score", "max_score"):
            if d.get(k) is not None:
                d[k] = round(float(d[k]), 3)
        items.append(d)
    return {"window_hours": safe_window, "count": len(items), "items": items}


@router.get("/sessions/user/{user_id}")
def get_user_sessions(
    user_id: str,
    assessment_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get all assessment sessions for a user."""
    if assessment_type:
        sessions = db.execute(text("""
            SELECT * FROM assessment_sessions 
            WHERE user_id = :user_id AND assessment_type = :type
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"user_id": user_id, "type": assessment_type, "limit": limit}).mappings().all()
    else:
        sessions = db.execute(text("""
            SELECT * FROM assessment_sessions 
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"user_id": user_id, "limit": limit}).mappings().all()
    
    return {
        "user_id": user_id,
        "count": len(sessions),
        "sessions": [dict(s) for s in sessions],
    }


@router.get("/users/{user_id}/recent_updates")
def get_user_recent_assessment_updates(
    user_id: str,
    limit: int = 10,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get recent interactive assessments plus linked skill updates for one user.
    """
    def _assessment_event_item(row: Dict[str, Any], skill_update: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        submitted_at = row.get("submitted_at")
        completed_at = row.get("completed_at")
        event_ts = submitted_at or completed_at
        session_id = str(row["session_id"])
        return {
            "event_id": f"{session_id}:{(event_ts.isoformat() if event_ts else 'na')}",
            "event_type": "interactive_assessment_submitted",
            "session_id": session_id,
            "attempt_id": str(row.get("attempt_id")) if row.get("attempt_id") is not None else None,
            "assessment_type": row.get("assessment_type"),
            "skill_id": str(row.get("skill_id") or ""),
            "submitted_at": submitted_at.isoformat() if submitted_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
            "score": float(row.get("score") or 0),
            "level": int(row.get("level")) if isinstance(row.get("level"), (int, float)) else 0,
            "status": "completed",
            "skill_update": skill_update,
        }

    try:
        sess_rows = db.execute(text("""
            SELECT s.session_id, s.assessment_type, s.skill_id, s.completed_at, a.attempt_id, a.submitted_at, a.score, a.evaluation
            FROM assessment_sessions s
            JOIN assessment_attempts a ON a.session_id = s.session_id
            WHERE s.user_id = :user_id
            ORDER BY COALESCE(a.submitted_at, s.completed_at, s.created_at) DESC
            LIMIT :limit
        """), {"user_id": user_id, "limit": max(1, min(limit, 50))}).mappings().all()

        prof_rows = db.execute(text("""
            SELECT sp.skill_id, sp.level, sp.label, sp.rationale, sp.created_at, sp.doc_id
            FROM skill_proficiency sp
            JOIN consents c ON c.doc_id = sp.doc_id::text
            WHERE c.user_id = :user_id AND c.status = 'granted'
            ORDER BY sp.created_at DESC
            LIMIT :limit
        """), {"user_id": user_id, "limit": max(1, min(limit * 3, 200))}).mappings().all()

        latest_prof_by_skill: Dict[str, Dict[str, Any]] = {}
        for r in prof_rows:
            sid = str(r["skill_id"])
            if sid not in latest_prof_by_skill:
                latest_prof_by_skill[sid] = {
                    "level": int(r["level"]) if r.get("level") is not None else 0,
                    "label": r.get("label"),
                    "rationale": r.get("rationale"),
                    "doc_id": str(r["doc_id"]) if r.get("doc_id") is not None else None,
                    "updated_at": r.get("created_at").isoformat() if r.get("created_at") else None,
                }

        items: List[Dict[str, Any]] = []
        for row in sess_rows:
            ev = row.get("evaluation")
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except Exception:
                    ev = {}
            if not isinstance(ev, dict):
                ev = {}

            sid = str(row.get("skill_id") or "")
            score = row.get("score")
            if score is None:
                score = ev.get("overall_score", ev.get("score", 0))
            level = ev.get("level")
            if isinstance(level, str):
                lmap = {"novice": 0, "developing": 1, "intermediate": 2, "advanced": 3, "expert": 3}
                level = lmap.get(level.lower(), 0)

            skill_update = latest_prof_by_skill.get(sid)
            items.append(_assessment_event_item({
                "session_id": row["session_id"],
                "attempt_id": row.get("attempt_id"),
                "assessment_type": row.get("assessment_type"),
                "skill_id": sid,
                "submitted_at": row.get("submitted_at"),
                "completed_at": row.get("completed_at"),
                "score": float(score or 0),
                "level": int(level) if isinstance(level, (int, float)) else 0,
            }, skill_update))

        return {"user_id": user_id, "count": len(items), "items": items, "assessment_events": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"recent updates query failed: {type(e).__name__}: {e}")


@router.get("/sessions/{session_id}/consistency")
def get_consistency_score(
    session_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Calculate consistency score across multiple attempts.
    Useful for communication assessment with retries.
    """
    attempts = db.execute(text("""
        SELECT * FROM assessment_attempts 
        WHERE session_id = :session_id 
        ORDER BY attempt_number ASC
    """), {"session_id": session_id}).mappings().all()
    
    if not attempts:
        raise HTTPException(status_code=404, detail="No attempts found")
    
    scores = [a["score"] for a in attempts if a.get("score") is not None]
    
    if len(scores) < 2:
        return {
            "session_id": session_id,
            "attempts": len(attempts),
            "consistency_score": None,
            "message": "Need at least 2 attempts for consistency calculation",
        }
    
    # Calculate consistency (lower variance = more consistent)
    mean_score = sum(scores) / len(scores)
    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
    std_dev = variance ** 0.5
    
    # Convert to consistency score (100 = perfectly consistent)
    consistency = max(0, 100 - (std_dev * 2))
    
    # Best and latest scores
    best_score = max(scores)
    latest_score = scores[-1]
    
    # Trend
    if len(scores) >= 2:
        if scores[-1] > scores[0]:
            trend = "improving"
        elif scores[-1] < scores[0]:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "n/a"
    
    return {
        "session_id": session_id,
        "attempts": len(attempts),
        "scores": scores,
        "mean_score": round(mean_score, 1),
        "best_score": round(best_score, 1),
        "latest_score": round(latest_score, 1),
        "consistency_score": round(consistency, 1),
        "trend": trend,
        "recommendation": _get_consistency_recommendation(consistency, trend),
    }


def _get_consistency_recommendation(consistency: float, trend: str) -> str:
    """Generate recommendation based on consistency and trend."""
    if consistency >= 90:
        return "Excellent consistency! Your performance is reliable."
    elif consistency >= 70:
        if trend == "improving":
            return "Good consistency with improvement shown. Keep practicing!"
        else:
            return "Reasonably consistent performance. Focus on maintaining your best."
    else:
        if trend == "improving":
            return "Performance varies but showing improvement. Continue practicing for more consistency."
        else:
            return "Performance is inconsistent. Consider reviewing fundamentals and practicing more."
