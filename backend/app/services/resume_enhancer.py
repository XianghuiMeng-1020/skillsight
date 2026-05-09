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
_BACKEND_DIR = Path(__file__).resolve().parents[2]
PROMPTS_DIR = _BACKEND_DIR / "prompts" if (_BACKEND_DIR / "prompts").exists() else REPO_ROOT / "packages" / "prompts"

_log = logging.getLogger(__name__)

SUGGEST_TIMEOUT = 120
VALID_DIMENSIONS = {"impact", "relevance", "structure", "language", "skills_presentation", "ats"}
VALID_PRIORITIES = {"high", "medium", "low"}

# Regex patterns that signal a fabricated strong claim if not found in original text
import re as _re
_FABRICATED_CLAIM_RE = _re.compile(
    r"""
    (?:
        \b\d{1,3}(?:\.\d+)?\s*%           # percentages: 35%, 12.5%
        | \$\d[\d,]*                        # dollar amounts: $50,000
        | \b\d{2,}[xX]\b                    # multipliers: 10x, 3X
        | \b\d+\s*(?:times|fold)\b          # "3 times", "4-fold"
        | \b(?:increased|reduced|improved|saved|grew|cut|boosted)\s+by\s+\d  # "improved by 30"
    )
    """,
    _re.VERBOSE | _re.IGNORECASE,
)


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


def load_suggest_prompt(lang: str = "en") -> str:
    fname = "resume_suggest_zh_v1.txt" if lang == "zh" else "resume_suggest_v1.txt"
    path = PROMPTS_DIR / fname
    if not path.exists():
        # fallback to English
        path = PROMPTS_DIR / "resume_suggest_v1.txt"
    if not path.exists():
        raise FileNotFoundError(f"Suggest prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _is_cjk_heavy(text: str, threshold: float = 0.15) -> bool:
    """Return True if >15 % of chars are CJK ideographs."""
    if not text:
        return False
    cjk = sum(
        1 for ch in text
        if "\u4e00" <= ch <= "\u9fff"
        or "\u3400" <= ch <= "\u4dbf"
        or "\uf900" <= ch <= "\ufaff"
    )
    return cjk / len(text) >= threshold


def _has_fabricated_claim(suggested: str, original_resume: str) -> bool:
    """Return True if *suggested* introduces a quantitative claim absent from the resume."""
    for m in _FABRICATED_CLAIM_RE.finditer(suggested):
        claim = m.group(0).strip()
        if claim.lower() not in original_resume.lower():
            return True
    return False


def _validate_suggestion(item: Any, index: int, resume_text: str = "") -> Dict[str, Any]:
    """Validate one suggestion item; return as dict with keys expected by DB (original_text, suggested_text, explanation).

    Server-side anchor & fabrication checks:
    - original must appear verbatim in resume_text (if provided).
    - suggested must not introduce quantitative claims absent from the resume.
    Raises ValueError to indicate the suggestion should be discarded.
    """
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

    if resume_text and original:
        if original not in resume_text:
            _log.warning(
                "anchor_check: suggestion %d 'original' not found verbatim in resume; discarding. sample=%r",
                index,
                original[:100],
            )
            raise ValueError("anchor_not_found")

    if resume_text and suggested and _has_fabricated_claim(suggested, resume_text):
        _log.warning(
            "anchor_check: suggestion %d 'suggested' introduces fabricated claim; discarding. sample=%r",
            index,
            suggested[:150],
        )
        raise ValueError("fabricated_claim")

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
    lang = "zh" if _is_cjk_heavy(resume_text or "") else "en"
    prompt_tpl = load_suggest_prompt(lang=lang)
    if lang == "zh":
        _log.info("generate_suggestions: CJK-heavy resume — using Chinese suggest prompt")
    verified_skills = get_verified_skills_summary(db, user_id)
    target_role_desc = get_target_role_description(db, target_role_id)

    user_message = (
        prompt_tpl
        .replace("{scoring_json}", json.dumps(scoring_json, ensure_ascii=False, indent=2))
        .replace("{verified_skills}", verified_skills)
        .replace("{target_role_description}", target_role_desc or "(Not specified)")
        .replace("{resume_text}", (resume_text or "")[:30000])
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
    discarded_anchors = 0
    discarded_fabricated = 0
    for i, item in enumerate(data[:50]):
        try:
            out.append(_validate_suggestion(item, i, resume_text=resume_text or ""))
        except ValueError as e:
            if str(e) == "anchor_not_found":
                discarded_anchors += 1
            elif str(e) == "fabricated_claim":
                discarded_fabricated += 1
            continue
    if discarded_anchors or discarded_fabricated:
        _log.info(
            "generate_suggestions: discarded anchor_not_found=%d fabricated_claim=%d kept=%d",
            discarded_anchors,
            discarded_fabricated,
            len(out),
        )
    return out
