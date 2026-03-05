import json

import pytest

from backend.app.guardrails import enforce_demo_output, enforce_prof_output


def test_demo_contract_refusal_shape():
    allowed = {"c1"}
    out = {
        "label": "not_enough_information",
        "evidence_chunk_ids": [],
        "rationale": "x",
        "refusal_reason": "irrelevant_evidence",
    }
    enforce_demo_output(out, allowed)


def test_prof_contract_level0_shape():
    allowed = {"c1"}
    rubric = {"L1.BASIC", "L2.APPLIED"}
    out = {
        "level": 0,
        "label": "novice",
        "matched_criteria": [],
        "evidence_chunk_ids": [],
        "why": "x",
    }
    enforce_prof_output(out, allowed, rubric)


@pytest.mark.parametrize(
    "label,eids,reason,ok",
    [
        ("not_enough_information", [], "irrelevant_evidence", True),
        ("not_enough_information", ["c1"], "irrelevant_evidence", False),
        ("demonstrated", ["c1"], None, True),
        ("demonstrated", [], None, False),
    ],
)
def test_demo_contract_matrix(label, eids, reason, ok):
    allowed = {"c1"}
    out = {"label": label, "evidence_chunk_ids": eids, "rationale": "x", "refusal_reason": reason}
    if ok:
        enforce_demo_output(out, allowed)
    else:
        with pytest.raises(ValueError):
            enforce_demo_output(out, allowed)

