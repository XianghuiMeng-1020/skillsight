"""
Embeddings module for SkillSight.
Uses sentence-transformers for text embeddings.
Falls back to simple hashing if sentence-transformers is not available.
"""
import hashlib
import threading
import warnings

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 384 dims, stable baseline
_model = None
_use_fallback = False
_model_lock = threading.Lock()


def get_model():
    """Lazy load the sentence transformer model (thread-safe)."""
    global _model, _use_fallback

    if _use_fallback:
        return None

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model
        if _use_fallback:
            return None
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(MODEL_NAME)
        except ImportError:
            warnings.warn("sentence-transformers not available, using fallback embeddings")
            _use_fallback = True
            return None
        except Exception as e:
            warnings.warn(f"Failed to load sentence-transformers: {e}, using fallback")
            _use_fallback = True
            return None

    return _model


def _fallback_embed(text: str, dim: int = 384) -> list[float]:
    """Simple hash-based fallback embedding."""
    # Create a deterministic embedding from text hash
    h = hashlib.sha256(text.encode()).hexdigest()
    # Convert hex to list of floats normalized to [-1, 1]
    result = []
    for i in range(0, min(len(h), dim * 2), 2):
        byte_val = int(h[i:i+2], 16)
        result.append((byte_val - 128) / 128.0)
    # Pad or truncate to dim
    while len(result) < dim:
        result.append(0.0)
    return result[:dim]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts.
    Uses sentence-transformers if available, otherwise falls back to hash-based embeddings.
    """
    m = get_model()
    
    if m is None:
        # Fallback mode
        return [_fallback_embed(t) for t in texts]
    
    vecs = m.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def emb_dim() -> int:
    """Return the embedding dimension."""
    return 384  # Fixed dimension for consistency
