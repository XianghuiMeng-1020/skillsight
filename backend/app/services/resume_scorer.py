"""
Resume scoring service: load rubric + prompt, get resume text from chunks,
call LLM, return structured scores and weighted total.
"""
from __future__ import annotations

import functools
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = Path(__file__).resolve().parents[2]
PROMPTS_DIR = _BACKEND_DIR / "prompts" if (_BACKEND_DIR / "prompts").exists() else REPO_ROOT / "packages" / "prompts"
SCHEMAS_DIR = REPO_ROOT / "packages" / "schemas"

_log = logging.getLogger(__name__)

# Minimum resume length (chars) to avoid scoring empty or tiny content
MIN_RESUME_LENGTH = 100

# LLM timeout for scoring (seconds)
SCORING_TIMEOUT = 120


def _get_llm_generate():
    """Return the configured LLM generate function (openai or ollama)."""
    provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if provider == "ollama":
        try:
            from backend.app.ollama_client import ollama_generate
            return ollama_generate
        except ImportError:
            pass
    try:
        from backend.app.openai_client import openai_generate
        return openai_generate
    except ImportError:
        try:
            from backend.app.ollama_client import ollama_generate
            return ollama_generate
        except ImportError:
            raise RuntimeError("No LLM client available (install openai or ollama)")


def _get_default_model() -> str:
    """Return default model name for the configured provider."""
    provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if provider == "ollama":
        return os.getenv("OLLAMA_MODEL", "llama3.2")
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_resume_text_from_doc(db: Session, doc_id: str) -> str:
    """
    Fetch all chunks for doc_id and concatenate chunk_text (or snippet) in order.
    Returns empty string if no chunks. Uses idx if present, else created_at.
    """
    # Support both UUID and string doc_id
    doc_id_str = str(doc_id)
    try:
        rows = db.execute(
            text("""
                SELECT COALESCE(chunk_text, snippet, '') AS text
                FROM chunks
                WHERE doc_id::text = :doc_id
                ORDER BY idx ASC NULLS LAST, created_at ASC
                LIMIT 500
            """),
            {"doc_id": doc_id_str},
        ).fetchall()
    except Exception as e:
        _log.warning("get_resume_text_from_doc query failed (idx may be missing): %s", e)
        rows = db.execute(
            text("""
                SELECT COALESCE(chunk_text, snippet, '') AS text
                FROM chunks
                WHERE doc_id::text = :doc_id
                ORDER BY created_at ASC
                LIMIT 500
            """),
            {"doc_id": doc_id_str},
        ).fetchall()
    if not rows:
        return ""
    return "\n\n".join((r[0] or "").strip() for r in rows).strip()


def get_verified_skills_summary(db: Session, user_id: str) -> str:
    """
    Get a short text summary of the user's verified skills from skill_proficiency,
    scoped to documents the user has granted consent for.
    """
    try:
        rows = db.execute(
            text("""
                SELECT DISTINCT sp.skill_id, sp.level, sp.label
                FROM skill_proficiency sp
                JOIN consents c ON c.doc_id = sp.doc_id::text AND c.user_id = :user_id AND c.status = 'granted'
                ORDER BY sp.skill_id
                LIMIT 200
            """),
            {"user_id": user_id},
        ).fetchall()
    except Exception as e:
        _log.warning("get_verified_skills_summary query failed: %s", e)
        return "None (no verified skills yet)."
    if not rows:
        return "None (no verified skills yet)."
    lines = []
    for r in rows:
        skill_id, level, label = r[0], r[1], r[2]
        lines.append(f"- {skill_id}: level {level} ({label or 'N/A'})")
    return "\n".join(lines)


def get_target_role_description(db: Session, target_role_id: Optional[str]) -> str:
    """Get role title and description for the target role, if any."""
    if not target_role_id or not target_role_id.strip():
        return ""
    row = db.execute(
        text("""
            SELECT role_title, description
            FROM roles
            WHERE role_id = :rid
            LIMIT 1
        """),
        {"rid": target_role_id.strip()},
    ).fetchone()
    if not row:
        return ""
    title, desc = row[0] or "", row[1] or ""
    if desc:
        return f"{title}\n{desc}"
    return title


