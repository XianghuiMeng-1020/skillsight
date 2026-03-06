"""
Embeddings module for SkillSight.
Uses OpenAI embeddings API when OPENAI_API_KEY is set (production).
Falls back to sentence-transformers locally, then to hash-based embeddings.
"""
import hashlib
import os
import threading
import warnings
from typing import List

_openai_client = None
_st_model = None
_use_fallback = False
_lock = threading.Lock()

OPENAI_EMB_MODEL = "text-embedding-3-small"
OPENAI_EMB_DIM = 384
ST_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _get_openai_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import openai
        _openai_client = openai.OpenAI(api_key=api_key)
        return _openai_client
    except ImportError:
        return None


def _get_st_model():
    global _st_model, _use_fallback
    if _use_fallback:
        return None
    if _st_model is not None:
        return _st_model
    with _lock:
        if _st_model is not None:
            return _st_model
        if _use_fallback:
            return None
        try:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer(ST_MODEL_NAME)
        except (ImportError, Exception) as e:
            warnings.warn(f"sentence-transformers unavailable: {e}, will try OpenAI or fallback")
            _use_fallback = True
            return None
    return _st_model


def _fallback_embed(text: str, dim: int = OPENAI_EMB_DIM) -> List[float]:
    """Simple hash-based fallback embedding."""
    h = hashlib.sha256(text.encode()).hexdigest()
    result = []
    for i in range(0, min(len(h), dim * 2), 2):
        byte_val = int(h[i:i+2], 16)
        result.append((byte_val - 128) / 128.0)
    while len(result) < dim:
        result.append(0.0)
    return result[:dim]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts.
    Priority: OpenAI API > sentence-transformers > hash fallback.
    """
    # 1. Try OpenAI (cheap, fast, no memory)
    client = _get_openai_client()
    if client is not None:
        try:
            resp = client.embeddings.create(
                model=OPENAI_EMB_MODEL,
                input=texts,
                dimensions=OPENAI_EMB_DIM,
            )
            return [item.embedding for item in resp.data]
        except Exception as e:
            warnings.warn(f"OpenAI embeddings failed: {e}, trying fallbacks")

    # 2. Try sentence-transformers (local, uses memory)
    m = _get_st_model()
    if m is not None:
        vecs = m.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]

    # 3. Hash fallback
    return [_fallback_embed(t) for t in texts]


def emb_dim() -> int:
    """Return the embedding dimension."""
    return OPENAI_EMB_DIM
