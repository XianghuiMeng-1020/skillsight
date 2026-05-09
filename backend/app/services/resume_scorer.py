"""
Resume scoring service: load rubric + prompt, get resume text from chunks,
call LLM, return structured scores and weighted total.

Long-resume strategy:
  When a resume exceeds SEGMENT_CHAR_LIMIT the text is split into segments
  that each fit within the LLM context window.  Each segment is scored
  independently and the final scores are merged by taking the weighted
  average (weighted by segment length) for all numeric dimensions.
  This prevents the silent truncation that previously discarded the second
  half of long resumes (projects, publications, etc.).
"""
from __future__ import annotations

import functools
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = Path(__file__).resolve().parents[2]
PROMPTS_DIR = _BACKEND_DIR / "prompts" if (_BACKEND_DIR / "prompts").exists() else REPO_ROOT / "packages" / "prompts"
SCHEMAS_DIR = REPO_ROOT / "packages" / "schemas"

_log = logging.getLogger(__name__)

# Minimum resume length (chars) to avoid scoring empty or tiny content
MIN_RESUME_LENGTH = 100

# Characters per LLM segment (leaves room for prompt + rubric ≈ 4–5K tokens)
SEGMENT_CHAR_LIMIT: int = int(os.getenv("RESUME_SEGMENT_CHARS", "12000"))

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
    total_rows = 0
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
        total_rows = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE doc_id::text = :doc_id"),
            {"doc_id": doc_id_str},
        ).scalar() or 0
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
        total_rows = len(rows)
    if not rows:
        return ""
    # Single newlines between chunks avoid artificial double gaps that fragment sections in parse_resume.
    parts = [(r[0] or "").strip() for r in rows if (r[0] or "").strip()]
    if total_rows > 500:
        _log.warning(
            "get_resume_text_from_doc truncated chunks doc_id=%s total=%s used=500",
            doc_id_str,
            total_rows,
        )
    return "\n".join(parts).strip()


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


@functools.lru_cache(maxsize=1)
def load_scoring_prompt_zh() -> str:
    """Load Chinese scoring prompt (cached); falls back to English if not found."""
    path = PROMPTS_DIR / "resume_scoring_zh_v1.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return load_scoring_prompt()


@functools.lru_cache(maxsize=1)
def load_rubric_zh() -> Dict[str, Any]:
    """Load Chinese rubric JSON (cached); falls back to English rubric if not found."""
    path = PROMPTS_DIR / "resume_rubric_zh_v1.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return load_rubric()


def _is_cjk_heavy(text: str, threshold: float = 0.15) -> bool:
    """Return True if >15 % of characters in *text* are CJK (Chinese/Japanese/Korean)."""
    if not text:
        return False
    cjk_count = sum(
        1 for ch in text
        if "\u4e00" <= ch <= "\u9fff"  # CJK Unified
        or "\u3400" <= ch <= "\u4dbf"  # CJK Extension A
        or "\uf900" <= ch <= "\ufaff"  # CJK Compatibility
    )
    return cjk_count / len(text) >= threshold


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
    return round(total, 2)


def _split_resume_into_segments(text: str, limit: int = SEGMENT_CHAR_LIMIT) -> List[str]:
    """Split resume text into segments that each fit within *limit* characters.

    Segments are broken on paragraph boundaries (double newlines) so that
    logical blocks (experience entries, project descriptions) stay intact.
    Each segment is labelled with a header so the LLM knows it is reviewing
    a portion of a larger document.
    """
    if len(text) <= limit:
        return [text]

    paragraphs = text.split("\n\n")
    segments: List[str] = []
    current_parts: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2  # +2 for the \n\n
        if current_len + para_len > limit and current_parts:
            segments.append("\n\n".join(current_parts))
            current_parts = []
            current_len = 0
        current_parts.append(para)
        current_len += para_len

    if current_parts:
        segments.append("\n\n".join(current_parts))

    return segments or [text]


