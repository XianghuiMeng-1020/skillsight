"""
AI Assessment Routes for SkillSight
- POST /ai/demonstration: LLM-based demonstration classification
- POST /ai/proficiency: LLM-based proficiency level assessment
- POST /ai/transcribe: Audio transcription using Whisper
- POST /ai/analyze-writing: AI-powered writing analysis
- POST /ai/learning-path: Personalized learning path recommendations
"""
import json
import re
import uuid
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.deps import get_db
from backend.app.db.session import engine
from backend.app.deps import check_doc_access
from backend.app.security import Identity, require_auth

# Lazy imports for optional dependencies
def _get_llm():
    """Return generate(model, prompt, temperature, timeout_s) -> str. Prefer OpenAI when LLM_PROVIDER=openai."""
    provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if provider == "ollama":
        try:
            from backend.app.ollama_client import ollama_generate
            return ollama_generate
        except ImportError:
            return None
    # default: openai
    try:
        from backend.app.openai_client import openai_generate
        return openai_generate
    except ImportError:
        try:
            from backend.app.ollama_client import ollama_generate
            return ollama_generate
        except ImportError:
            return None

def _get_embeddings():
    try:
        from backend.app.embeddings import embed_texts
        return embed_texts
    except ImportError:
        return None

def _get_vector_store():
    try:
        from backend.app.vector_store import get_client, search
        return get_client, search
    except ImportError:
        return None, None

def _get_qm():
    try:
        from qdrant_client.http import models as qm
        return qm
    except ImportError:
        return None

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(require_auth)])

# Load prompt templates
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "packages" / "prompts"

def _load_prompt(name: str) -> str:
    p = PROMPTS_DIR / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt template not found: {p}")

DEMONSTRATION_PROMPT = _load_prompt("demonstration_v1.txt")
PROFICIENCY_PROMPT = _load_prompt("proficiency_v1.txt")

# Default LLM model (OpenAI or Ollama depending on LLM_PROVIDER)
_provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini") if _provider == "openai" else os.getenv("OLLAMA_MODEL", "deepseek-r1:14b")
MAX_AUDIO_UPLOAD_BYTES = int(os.getenv("MAX_AUDIO_UPLOAD_BYTES", str(50 * 1024 * 1024)))


def _now_utc():
    return datetime.now(timezone.utc)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try to extract from markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    # Try to find JSON object in text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


def _get_skill(db: Session, skill_id: str) -> Optional[Dict[str, Any]]:
    """Get skill with rubric from DB."""
    sql = text("""
        SELECT skill_id, canonical_name, definition, evidence_rules, level_rubric_json, version, source
        FROM skills
        WHERE skill_id = :skill_id
        LIMIT 1
    """)
    row = db.execute(sql, {"skill_id": skill_id}).mappings().first()
    if not row:
        return None
    d = dict(row)
    # Parse rubric JSON
    rubric = d.get("level_rubric_json")
    if rubric and isinstance(rubric, str):
        try:
            d["level_rubric"] = json.loads(rubric)
        except Exception:
            d["level_rubric"] = {}
    elif isinstance(rubric, dict):
        d["level_rubric"] = rubric
    else:
        d["level_rubric"] = {}
    return d


