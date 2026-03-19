"""
Embeddings module for SkillSight.
Uses OpenAI text-embedding-3-small API (production).
Falls back to deterministic hash-based embeddings when OPENAI_API_KEY is unset.
"""
import hashlib
import os
import warnings
from typing import List

_openai_client = None

OPENAI_EMB_MODEL = "text-embedding-3-small"
OPENAI_EMB_DIM = 384


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


def _fallback_embed(text: str, dim: int = OPENAI_EMB_DIM) -> List[float]:
    """Deterministic hash-based fallback when OpenAI is unavailable."""
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
    Priority: OpenAI API > hash fallback.
    """
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
            warnings.warn(f"OpenAI embeddings failed: {e}, using hash fallback")

    return [_fallback_embed(t) for t in texts]


def emb_dim() -> int:
    """Return the embedding dimension."""
    return OPENAI_EMB_DIM