def _merge_segment_scores(
    segment_results: List[Tuple[Dict[str, Any], int]],
) -> Dict[str, Any]:
    """Merge per-segment score dicts into one by weighted-averaging scores.

    *segment_results* is a list of (scores_dict, segment_char_length) tuples.
    The comment from the **first** segment (which typically contains the name /
    summary / most recent experience) is kept for each dimension as it is most
    representative.
    """
    if not segment_results:
        return {}
    if len(segment_results) == 1:
        return segment_results[0][0]

    total_weight = sum(w for _, w in segment_results)
    dims = list(segment_results[0][0].keys())
    merged: Dict[str, Any] = {}
    for dim in dims:
        weighted_score = 0.0
        first_comment = ""
        for scores, weight in segment_results:
            v = scores.get(dim, {})
            if isinstance(v, dict):
                weighted_score += float(v.get("score", 0)) * weight
                if not first_comment:
                    first_comment = str(v.get("comment", ""))
        merged[dim] = {
            "score": round(weighted_score / total_weight, 1),
            "comment": first_comment,
        }
    return merged


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
    resume_text = resume_text_override
    if resume_text is None:
        resume_text = get_resume_text_from_doc(db, doc_id)

    if len((resume_text or "").strip()) < MIN_RESUME_LENGTH:
        raise ValueError("resume_too_short")

    # Auto-select language of prompt/rubric based on resume content
    if _is_cjk_heavy(resume_text):
        _log.info("score_resume: CJK-heavy resume detected — using Chinese prompt/rubric doc_id=%s", doc_id)
        rubric = load_rubric_zh()
        prompt_tpl = load_scoring_prompt_zh()
    else:
        rubric = load_rubric()
        prompt_tpl = load_scoring_prompt()

    verified_skills = get_verified_skills_summary(db, user_id)
    target_role_desc = get_target_role_description(db, target_role_id)

    generate = _get_llm_generate()
    model = _get_default_model()

    # Use deterministic seed (hash of resume content) for scoring stability
    import hashlib
    content_hash = hashlib.md5(resume_text.encode("utf-8", errors="replace")).hexdigest()
    deterministic_seed = int(content_hash[:8], 16)

    rubric_json_str = json.dumps(rubric, ensure_ascii=False, indent=2)

    def _score_single_segment(seg_text: str, seg_label: str = "") -> Dict[str, Any]:
        """Call LLM once for one segment; return validated score dict."""
        display = seg_text
        if seg_label:
            display = f"[PARTIAL RESUME — {seg_label}]\n\n{seg_text}"
        user_message = (
            prompt_tpl
            .replace("{rubric_json}", rubric_json_str)
            .replace("{verified_skills}", verified_skills)
            .replace("{target_role_description}", target_role_desc or "(Not specified)")
            .replace("{resume_text}", display)
        )
        try:
            raw = generate(
                model=model,
                prompt=user_message,
                temperature=0.0,
                timeout_s=SCORING_TIMEOUT,
                seed=deterministic_seed,
            )
        except TypeError:
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

        text_clean = raw.strip()
        if text_clean.startswith("```"):
            lines = text_clean.split("\n")
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text_clean = "\n".join(lines)

        try:
            seg_scores = json.loads(text_clean)
        except json.JSONDecodeError as e:
            _log.warning("LLM output not valid JSON: %s", e)
            raise ValueError("llm_parse_error") from e

        if not isinstance(seg_scores, dict):
            raise ValueError("llm_parse_error")

        try:
            seg_scores = _validate_scores(seg_scores)
        except ValueError as e:
            raise ValueError("llm_parse_error") from e

        return seg_scores

    # ── Segmented scoring for long resumes ────────────────────────────────────
    segments = _split_resume_into_segments(resume_text, limit=SEGMENT_CHAR_LIMIT)
    if len(segments) == 1:
        scores = _score_single_segment(segments[0])
    else:
        _log.info(
            "score_resume: long resume split into %d segments doc_id=%s total_chars=%d",
            len(segments),
            doc_id,
            len(resume_text),
        )
        segment_results = []
        for i, seg in enumerate(segments):
            label = f"segment {i + 1} of {len(segments)}"
            seg_scores = _score_single_segment(seg, seg_label=label)
            segment_results.append((seg_scores, len(seg)))
        scores = _merge_segment_scores(segment_results)
        try:
            scores = _validate_scores(scores)
        except ValueError as e:
            raise ValueError("llm_parse_error") from e

    total = _compute_weighted_total(scores, rubric)

    return {
        "scores": scores,
        "total": total,
        "rubric_version": rubric.get("version", "v1"),
        "segments_scored": len(segments),
    }