def _get_chunks_for_doc(db: Session, doc_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Get all chunks for a document."""
    sql = text("""
        SELECT chunk_id::text as chunk_id, doc_id::text as doc_id, idx, char_start, char_end, 
               snippet, quote_hash, chunk_text, section_path, page_start, page_end
        FROM chunks
        WHERE doc_id = :doc_id
        ORDER BY idx ASC
        LIMIT :limit
    """)
    rows = db.execute(sql, {"doc_id": doc_id, "limit": limit}).mappings().all()
    return [dict(r) for r in rows]


def _search_relevant_chunks(skill_text: str, doc_id: str, k: int = 5, min_score: float = 0.1) -> List[Dict[str, Any]]:
    """Use vector search to find relevant chunks for a skill in a document."""
    get_client, search = _get_vector_store()
    embed_texts = _get_embeddings()
    qm = _get_qm()
    
    if get_client is None or embed_texts is None:
        return []  # Vector search not available
    
    try:
        client = get_client()
        if client is None:
            return []
        query_vec = embed_texts([skill_text])[0]
        flt = None
        if qm is not None:
            flt = qm.Filter(
                must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))]
            )
        results = search(client, query_vec, k, flt) if search else []
        chunks = []
        for r in results:
            if r.score >= min_score:
                payload = r.payload or {}
                chunks.append({
                    "chunk_id": payload.get("chunk_id"),
                    "doc_id": payload.get("doc_id"),
                    "snippet": payload.get("snippet", ""),
                    "section_path": payload.get("section_path"),
                    "page_start": payload.get("page_start"),
                    "page_end": payload.get("page_end"),
                    "score": float(r.score),
                })
        return chunks
    except Exception as e:
        # Fallback: return empty if vector search fails
        return []


def _format_evidence_list(chunks: List[Dict[str, Any]]) -> str:
    """Format chunks for prompt injection."""
    lines = []
    for i, ch in enumerate(chunks):
        cid = ch.get("chunk_id", f"chunk_{i}")
        snippet = (ch.get("snippet") or "")[:300]
        section = ch.get("section_path") or ""
        page = ch.get("page_start")
        meta = []
        if section:
            meta.append(f"section={section}")
        if page:
            meta.append(f"page={page}")
        meta_str = ", ".join(meta) if meta else ""
        lines.append(f"[{cid}] ({meta_str})\n{snippet}")
    return "\n\n".join(lines) if lines else "(no evidence chunks provided)"


def _format_rubric_text(rubric: Dict[str, Any]) -> str:
    """Format rubric for prompt injection."""
    if not rubric:
        return "(no rubric provided)"
    
    lines = []
    levels = rubric.get("levels", rubric)
    for level_key in sorted(levels.keys(), key=lambda x: int(x) if x.isdigit() else 999):
        level_data = levels[level_key]
        label = level_data.get("label", f"level_{level_key}")
        criteria = level_data.get("criteria", [])
        lines.append(f"Level {level_key} ({label}):")
        for c in criteria:
            cid = c.get("id", "?")
            ctext = c.get("text", "")
            lines.append(f"  - [{cid}] {ctext}")
    return "\n".join(lines) if lines else "(no rubric provided)"


def _validate_demonstration_output(output: Dict[str, Any], valid_chunk_ids: List[str]) -> Dict[str, Any]:
    """Validate and normalize demonstration output."""
    label = output.get("label", "not_enough_information")
    if label not in ["demonstrated", "mentioned", "not_enough_information"]:
        label = "not_enough_information"
    
    evidence_ids = output.get("evidence_chunk_ids", [])
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    
    # Filter to only valid chunk IDs
    valid_set = set(valid_chunk_ids)
    evidence_ids = [cid for cid in evidence_ids if cid in valid_set]
    
    rationale = output.get("rationale", "")
    refusal_reason = output.get("refusal_reason")
    
    # Enforce refusal rules
    if label == "not_enough_information":
        evidence_ids = []
        if not refusal_reason:
            refusal_reason = "Evidence insufficient or irrelevant to demonstrate this skill."
    else:
        if not evidence_ids:
            # If no valid evidence but claiming demonstrated/mentioned, downgrade to not_enough_information
            label = "not_enough_information"
            refusal_reason = "No valid evidence chunk IDs provided."
    
    return {
        "label": label,
        "evidence_chunk_ids": evidence_ids,
        "rationale": rationale[:500] if rationale else "",
        "refusal_reason": refusal_reason,
    }


def _validate_proficiency_output(output: Dict[str, Any], valid_chunk_ids: List[str], valid_criteria: List[str]) -> Dict[str, Any]:
    """Validate and normalize proficiency output."""
    level = output.get("level", 0)
    if not isinstance(level, int) or level < 0 or level > 3:
        level = 0
    
    label_map = {0: "novice", 1: "developing", 2: "proficient", 3: "advanced"}
    label = output.get("label", label_map.get(level, "novice"))
    if label not in label_map.values():
        label = label_map.get(level, "novice")
    
    evidence_ids = output.get("evidence_chunk_ids", [])
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    valid_set = set(valid_chunk_ids)
    evidence_ids = [cid for cid in evidence_ids if cid in valid_set]
    
    matched_criteria = output.get("matched_criteria", [])
    if not isinstance(matched_criteria, list):
        matched_criteria = []
    if valid_criteria:
        valid_criteria_set = set(valid_criteria)
        matched_criteria = [c for c in matched_criteria if c in valid_criteria_set]
    
    why = output.get("why", "")
    
    # Enforce: if no evidence, level must be 0
    if not evidence_ids and level > 0:
        level = 0
        label = "novice"
    
    return {
        "level": level,
        "label": label,
        "matched_criteria": matched_criteria,
        "evidence_chunk_ids": evidence_ids,
        "why": why[:500] if why else "",
    }


def _extract_all_criteria_ids(rubric: Dict[str, Any]) -> List[str]:
    """Extract all criterion IDs from rubric."""
    ids = []
    if not rubric or not isinstance(rubric, dict):
        return ids
    levels = rubric.get("levels", rubric)
    if not isinstance(levels, dict):
        return ids
    for level_data in levels.values():
        if not isinstance(level_data, dict):
            continue
        criteria = level_data.get("criteria", [])
        if not isinstance(criteria, list):
            continue
        for c in criteria:
            if isinstance(c, dict):
                cid = c.get("id")
                if cid:
                    ids.append(cid)
    return ids


# === Request/Response Models ===

class DemonstrationRequest(BaseModel):
    skill_id: str
    doc_id: str
    k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.2, ge=0.0, le=1.0)
    model: str = Field(default=DEFAULT_MODEL)


class ProficiencyRequest(BaseModel):
    skill_id: str
    doc_id: str
    k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.2, ge=0.0, le=1.0)
    model: str = Field(default=DEFAULT_MODEL)


# === Routes ===

@router.post("/demonstration")
def ai_demonstration(
    req: DemonstrationRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Decision 2: LLM-based demonstration assessment.
    Returns: label (demonstrated/mentioned/not_enough_information), evidence_chunk_ids, rationale, refusal_reason
    """
    started = _now_utc()
    check_doc_access(ident, req.doc_id, db)
    # Get skill
    skill = _get_skill(db, req.skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {req.skill_id}")
    
    # Build skill text for prompt
    skill_text = f"{skill.get('canonical_name', '')} — {skill.get('definition', '')}"
    
    # Get relevant evidence chunks via vector search
    chunks = _search_relevant_chunks(skill_text, req.doc_id, k=req.k, min_score=req.min_score)
    
    # If no chunks from vector search, try DB fallback with more chunks
    if not chunks:
        db_chunks = _get_chunks_for_doc(db, req.doc_id, limit=max(req.k, 20))
        chunks = [{"chunk_id": str(c["chunk_id"]),
                   "snippet": c.get("chunk_text") or c.get("snippet", ""),
                   "section_path": c.get("section_path"), "page_start": c.get("page_start")}
                  for c in db_chunks]
    
    valid_chunk_ids = [c["chunk_id"] for c in chunks if c.get("chunk_id")]
    
    # Format evidence for prompt
    evidence_text = _format_evidence_list(chunks)
    
    # Build prompt
    prompt = DEMONSTRATION_PROMPT.replace("{skill_text}", skill_text).replace("{evidence_list}", evidence_text)
    
    # Call LLM
    llm_generate = _get_llm()
    if llm_generate is None:
        raise HTTPException(status_code=503, detail="LLM service not available")
    
    try:
        raw_response = llm_generate(req.model, prompt, temperature=0.0, timeout_s=120)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM call failed: {type(e).__name__}: {e}")
    
    # Parse response
    parsed = _extract_json(raw_response)
    if not parsed:
        # Return refusal if parse fails
        return {
            "skill_id": req.skill_id,
            "doc_id": req.doc_id,
            "label": "not_enough_information",
            "evidence_chunk_ids": [],
            "rationale": "",
            "refusal_reason": "LLM output could not be parsed as valid JSON.",
            "raw_response": raw_response[:500],
            "model": req.model,
            "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
        }
    
    # Validate
    validated = _validate_demonstration_output(parsed, valid_chunk_ids)

    # Decision 2 B1: reliability for demonstration
    label = validated.get("label", "not_enough_information")
    ev_ids = validated.get("evidence_chunk_ids", [])
    if label == "not_enough_information" or not ev_ids:
        reliability_level = "low"
        reliability_reason = "Insufficient or no valid evidence."
    elif len(ev_ids) >= 2:
        reliability_level = "high"
        reliability_reason = "Multiple evidence chunks support the conclusion."
    else:
        reliability_level = "medium"
        reliability_reason = "Single evidence chunk; consider more evidence for higher confidence."

    return {
        "skill_id": req.skill_id,
        "doc_id": req.doc_id,
        **validated,
        "model": req.model,
        "chunks_considered": len(chunks),
        "reliability": {"level": reliability_level, "reason_codes": [reliability_reason]},
        "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
    }


@router.post("/proficiency")
def ai_proficiency(
    req: ProficiencyRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Decision 3: LLM-based proficiency level assessment using rubric.
    Returns: level (0-3), label, matched_criteria, evidence_chunk_ids, why
    """
    started = _now_utc()
    check_doc_access(ident, req.doc_id, db)
    # Get skill with rubric
    skill = _get_skill(db, req.skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {req.skill_id}")
    
    rubric = skill.get("level_rubric", {})
    
    # Build skill text for prompt
    skill_text = f"{skill.get('canonical_name', '')} — {skill.get('definition', '')}"
    
    # Get relevant evidence chunks
    chunks = _search_relevant_chunks(skill_text, req.doc_id, k=req.k, min_score=req.min_score)
    
    # Fallback to DB if vector search empty
    if not chunks:
        db_chunks = _get_chunks_for_doc(db, req.doc_id, limit=max(req.k, 20))
        chunks = [{"chunk_id": str(c["chunk_id"]),
                   "snippet": c.get("chunk_text") or c.get("snippet", ""),
                   "section_path": c.get("section_path"), "page_start": c.get("page_start")}
                  for c in db_chunks]
    
    valid_chunk_ids = [c["chunk_id"] for c in chunks if c.get("chunk_id")]
    valid_criteria = _extract_all_criteria_ids(rubric)
    
    # Format evidence and rubric
    evidence_text = _format_evidence_list(chunks)
    rubric_text = _format_rubric_text(rubric)
    
    # Build prompt
    prompt = (PROFICIENCY_PROMPT
              .replace("{skill_text}", skill_text)
              .replace("{rubric_text}", rubric_text)
              .replace("{evidence_list}", evidence_text))
    
    # Call LLM
    llm_generate = _get_llm()
    if llm_generate is None:
        raise HTTPException(status_code=503, detail="LLM service not available")
    
    try:
        raw_response = llm_generate(req.model, prompt, temperature=0.0, timeout_s=120)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM call failed: {type(e).__name__}: {e}")
    
    # Parse response
    parsed = _extract_json(raw_response)
    if not parsed:
        return {
            "skill_id": req.skill_id,
            "doc_id": req.doc_id,
            "level": 0,
            "label": "novice",
            "matched_criteria": [],
            "evidence_chunk_ids": [],
            "why": "LLM output could not be parsed as valid JSON.",
            "raw_response": raw_response[:500],
            "model": req.model,
            "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
        }
    
    # Validate
    validated = _validate_proficiency_output(parsed, valid_chunk_ids, valid_criteria)
    
    return {
        "skill_id": req.skill_id,
        "doc_id": req.doc_id,
        **validated,
        "model": req.model,
        "chunks_considered": len(chunks),
        "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
    }


# === Audio Transcription (Whisper) ===

@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Transcribe audio file using OpenAI Whisper.
    Supports: webm, mp3, wav, m4a, ogg
    """
    started = _now_utc()
    
    # Save uploaded file to temp
    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await audio.read(MAX_AUDIO_UPLOAD_BYTES + 1)
        if len(content) > MAX_AUDIO_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large (max {MAX_AUDIO_UPLOAD_BYTES // (1024 * 1024)} MB)",
            )
        tmp.write(content)
        tmp_path = tmp.name
    
    transcript_text = ""
    confidence = 0.9
    language = "zh"
    
    try:
        # Try local Whisper first
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(tmp_path, language="zh")
            transcript_text = result.get("text", "")
            language = result.get("language", "zh")
            # Estimate confidence from segment probabilities
            segments = result.get("segments", [])
            if segments:
                avg_prob = sum(s.get("no_speech_prob", 0) for s in segments) / len(segments)
                confidence = 1.0 - avg_prob
        except ImportError:
            pass
        
        # Try OpenAI Whisper API as fallback
        if not transcript_text:
            try:
                import openai
                with open(tmp_path, "rb") as audio_file:
                    result = openai.Audio.transcribe("whisper-1", audio_file)
                transcript_text = result.get("text", "")
            except Exception:
                pass
        
        # If still no transcript, return mock for demo
        if not transcript_text:
            transcript_text = "[音频转录服务暂不可用。请安装 openai-whisper 或配置 OpenAI API 密钥。]"
            confidence = 0.0
        
        # Get audio duration
        duration = 0.0
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", tmp_path],
                capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
        except Exception:
            pass
        
        return {
            "text": transcript_text,
            "confidence": round(confidence, 3),
            "duration": round(duration, 2),
            "language": language,
            "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
        }
    
    finally:
        # Cleanup temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# === AI Writing Analysis ===

class WritingAnalysisRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=10000)
    prompt: Optional[str] = None


@router.post("/analyze-writing")
def analyze_writing(req: WritingAnalysisRequest) -> Dict[str, Any]:
    """
    Analyze writing quality using AI.
    Returns scores for grammar, content, structure, and style.
    """
    started = _now_utc()
    text = req.text.strip()
    
    # Basic text analysis
    words = text.split()
    sentences = [s.strip() for s in re.split(r'[.!?。！？]', text) if s.strip()]
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    word_count = len(words)
    sentence_count = len(sentences)
    paragraph_count = len(paragraphs)
    avg_sentence_length = word_count / max(sentence_count, 1)
    
    # Grammar analysis (basic rules)
    grammar_issues = []
    
    # Check for double spaces
    double_spaces = re.findall(r'\s{2,}', text)
    for match in double_spaces[:3]:
        pos = text.find(match)
        grammar_issues.append({
            "text": "多余空格",
            "suggestion": "删除重复空格",
            "position": pos,
        })
    
    # Check for repeated punctuation
    repeated_punct = re.findall(r'([.!?,。！？，]{2,})', text)
    for match in repeated_punct[:3]:
        pos = text.find(match)
        grammar_issues.append({
            "text": f"重复标点: {match}",
            "suggestion": "删除重复标点",
            "position": pos,
        })
    
    grammar_score = max(60, 100 - len(grammar_issues) * 10)
    
    # Content score (based on length and variety)
    unique_words = len(set(w.lower() for w in words))
    vocabulary_ratio = unique_words / max(word_count, 1)
    content_score = min(100, int(50 + vocabulary_ratio * 30 + min(word_count / 5, 20)))
    
    # Structure score
    if paragraph_count >= 3 and sentence_count >= 5:
        structure_score = 85
    elif paragraph_count >= 2:
        structure_score = 70
    else:
        structure_score = 55
    
    if sentence_count < 3:
        structure_score -= 15
    
    # Style score
    style_score = 80
    if avg_sentence_length > 30:
        style_score -= 15
    elif avg_sentence_length > 25:
        style_score -= 10
    elif avg_sentence_length < 5:
        style_score -= 10
    
    # Generate suggestions
    content_suggestions = []
    style_suggestions = []
    
    if word_count < 100:
        content_suggestions.append("建议增加更多内容以充分论述观点")
    if word_count < 300 and req.prompt:
        content_suggestions.append("内容较短，可以展开更多细节")
    
    if avg_sentence_length > 25:
        style_suggestions.append("部分句子偏长，考虑拆分以提高可读性")
    if vocabulary_ratio < 0.3:
        style_suggestions.append("词汇多样性较低，尝试使用更多不同的词汇")
    
    # Determine tone
    formal_words = ['因此', '然而', '此外', '综上所述', 'therefore', 'however', 'moreover']
    informal_words = ['啊', '呢', '吧', '哈', 'yeah', 'ok', 'cool']
    
    formal_count = sum(1 for w in formal_words if w in text.lower())
    informal_count = sum(1 for w in informal_words if w in text.lower())
    
    if formal_count > informal_count:
        tone = "正式"
    elif informal_count > formal_count:
        tone = "非正式"
    else:
        tone = "中性"
    
    # Calculate overall score
    overall = int((grammar_score + content_score + structure_score + style_score) / 4)
    
    # Try LLM-based analysis if available
    llm_generate = _get_llm()
    if llm_generate and len(text) >= 50:
        try:
            analysis_prompt = f"""分析以下文本的写作质量，返回JSON格式：
{{
  "grammar_issues": [概述发现的语法问题],
  "content_suggestions": [内容改进建议],
  "style_feedback": "风格评价",
  "overall_comment": "总体评价（1-2句话）"
}}

文本：
{text[:1500]}
"""
            raw_response = llm_generate(DEFAULT_MODEL, analysis_prompt, temperature=0.3, timeout_s=30)
            parsed = _extract_json(raw_response)
            
            if parsed:
                if parsed.get("grammar_issues"):
                    for issue in parsed["grammar_issues"][:3]:
                        if isinstance(issue, str):
                            grammar_issues.append({"text": issue, "suggestion": "", "position": 0})
                if parsed.get("content_suggestions"):
                    content_suggestions.extend(parsed["content_suggestions"][:2])
                if parsed.get("style_feedback"):
                    style_suggestions.append(parsed["style_feedback"])
        except Exception:
            pass  # Fall back to rule-based analysis
    
    return {
        "grammar": {
            "score": grammar_score,
            "issues": grammar_issues[:5],
        },
        "content": {
            "score": content_score,
            "suggestions": content_suggestions[:3],
        },
        "structure": {
            "score": structure_score,
            "feedback": "段落结构合理" if structure_score >= 70 else "建议分成多个段落",
        },
        "style": {
            "score": style_score,
            "tone": tone,
            "suggestions": style_suggestions[:3],
        },
        "overall": overall,
        "stats": {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "paragraph_count": paragraph_count,
            "avg_sentence_length": round(avg_sentence_length, 1),
        },
        "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
    }


# === Learning Path Recommendations ===

class LearningPathRequest(BaseModel):
    skills: List[Dict[str, Any]]  # [{"name": "Python", "level": 2}, ...]
    targetRole: Optional[str] = None


@router.post("/learning-path")
def generate_learning_path(req: LearningPathRequest) -> Dict[str, Any]:
    """
    Generate personalized learning recommendations based on skill gaps.
    """
    started = _now_utc()
    
    # Calculate skill gaps
    skill_gaps = []
    for skill in req.skills:
        name = skill.get("name", "")
        level = skill.get("level", 0)
        target_level = 3  # Default target
        
        if level < target_level:
            skill_gaps.append({
                "skill": name,
                "currentLevel": level,
                "targetLevel": target_level,
                "gap": target_level - level,
            })
    
    # Sort by gap (highest first)
    skill_gaps.sort(key=lambda x: x["gap"], reverse=True)
    
    # Generate recommendations
    recommendations = []
    
    # Predefined course templates
    course_templates = {
        "python": {"title": "Python 进阶课程", "titleEn": "Advanced Python", "type": "course", "hours": 20, "icon": "🐍"},
        "communication": {"title": "商务沟通技巧", "titleEn": "Business Communication", "type": "course", "hours": 15, "icon": "🎙️"},
        "data analysis": {"title": "数据分析实战", "titleEn": "Data Analysis Practice", "type": "project", "hours": 25, "icon": "📊"},
        "machine learning": {"title": "机器学习基础", "titleEn": "ML Fundamentals", "type": "course", "hours": 40, "icon": "🤖"},
        "problem solving": {"title": "算法与问题解决", "titleEn": "Algorithms & Problem Solving", "type": "assessment", "hours": 30, "icon": "🧠"},
        "writing": {"title": "学术写作训练", "titleEn": "Academic Writing", "type": "course", "hours": 15, "icon": "✍️"},
        "leadership": {"title": "领导力培养", "titleEn": "Leadership Development", "type": "course", "hours": 20, "icon": "👥"},
        "project management": {"title": "项目管理实践", "titleEn": "Project Management", "type": "project", "hours": 25, "icon": "📋"},
    }
    
    for i, gap in enumerate(skill_gaps[:5]):
        skill_lower = gap["skill"].lower()
        template = None
        
        # Find matching template
        for key, tmpl in course_templates.items():
            if key in skill_lower or skill_lower in key:
                template = tmpl
                break
        
        if not template:
            template = {
                "title": f"提升 {gap['skill']}",
                "titleEn": f"Improve {gap['skill']}",
                "type": "course",
                "hours": gap["gap"] * 10,
                "icon": "📚",
            }
        
        priority = "high" if gap["gap"] >= 2 else "medium" if gap["gap"] == 1 else "low"
        
        recommendations.append({
            "id": f"rec-{i}",
            "title": template["title"],
            "titleEn": template["titleEn"],
            "description": f"通过系统学习提升您的{gap['skill']}技能，从 Level {gap['currentLevel']} 提升到 Level {gap['targetLevel']}",
            "descriptionEn": f"Improve your {gap['skill']} skills from Level {gap['currentLevel']} to Level {gap['targetLevel']}",
            "type": template["type"],
            "skill": gap["skill"],
            "priority": priority,
            "estimatedHours": template["hours"],
            "icon": template["icon"],
        })
    
    return {
        "recommendations": recommendations,
        "skillGaps": skill_gaps,
        "timing_ms": int((_now_utc() - started).total_seconds() * 1000),
    }
