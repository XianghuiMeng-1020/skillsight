"""Apply accepted resume suggestions to plain text (shared by rescore and template export)."""

from __future__ import annotations

import re


def apply_suggestion_replace_once(text: str, orig: str, repl: str) -> str:
    """
    Replace the first occurrence of orig with repl: exact match, stripped match,
    newline-normalized match, or flexible whitespace between words.
    """
    if not orig or repl is None:
        return text
    if orig in text:
        return text.replace(orig, repl, 1)
    o = orig.strip()
    if o and o in text:
        return text.replace(o, repl, 1)
    nt = text.replace("\r\n", "\n")
    oo = o.replace("\r\n", "\n")
    if oo and oo in nt:
        i = nt.index(oo)
        return nt[:i] + repl + nt[i + len(oo) :]
    tokens = o.split()
    if len(tokens) < 2:
        return text
    pat = r"\s+".join(re.escape(t) for t in tokens)
    m = re.search(pat, text)
    if m:
        return text[: m.start()] + repl + text[m.end() :]
    return text
