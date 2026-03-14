"""
Resume enhancer service: generate actionable improvement suggestions from scoring results
using LLM. Uses same verified-skills and target-role helpers as resume_scorer.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.services.resume_scorer import (
    get_resume_text_from_doc,
    get_target_role_description,
    get_verified_skills_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "packages" / "prompts"

_log = logging.getLogger(__name__)

SUGGEST_TIMEOUT = 120
VALID_DIMENSIONS = {"impact", "relevance", "structure", "language", "skills_presentation", "ats"}
VALID_PRIORITIES = {"high", "medium", "low"}


def _get_llm_generate():
    """Return the configured LLM generate function."""
    import os
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
            raise RuntimeError("No LLM client available")


def _get_default_model() -> str:
    import os
    provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if provider == "ollama":
        return os.getenv("OLLAMA_MODEL", "llama3.2")
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def load_suggest_prompt() -> str:
    path = PROMPTS_DIR / "resume_suggest_v1.txt"
    if not path.exists():
        raise FileNotFoundError(f"Suggest prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _validate_suggestion(item: Any, index: int) -> Dict[str, Any]:
    """Validate one suggestion item; return as dict with keys expected by DB (original_text, suggested_text, explanation)."""
    if not isinstance(item, dict):
        raise ValueError("llm_parse_error")
    dimension = item.get("dimension") or ""
    if dimension not in VALID_DIMENSIONS:
        dimension = "language"  # fallback
    priority = (item.get("priority") or "medium").lower()
    if priority not in VALID_PRIORITIES:
        priority = "medium"
    section = (item.get("section") or "").strip()
    original = (item.get("original") or "").strip()
    suggested = (item.get("suggested") or "").strip()
    why = (item.get("why") or "").strip()
    return {
        "dimension": dimension,
        "section": section[:500] if section else None,
        "original_text": original[:10000] if original else None,
        "suggested_text": suggested[:10000] if suggested else None,
        "explanation": why[:2000] if why else None,
        "priority": priority,
    }


def generate_suggestions(
    db: Session,
    user_id: str,
    resume_text: str,
    scoring_json: Dict[str, Any],
    target_role_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Generate improvement suggestions from scoring results and resume text.
    Returns list of dicts with keys: dimension, section, original_text, suggested_text, explanation, priority.
    """
    prompt_tpl = load_suggest_prompt()
    verified_skills = get_verified_skills_summary(db, user_id)
    target_role_desc = get_target_role_description(db, target_role_id)

    user_message = prompt_tpl.format(
        scoring_json=json.dumps(scoring_json, ensure_ascii=False, indent=2),
        verified_skills=verified_skills,
        target_role_description=target_role_desc or "(Not specified)",
        resume_text=(resume_text or "")[:30000],
    )

    generate = _get_llm_generate()
    model = _get_default_model()

    try:
        raw = generate(
            model=model,
            prompt=user_message,
            temperature=0.3,
            timeout_s=SUGGEST_TIMEOUT,
        )
    except Exception as e:
        _log.exception("LLM suggest call failed")
        raise RuntimeError(f"LLM suggestions failed: {e}") from e

    if not (raw and raw.strip()):
        raise ValueError("llm_parse_error")

    text_clean = raw.strip()
    if text_clean.startswith("```"):
        lines = text_clean.split("\n")
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text_clean = "\n".join(lines)

    try:
        data = json.loads(text_clean)
    except json.JSONDecodeError:
        raise ValueError("llm_parse_error")

    if not isinstance(data, list):
        raise ValueError("llm_parse_error")

    out = []
    for i, item in enumerate(data[:50]):
        try:
            out.append(_validate_suggestion(item, i))
        except ValueError:
            continue
    return out
