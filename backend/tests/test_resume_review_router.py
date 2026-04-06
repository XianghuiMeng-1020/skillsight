from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.app.routers import resume_review as rr
from backend.app.security import Identity


def _ident() -> Identity:
    return Identity(subject_id="u1", role="student", source="bearer")


def test_score_unexpected_error_is_sanitized(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(rr, "_get_review_for_user", lambda *_: {"status": "scoring", "doc_id": "d1", "target_role_id": None})
    monkeypatch.setattr(rr, "_check_consent", lambda *_: None)
    monkeypatch.setattr(rr, "get_resume_text_from_doc", lambda *_: "x" * 200)
    monkeypatch.setattr(rr, "score_resume", lambda *_, **__: (_ for _ in ()).throw(Exception("boom: internal detail")))

    with pytest.raises(HTTPException) as ei:
        rr.resume_review_score("r1", db=db, ident=_ident())
    assert ei.value.status_code == 500
    detail = ei.value.detail
    assert detail["error"] == "scoring_failed"
    assert "Exception" not in detail["message"]
    assert "boom" not in detail["message"]


def test_apply_template_internal_error_is_sanitized(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(rr, "_get_review_for_user", lambda *_: {"status": "enhanced", "doc_id": "d1", "target_role_id": None})
    monkeypatch.setattr(rr, "_merge_resume_with_suggestions", lambda *_: "Resume content")
    monkeypatch.setattr(rr, "template_apply", lambda *_, **__: (_ for _ in ()).throw(RuntimeError("private stack details")))

    with pytest.raises(HTTPException) as ei:
        rr.resume_review_apply_template(
            "r1",
            payload=rr.ApplyTemplateRequest(template_id="professional_classic", export_format="docx"),
            db=db,
            ident=_ident(),
        )
    assert ei.value.status_code == 500
    detail = ei.value.detail
    assert detail["error"] == "internal_error"
    assert "traceback" not in detail
    assert "RuntimeError" not in detail["message"]
