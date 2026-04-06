"""Shared helpers for resume parsing/rendering."""

from __future__ import annotations

import re
from typing import List, Tuple


def contains_cjk(text: str) -> bool:
    """East Asian / CJK codepoints (incl. Japanese/Korean)."""
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text or ""))


def split_contact_parts(contact_lines: List[str]) -> List[str]:
    """Flatten contact lines separated by pipes / dots into individual items."""
    parts: List[str] = []
    for cl in contact_lines:
        for p in re.split(r"[|·•]", cl):
            p = p.strip()
            if p:
                parts.append(p)
    return parts


def split_skills_lines(lines: List[str]) -> Tuple[List[str], List[str]]:
    """Parse skills lines into structured ('Label: ...') and flat items."""
    structured: List[str] = []
    flat: List[str] = []
    for line in lines:
        stripped = (line or "").strip().lstrip("•-–▪►✦*▸ ").strip()
        if not stripped:
            continue
        if re.match(r"^[^:]{1,48}:\s*.{2,}", stripped) and "http" not in stripped.lower():
            structured.append(stripped)
            continue
        for part in re.split(r"[,;，；、]", stripped):
            part = part.strip()
            if part:
                flat.append(part)
    return structured, flat
