"""
Tutor dialogue service for Live Agent (RAG) — create session, append turns,
build LLM messages, parse assessment from reply, persist conclusion.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PKG_DIR = Path(__file__).resolve().parents[3] / "packages" / "prompts"
PROMPTS_DIR = _BACKEND_DIR / "prompts" if (_BACKEND_DIR / "prompts").exists() else _PKG_DIR


def _load_system_prompt(mode: str = "assessment") -> str:
    if mode == "resume_review":
        p = PROMPTS_DIR / "resume_review_system_v1.txt"
    else:
        # Prefer assessment-focused prompt (no small talk, 10-turn limit)
        p = PROMPTS_DIR / "assessment_agent_system_v1.txt"
        if not p.exists():
            p = PROMPTS_DIR / "tutor_dialogue_system_v1.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    if mode == "resume_review":
        return (
            "You are SkillSight, an HKU career advisor. Review the student's resume and give "
            "actionable feedback. Do NOT output ASSESSMENT: {...}. Give strengths, gaps, and suggestions."
        )
    return (
        "You are an HKU skills assessment tutor. Use only the evidence provided. "
        "When you can conclude, output: ASSESSMENT: {\"level\": 0|1|2|3, \"evidence_chunk_ids\": [...], \"why\": \"...\"}"
    )


def create_session(
    db: Session,
    user_id: str,
    skill_id: str,
    doc_ids: Optional[List[str]] = None,
    mode: str = "assessment",
) -> str:
    """Create a tutor dialogue session. Returns session_id. mode: 'assessment' | 'resume_review'."""
    session_id = str(uuid.uuid4())
    doc_ids = doc_ids or []
    mode = "resume_review" if mode == "resume_review" else "assessment"
    db.execute(
        text("""
            INSERT INTO tutor_dialogue_sessions (session_id, user_id, skill_id, doc_ids, status, mode, created_at)
            VALUES (:session_id, :user_id, :skill_id, CAST(:doc_ids AS JSONB), 'active', :mode, :now)
        """),
        {
            "session_id": session_id,
            "user_id": user_id,
            "skill_id": skill_id,
            "doc_ids": json.dumps(doc_ids),
            "mode": mode,
            "now": datetime.now(timezone.utc),
        },
    )
    db.commit()
    return session_id


def get_session(db: Session, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Get session by id; ensure it belongs to user_id."""
    row = db.execute(
        text("""
            SELECT session_id, user_id, skill_id, doc_ids, status, created_at,
                   COALESCE(mode, 'assessment') AS mode
            FROM tutor_dialogue_sessions
            WHERE session_id = :session_id AND user_id = :user_id
        """),
        {"session_id": session_id, "user_id": user_id},
    ).mappings().first()
    if not row:
        return None
    d = dict(row)
    if isinstance(d.get("doc_ids"), str):
        try:
            d["doc_ids"] = json.loads(d["doc_ids"])
        except Exception:
            d["doc_ids"] = []
    if d.get("mode") is None:
        d["mode"] = "assessment"
    return d


def append_turn(
    db: Session,
    session_id: str,
    role: str,
    content: str,
    retrieved_chunk_ids: Optional[List[str]] = None,
) -> None:
    """Append a dialogue turn."""
    turn_id = str(uuid.uuid4())
    retrieved_chunk_ids = retrieved_chunk_ids or []
    db.execute(
        text("""
            INSERT INTO tutor_dialogue_turns (turn_id, session_id, role, content, retrieved_chunk_ids, created_at)
            VALUES (:turn_id, :session_id, :role, :content, CAST(:chunk_ids AS JSONB), :now)
        """),
        {
            "turn_id": turn_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "chunk_ids": json.dumps(retrieved_chunk_ids),
            "now": datetime.now(timezone.utc),
        },
    )
    db.commit()


