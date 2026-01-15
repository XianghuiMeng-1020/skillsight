from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 384 dims, stable baseline
_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model

def embed_texts(texts: list[str]) -> list[list[float]]:
    m = get_model()
    vecs = m.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]

def emb_dim() -> int:
    return len(embed_texts(["test"])[0])