@functools.lru_cache(maxsize=1)
def load_rubric() -> Dict[str, Any]:
    """Load resume rubric JSON from packages/prompts (cached)."""
    path = PROMPTS_DIR / "resume_rubric_v1.json"
    if not path.exists():
        raise FileNotFoundError(f"Rubric not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def load_scoring_prompt() -> str:
    """Load scoring system prompt template (cached)."""
    path = PROMPTS_DIR / "resume_scoring_v1.txt"
    if not path.exists():
        raise FileNotFoundError(f"Scoring prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _validate_scores(scores: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate that scores has the required dimension keys and each has score (0-100) and comment.
    Returns the same dict if valid; raises ValueError if invalid.
    """
    required = ["impact", "relevance", "structure", "language", "skills_presentation", "ats"]
    for k in required:
        if k not in scores:
            raise ValueError(f"Missing dimension: {k}")
        v = scores[k]
        if not isinstance(v, dict):
            raise ValueError(f"Dimension {k} must be an object")
        if "score" not in v:
            raise ValueError(f"Dimension {k} missing 'score'")
        s = v["score"]
        if not isinstance(s, (int, float)) or s < 0 or s > 100:
            raise ValueError(f"Dimension {k} score must be 0-100, got {s}")
        if "comment" not in v:
            v["comment"] = ""
    return scores


def _compute_weighted_total(scores: Dict[str, Any], rubric: Dict[str, Any]) -> float:
    """Compute weighted total from rubric weights."""
    weights = {}
    for dim in rubric.get("dimensions", []):
        weights[dim["id"]] = float(dim.get("weight", 0))
    total = 0.0
    for dim_id, data in scores.items():
        if isinstance(data, dict) and "score" in data:
            w = weights.get(dim_id, 0)
            total += w * float(data["score"])
    return round(total, 1)


def score_resume(
    db: Session,
    doc_id: str,
    user_id: str,
    target_role_id: Optional[str] = None,
    resume_text_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Score a resume by doc_id: load rubric + prompt, get resume text from chunks
    (or use resume_text_override if provided), get verified skills and role description,
    call LLM, parse JSON, validate, and return structured scores + total_initial.

    Returns:
        {
            "scores": { "impact": {"score": 72, "comment": "..."}, ... },
            "total": 68.5,
            "rubric_version": "v1"
        }

    Raises:
        ValueError: if resume text too short, no chunks, or LLM output invalid
        RuntimeError: if LLM call fails or times out
    """
    rubric = load_rubric()
    prompt_tpl = load_scoring_prompt()

    resume_text = resume_text_override
    if resume_text is None:
        resume_text = get_resume_text_from_doc(db, doc_id)

    if len((resume_text or "").strip()) < MIN_RESUME_LENGTH:
        raise ValueError("resume_too_short")

    verified_skills = get_verified_skills_summary(db, user_id)
    target_role_desc = get_target_role_description(db, target_role_id)

    user_message = (
        prompt_tpl
        .replace("{rubric_json}", json.dumps(rubric, ensure_ascii=False, indent=2))
        .replace("{verified_skills}", verified_skills)
        .replace("{target_role_description}", target_role_desc or "(Not specified)")
        .replace("{resume_text}", resume_text[:30000])
    )

    generate = _get_llm_generate()
    model = _get_default_model()

    # Use deterministic seed (hash of resume content) for scoring stability
    import hashlib
    content_hash = hashlib.md5(resume_text.encode("utf-8", errors="replace")).hexdigest()
    deterministic_seed = int(content_hash[:8], 16)

    try:
        raw = generate(
            model=model,
            prompt=user_message,
            temperature=0.0,
            timeout_s=SCORING_TIMEOUT,
            seed=deterministic_seed,
        )
    except TypeError:
        # Fallback for LLM clients that don't support `seed`
        raw = generate(
            model=model,
            prompt=user_message,
            temperature=0.0,
            timeout_s=SCORING_TIMEOUT,
        )
    except Exception as e:
        _log.exception("LLM scoring call failed")
        raise RuntimeError(f"LLM scoring failed: {e}") from e

    if not (raw and raw.strip()):
        raise ValueError("llm_parse_error")

    # Strip markdown code fence if present
    text_clean = raw.strip()
    if text_clean.startswith("```"):
        lines = text_clean.split("\n")
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text_clean = "\n".join(lines)

    try:
        scores = json.loads(text_clean)
    except json.JSONDecodeError as e:
        _log.warning("LLM output not valid JSON: %s", e)
        raise ValueError("llm_parse_error") from e

    if not isinstance(scores, dict):
        raise ValueError("llm_parse_error")

    try:
        scores = _validate_scores(scores)
    except ValueError as e:
        raise ValueError("llm_parse_error") from e
    total = _compute_weighted_total(scores, rubric)

    return {
        "scores": scores,
        "total": total,
        "rubric_version": rubric.get("version", "v1"),
    }
