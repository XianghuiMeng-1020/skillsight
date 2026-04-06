"""Chunk coalescing and TXT chunking behavior."""

from backend.app.parsers import _coalesce_short_paragraphs, parse_txt_to_chunks


def test_coalesce_merges_short_segments():
    parts = ["x" * 25, "y" * 25]
    out = _coalesce_short_paragraphs(parts, min_chunk_len=50)
    assert len(out) == 1
    assert len(out[0]) >= 50


def test_coalesce_single_short_emitted():
    out = _coalesce_short_paragraphs(["hi"], min_chunk_len=50)
    assert out == ["hi"]


def test_parse_txt_merges_double_newline_short_blocks():
    text = "a" * 30 + "\n\n" + "b" * 30
    chunks = parse_txt_to_chunks(text, min_chunk_len=50)
    assert len(chunks) >= 1
    assert len(chunks[0]["chunk_text"]) >= 50
