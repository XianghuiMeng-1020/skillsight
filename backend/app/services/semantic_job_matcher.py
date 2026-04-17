"""Lightweight TF-IDF semantic matcher.

Upgraded over the previous bag-of-words version:

* **IDF weighting** down-weights common stop-tokens (the, and, with, …)
  that dominated cosine similarity in the BoW baseline.
* **Stop word filter** excludes very high-frequency English/Chinese
  function words.
* **Corpus-aware ranking** (``rank_jobs_for_skills``) returns the most
  semantically aligned jobs for a set of student skill names, used by
  the dashboard to pick "next best to assess" candidates without
  resorting to embeddings.

Backward compatibility: ``match_job_skill_semantic`` keeps the same
signature/return shape but now uses TF-IDF cosine internally.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence


_TOKEN_RE = re.compile(r"[a-z0-9+#./\-]{2,}|[\u4e00-\u9fff]{1,}")

# Conservative stop list — only obviously content-free tokens.  We do
# NOT filter domain words like "data" or "model" because they carry
# meaningful signal in our context.
_STOP_WORDS = {
    "the", "and", "for", "with", "are", "you", "your", "our", "this",
    "that", "from", "have", "has", "will", "would", "should", "into",
    "their", "they", "them", "but", "not", "all", "any", "can", "may",
    "use", "using", "used", "able", "etc", "ext", "via", "about",
    "across", "such", "also", "more", "most", "much", "many", "some",
    "few", "one", "two", "three",
    "的", "了", "是", "在", "和", "或", "及", "与", "对", "为",
}


def _tokens(text: str) -> List[str]:
    raw = _TOKEN_RE.findall((text or "").lower())
    return [t for t in raw if t not in _STOP_WORDS]


def _tf(text: str) -> Counter:
    return Counter(_tokens(text))


def compute_idf(corpus: Sequence[str]) -> Dict[str, float]:
    """Standard smoothed IDF over a small corpus.  Pure function."""
    n = max(1, len(corpus))
    df: Counter = Counter()
    for doc in corpus:
        for tok in set(_tokens(doc)):
            df[tok] += 1
    # Smoothed IDF; never zero so common terms still contribute a hair.
    return {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}


def _tfidf_vec(text: str, idf: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    tf = _tf(text)
    if not tf:
        return {}
    if idf is None:
        # Without an IDF, fall back to plain TF (= BoW).
        return {t: float(c) for t, c in tf.items()}
    return {t: float(c) * float(idf.get(t, 1.0)) for t, c in tf.items()}


def cosine_similarity(a, b) -> float:
    """Cosine similarity over either Counter or {token: weight} dicts."""
    if not a or not b:
        return 0.0
    if isinstance(a, Counter):
        a_dict = {k: float(v) for k, v in a.items()}
    else:
        a_dict = a
    if isinstance(b, Counter):
        b_dict = {k: float(v) for k, v in b.items()}
    else:
        b_dict = b
    inter = set(a_dict.keys()) & set(b_dict.keys())
    num = sum(a_dict[k] * b_dict[k] for k in inter)
    den_a = math.sqrt(sum(v * v for v in a_dict.values()))
    den_b = math.sqrt(sum(v * v for v in b_dict.values()))
    den = den_a * den_b
    return float(num / den) if den > 0 else 0.0


def match_job_skill_semantic(
    job_text: str,
    skill_evidence_texts: Iterable[str],
    idf: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """Average / best cosine of skill evidence vs. job text.

    When ``idf`` is provided (recommended), uses TF-IDF.  Otherwise
    behaves like the previous BoW implementation.
    """
    skill_texts = list(skill_evidence_texts)
    # Build IDF on the fly from job text + evidence if not provided.
    if idf is None and (job_text or skill_texts):
        idf = compute_idf([job_text or ""] + skill_texts)
    job_vec = _tfidf_vec(job_text, idf)
    scores: List[float] = []
    for txt in skill_texts:
        scores.append(cosine_similarity(job_vec, _tfidf_vec(txt, idf)))
    if not scores:
        return {"semantic_score": 0.0, "best_similarity": 0.0}
    return {
        "semantic_score": round(sum(scores) / len(scores), 4),
        "best_similarity": round(max(scores), 4),
    }


def rank_jobs_for_skills(
    skill_names: Sequence[str],
    job_texts: Sequence[str],
    *,
    top_k: int = 10,
) -> List[Dict[str, float]]:
    """Rank job descriptions by TF-IDF cosine similarity to a profile of
    skill names.  Returns ``[{"index": i, "score": s}, ...]`` sorted
    descending.  Pure function — fast, no external models.
    """
    if not skill_names or not job_texts:
        return []
    profile_text = " ".join(skill_names)
    idf = compute_idf([profile_text] + list(job_texts))
    profile_vec = _tfidf_vec(profile_text, idf)
    out: List[Dict[str, float]] = []
    for i, jt in enumerate(job_texts):
        out.append(
            {
                "index": i,
                "score": round(cosine_similarity(profile_vec, _tfidf_vec(jt, idf)), 4),
            }
        )
    out.sort(key=lambda r: r["score"], reverse=True)
    return out[:top_k]


__all__ = [
    "compute_idf",
    "cosine_similarity",
    "match_job_skill_semantic",
    "rank_jobs_for_skills",
]
