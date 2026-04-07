from __future__ import annotations

import re
from typing import Dict, List


BLOOM_WEIGHTS: Dict[str, float] = {
    "remember": 0.1,
    "understand": 0.2,
    "apply": 0.4,
    "analyze": 0.6,
    "evaluate": 0.8,
    "create": 1.0,
}


_PATTERNS: Dict[str, List[str]] = {
    "remember": [r"\b(list|define|recall|identify|describe)\b", r"(了解|记住|识别|描述)"],
    "understand": [r"\b(explain|summari[sz]e|interpret|discuss)\b", r"(解释|总结|理解|阐述)"],
    "apply": [r"\b(use|implement|build|develop|execute)\b", r"(实现|应用|开发|搭建|执行)"],
    "analyze": [r"\b(analy[sz]e|compare|diagnose|investigate)\b", r"(分析|对比|诊断|研究)"],
    "evaluate": [r"\b(evaluate|review|assess|optimi[sz]e|validate)\b", r"(评估|审核|优化|验证)"],
    "create": [r"\b(design|architect|invent|prototype|lead)\b", r"(设计|架构|创新|原型|主导)"],
}


def classify_bloom_level(text: str) -> str:
    low = (text or "").lower()
    best = "remember"
    best_score = -1
    for level, patterns in _PATTERNS.items():
        score = 0
        for p in patterns:
            score += len(re.findall(p, low, flags=re.I))
        if score > best_score:
            best_score = score
            best = level
    return best


def compute_bloom_score(snippets: List[str]) -> Dict[str, object]:
    if not snippets:
        return {"score": 0.0, "distribution": {}, "dominant_level": "remember"}
    distribution: Dict[str, int] = {}
    weighted_sum = 0.0
    for s in snippets:
        level = classify_bloom_level(s)
        distribution[level] = distribution.get(level, 0) + 1
        weighted_sum += BLOOM_WEIGHTS.get(level, 0.1)
    dominant = max(distribution.items(), key=lambda kv: kv[1])[0]
    score = weighted_sum / max(len(snippets), 1)
    return {
        "score": round(score, 4),
        "distribution": distribution,
        "dominant_level": dominant,
    }
