import pytest

from backend.app.guardrails import enforce_demo_output, enforce_prof_output, validate_pointer


def test_demo_refusal_requires_empty_evidence_and_reason():
    allowed = {"c1", "c2"}
    obj = {"label": "not_enough_information", "evidence_chunk_ids": [], "rationale": "x", "refusal_reason": "insufficient_evidence"}
    out = enforce_demo_output(obj, allowed)
    assert out["evidence_chunk_ids"] == []
    assert out["refusal_reason"] == "insufficient_evidence"


def test_demo_non_refusal_requires_known_evidence():
    allowed = {"c1", "c2"}
    obj = {"label": "demonstrated", "evidence_chunk_ids": ["c2"], "rationale": "x", "refusal_reason": None}
    out = enforce_demo_output(obj, allowed)
    assert out["evidence_chunk_ids"] == ["c2"]
    assert out["refusal_reason"] is None


def test_demo_non_refusal_rejects_unknown_chunk_id():
    allowed = {"c1"}
    obj = {"label": "mentioned", "evidence_chunk_ids": ["c2"], "rationale": "x", "refusal_reason": None}
    with pytest.raises(ValueError):
        enforce_demo_output(obj, allowed)


def test_prof_level0_requires_empty_evidence_and_criteria():
    allowed = {"c1"}
    rub = {"R1"}
    obj = {"level": 0, "label": "novice", "matched_criteria": ["R1"], "evidence_chunk_ids": ["c1"], "why": "x"}
    with pytest.raises(ValueError):
        enforce_prof_output(obj, allowed, rub)


def test_prof_level_gt0_requires_evidence_and_known_criteria():
    allowed = {"c1", "c2"}
    rub = {"R1", "R2"}
    obj = {"level": 2, "label": "proficient", "matched_criteria": ["R2"], "evidence_chunk_ids": ["c1"], "why": "x"}
    out = enforce_prof_output(obj, allowed, rub)
    assert out["evidence_chunk_ids"] == ["c1"]
    assert out["matched_criteria"] == ["R2"]


def test_pointer_integrity_ok():
    p = {
        "doc_id": "d1",
        "chunk_id": "c1",
        "char_start": 0,
        "char_end": 10,
        "quote_hash": "a" * 32,
        "snippet": "hello",
    }
    validate_pointer(p)


def test_pointer_integrity_bad_range():
    p = {"doc_id": "d1", "chunk_id": "c1", "char_start": 10, "char_end": 10, "quote_hash": "a" * 32, "snippet": "x"}
    with pytest.raises(ValueError):
        validate_pointer(p)

