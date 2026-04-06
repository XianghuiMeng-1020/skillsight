"""Suggestion replacement helpers."""

from backend.app.services.resume_text_merge import apply_suggestion_replace_once


def test_exact_replace():
    assert apply_suggestion_replace_once("aa bb cc", "bb", "XX") == "aa XX cc"


def test_strip_replace():
    assert apply_suggestion_replace_once("  hello  ", "hello", "X") == "  X  "


def test_flexible_whitespace_multiword():
    t = "Led a team to deliver the product"
    orig = "Led  a   team to deliver"
    result = apply_suggestion_replace_once(t, orig, "Managed")
    assert result == "Managed the product"


def test_newline_normalized():
    t = "line one\nline two"
    orig = "line one\r\nline two"
    out = apply_suggestion_replace_once(t, orig, "Z")
    assert "Z" in out