def get_turns(db: Session, session_id: str) -> List[Dict[str, Any]]:
    """Get all turns for a session in order."""
    rows = db.execute(
        text("""
            SELECT role, content, retrieved_chunk_ids, created_at
            FROM tutor_dialogue_turns
            WHERE session_id = :session_id
            ORDER BY created_at ASC
        """),
        {"session_id": session_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_messages_for_llm(
    db: Session,
    session_id: str,
    skill_definition: str,
    rubric_summary: str,
    evidence_chunks_text: str,
    mode: str = "assessment",
    student_skill_summary: Optional[str] = None,
    doc_count: Optional[int] = None,
    verified_skills_count: Optional[int] = None,
) -> List[Dict[str, str]]:
    """
    Build OpenAI messages: system + first user (context) + history turns.
    evidence_chunks_text should be formatted as "chunk_id: snippet" lines.
    mode: 'assessment' | 'resume_review' selects the system prompt.
    student_skill_summary: optional text for resume_review (student's verified skills and levels).
    doc_count: optional number of documents the session is based on (for context hint).
    verified_skills_count: optional number of skills verified with evidence (resume_review hint).
    """
    system = _load_system_prompt(mode)
    context_hint = ""
    if doc_count is not None and doc_count > 0:
        context_hint = f"Current session is based on {doc_count} document(s) the student has uploaded.\n\n"
    if mode == "resume_review":
        if verified_skills_count is not None and verified_skills_count > 0:
            context_hint += f"The student has {verified_skills_count} skill(s) currently verified with evidence.\n\n"
        skill_block = ""
        if student_skill_summary:
            skill_block = f"STUDENT'S CURRENT SKILL PROFILE (use this to align resume feedback):\n{student_skill_summary}\n\n"
        first_user = (
            f"{context_hint}{skill_block}EVIDENCE CHUNKS (student's uploaded documents):\n{evidence_chunks_text}\n\n"
            "The student will now share their resume or ask for feedback. Give structured resume feedback; do NOT output ASSESSMENT."
        )
    else:
        first_user = (
            f"{context_hint}SKILL DEFINITION:\n{skill_definition}\n\nRUBRIC (levels 0-3):\n{rubric_summary}\n\n"
            f"EVIDENCE CHUNKS (use only these chunk_ids in ASSESSMENT):\n{evidence_chunks_text}\n\n"
            "The student will now chat. Reply based only on the evidence above; if enough to conclude, output ASSESSMENT line."
        )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": first_user},
    ]
    turns = get_turns(db, session_id)
    user_turn_count = sum(1 for t in turns if t.get("role") == "user")
    for t in turns:
        messages.append({"role": t["role"], "content": (t["content"] or "").strip()})
    # Force conclusion after 10 user messages (assessment-focused mode)
    if mode == "assessment" and user_turn_count >= 10:
        messages.append({
            "role": "user",
            "content": "Maximum turns reached. Please output your ASSESSMENT now as ASSESSMENT: {\"level\": ..., \"evidence_chunk_ids\": [...], \"why\": \"...\"}",
        })
    return messages


def parse_assessment_from_reply(reply: str) -> Optional[Dict[str, Any]]:
    """
    Extract ASSESSMENT JSON from assistant reply.
    Returns None if not found or invalid; else {"level": int, "evidence_chunk_ids": list, "why": str}.
    """
    reply = (reply or "").strip()
    match = re.search(r"ASSESSMENT:\s*(\{.*?\})(?:\s|$)", reply, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(1))
        if not isinstance(obj, dict):
            return None
        level = obj.get("level")
        if level is None or not isinstance(level, int) or not (0 <= level <= 3):
            return None
        chunk_ids = obj.get("evidence_chunk_ids")
        if not isinstance(chunk_ids, list):
            chunk_ids = []
        return {
            "level": level,
            "evidence_chunk_ids": [str(x) for x in chunk_ids],
            "why": (obj.get("why") or "").strip(),
        }
    except (json.JSONDecodeError, TypeError):
        return None


LEVEL_LABELS = {0: "novice", 1: "developing", 2: "proficient", 3: "advanced"}


def conclude_and_persist_assessment(
    db: Session,
    session_id: str,
    user_id: str,
    level: int,
    evidence_chunk_ids: List[str],
    why: str,
) -> None:
    """
    Write assessment to skill_assessments and skill_proficiency for the first doc in session;
    set session status to concluded.
    """
    session = get_session(db, session_id, user_id)
    if not session or session.get("status") == "concluded":
        return
    doc_ids = session.get("doc_ids") or []
    doc_id = doc_ids[0] if doc_ids else None
    if not doc_id:
        # No doc to attach; still conclude session
        db.execute(
            text("UPDATE tutor_dialogue_sessions SET status = 'concluded' WHERE session_id = :sid"),
            {"sid": session_id},
        )
        db.commit()
        return

    skill_id = session["skill_id"]
    label = LEVEL_LABELS.get(level, "novice")
    now = datetime.now(timezone.utc)

    # skill_assessments
    ass_id = str(uuid.uuid4())
    evidence_json = json.dumps([{"chunk_id": cid, "snippet": ""} for cid in evidence_chunk_ids])
    meta_json = json.dumps({"source": "tutor_dialogue", "session_id": session_id, "rationale": why[:500]})
    db.execute(
        text("""
            INSERT INTO skill_assessments (assessment_id, doc_id, skill_id, decision, evidence, decision_meta, created_at)
            VALUES (:aid, :doc_id, :skill_id, :decision, CAST(:evidence AS JSONB), CAST(:meta AS JSONB), :now)
        """),
        {
            "aid": ass_id,
            "doc_id": doc_id,
            "skill_id": skill_id,
            "decision": label,
            "evidence": evidence_json,
            "meta": meta_json,
            "now": now,
        },
    )

    # skill_proficiency
    prof_id = str(uuid.uuid4())
    best_evidence = {}
    if evidence_chunk_ids:
        best_evidence = {"chunk_id": evidence_chunk_ids[0], "snippet": ""}
    db.execute(
        text("""
            INSERT INTO skill_proficiency (prof_id, doc_id, skill_id, level, label, rationale, best_evidence, signals, meta, created_at)
            VALUES (:pid, :doc_id, :skill_id, :level, :label, :rationale, CAST(:best_evidence AS JSONB), '{}'::jsonb, CAST(:meta AS JSONB), :now)
        """),
        {
            "pid": prof_id,
            "doc_id": doc_id,
            "skill_id": skill_id,
            "level": level,
            "label": label,
            "rationale": why[:2000],
            "best_evidence": json.dumps(best_evidence),
            "meta": json.dumps({"source": "tutor_dialogue", "session_id": session_id}),
            "now": now,
        },
    )

    db.execute(
        text("UPDATE tutor_dialogue_sessions SET status = 'concluded' WHERE session_id = :sid"),
        {"sid": session_id},
    )
    db.commit()


def set_session_concluded(db: Session, session_id: str) -> None:
    """Mark session as concluded without writing assessment."""
    db.execute(
        text("UPDATE tutor_dialogue_sessions SET status = 'concluded' WHERE session_id = :sid"),
        {"sid": session_id},
    )
    db.commit()
