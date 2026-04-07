from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List


def _tokens(text: str) -> Counter:
    toks = re.findall(r"[a-z0-9+#./-]{2,}|[\u4e00-\u9fff]{1,}", (text or "").lower())
    return Counter(toks)


def cosine_similarity(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    inter = set(a.keys()) & set(b.keys())
    num = sum(a[k] * b[k] for k in inter)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return float(num / den) if den > 0 else 0.0


def match_job_skill_semantic(job_text: str, skill_evidence_texts: Iterable[str]) -> Dict[str, float]:
    job_vec = _tokens(job_text)
    scores: List[float] = []
    for text in skill_evidence_texts:
        scores.append(cosine_similarity(job_vec, _tokens(text)))
    if not scores:
        return {"semantic_score": 0.0, "best_similarity": 0.0}
    return {
        "semantic_score": round(sum(scores) / len(scores), 4),
        "best_similarity": round(max(scores), 4),
    }
