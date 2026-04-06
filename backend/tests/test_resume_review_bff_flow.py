from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.db.deps import get_db
from backend.app.routers import resume_review as rr
from backend.app.security import Identity, require_auth


class _Result:
    def __init__(self, rows: Optional[List[Any]] = None, scalar_value: Any = None):
        self._rows = rows or []
        self._scalar = scalar_value

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _FakeDb:
    def __init__(self):
        self.status = "scoring"
        self.review_id = "rid-1"
        self.suggestions: List[Dict[str, Any]] = []

    def execute(self, statement, params=None):
        sql = str(statement).lower()
        if "select 1 from resume_suggestions" in sql:
            return _Result(scalar_value=1 if self.suggestions else None)
        if "from resume_suggestions" in sql and "status in ('accepted', 'edited')" in sql and "replacement" in sql:
            rows = [(s["original_text"], s["suggested_text"], "accepted") for s in self.suggestions]
            return _Result(rows=rows)
        if "set initial_scores" in sql and "status = 'reviewed'" in sql:
            self.status = "reviewed"
            return _Result()
        if "set final_scores" in sql and "status = 'enhanced'" in sql:
            self.status = "enhanced"
            return _Result()
        if "set template_id" in sql and "status = 'completed'" in sql:
            self.status = "completed"
            return _Result()
        if "insert into resume_suggestions" in sql:
            self.suggestions.append(
                {
                    "original_text": params.get("orig", ""),
                    "suggested_text": params.get("sug", ""),
                }
            )
            return _Result()
        if "select count(*) from chunks" in sql:
            return _Result(scalar_value=650)
        if "select original_text" in sql and "from resume_suggestions" in sql:
            return _Result(rows=[("Improved impact sentence",)])
        return _Result()

    def commit(self):
        return None


def _override_auth():
    return Identity(subject_id="u1", role="student", source="bearer")


def test_resume_review_http_flow_happy_path(monkeypatch):
    fake_db = _FakeDb()
    app = FastAPI()
    app.include_router(rr.router, prefix="/bff/student")
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[require_auth] = _override_auth
    try:
        monkeypatch.setattr(rr, "_check_consent", lambda *args, **kwargs: None)
        monkeypatch.setattr(rr, "log_audit", lambda *args, **kwargs: None)
        monkeypatch.setattr(rr, "get_resume_text_from_doc", lambda *args, **kwargs: "Resume text " * 30)
        monkeypatch.setattr(
            rr,
            "_get_review_for_user",
            lambda db, review_id, user_id: {
                "review_id": review_id,
                "user_id": user_id,
                "doc_id": "doc-1",
                "target_role_id": "role-1",
                "status": fake_db.status,
                "initial_scores": {"impact": {"score": 70, "comment": "ok"}},
                "total_initial": 70,
                "final_scores": {"impact": {"score": 75, "comment": "better"}} if fake_db.status == "completed" else None,
                "total_final": 75 if fake_db.status == "completed" else None,
            },
        )
        monkeypatch.setattr(
            rr,
            "score_resume",
            lambda *args, **kwargs: {"scores": {"impact": {"score": 72, "comment": "good"}}, "total": 72},
        )
        monkeypatch.setattr(
            rr,
            "enhancer_generate_suggestions",
            lambda *args, **kwargs: [
                {
                    "dimension": "impact",
                    "section": "Experience",
                    "original_text": "Improved impact sentence",
                    "suggested_text": "Improved impact sentence with metric",
                    "explanation": "Add quantification",
                    "priority": "high",
                }
            ],
        )
        monkeypatch.setattr(rr, "template_apply", lambda *args, **kwargs: b"docx-bytes")
        monkeypatch.setattr(rr, "_merge_resume_with_suggestions", lambda *args, **kwargs: "Merged resume content")
        monkeypatch.setattr(rr, "resolve_template_builder_key", lambda *args, **kwargs: "professional_classic")
        monkeypatch.setattr(rr, "html_preview_for_resume", lambda text, key, opts=None: f"<html><body>{key}:{text[:10]}</body></html>")
        monkeypatch.setattr(rr, "build_verification_snapshot", lambda *args, **kwargs: {"version": "v1", "summary": {"verdict": "pass"}})
        monkeypatch.setattr(rr, "build_attribution_report_docx", lambda *args, **kwargs: b"report-docx")
        monkeypatch.setattr(rr, "docx_bytes_to_pdf_bytes", lambda b: b"report-pdf")

        with TestClient(app) as client:
            r = client.post("/bff/student/resume-review/start", json={"doc_id": "doc-1", "target_role_id": "role-1"})
            assert r.status_code == 200
            review_id = r.json()["review_id"]

            r = client.post(f"/bff/student/resume-review/{review_id}/score")
            assert r.status_code == 200
            assert r.json()["verification_version"] == "v1"

            r = client.post(f"/bff/student/resume-review/{review_id}/suggest")
            assert r.status_code == 200
            assert len(r.json()["suggestions"]) == 1

            r = client.post(f"/bff/student/resume-review/{review_id}/rescore")
            assert r.status_code == 200

            r = client.post(
                f"/bff/student/resume-review/{review_id}/apply-template",
                json={
                    "template_id": "professional_classic",
                    "export_format": "docx",
                    "resume_override_text": "Custom resume text",
                    "template_options": {"font_scale_pct": 105},
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert base64.b64decode(body["content_base64"])
            assert body["format_used"] == "docx"
            assert body["template_options"]["font_scale_pct"] == 105

            r = client.get(f"/bff/student/resume-review/{review_id}/state")
            assert r.status_code == 200
            assert r.json()["max_step"] == 5

            r = client.get(f"/bff/student/resume-review/{review_id}/editable-resume")
            assert r.status_code == 200
            assert "resume_text" in r.json()

            r = client.get(f"/bff/student/resume-review/{review_id}/compression-hints")
            assert r.status_code == 200
            assert "hints" in r.json()

            r = client.post(
                f"/bff/student/resume-review/{review_id}/preview-html",
                json={
                    "template_id": "professional_classic",
                    "resume_override_text": "Preview override",
                    "template_options": {"accent_color": "blue"},
                },
            )
            assert r.status_code == 200
            assert "professional_classic" in r.text

            r = client.post(
                f"/bff/student/resume-review/{review_id}/clone-version",
                json={"target_role_id": "role-2", "label": "A/B"},
            )
            assert r.status_code == 200
            assert "review_id" in r.json()

            r = client.post(
                f"/bff/student/resume-review/{review_id}/diff-insights",
                json={"compare_review_id": review_id, "resume_override_text": "Improved impact sentence\n- Increased conversion 20%"},
            )
            assert r.status_code == 200
            body = r.json()
            assert "dimension_impact" in body
            assert "highlights" in body
            assert "semantic_alignment" in body
            assert "risk_validator" in body
            assert "attribution" in body

            r = client.get(f"/bff/student/resume-review/{review_id}/attribution")
            assert r.status_code == 200
            assert "attribution" in r.json()

            r = client.post(
                f"/bff/student/resume-review/{review_id}/export-attribution-report",
                json={"export_format": "pdf"},
            )
            assert r.status_code == 200
            out = r.json()
            assert base64.b64decode(out["content_base64"])
            assert out["format_used"] == "pdf"
    finally:
        app.dependency_overrides.clear()


def test_layout_check_reports_truncation_and_ambiguity(monkeypatch):
    fake_db = _FakeDb()
    fake_db.status = "enhanced"
    app = FastAPI()
    app.include_router(rr.router, prefix="/bff/student")
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[require_auth] = _override_auth
    try:
        monkeypatch.setattr(
            rr,
            "_get_review_for_user",
            lambda *args, **kwargs: {"review_id": "rid-1", "doc_id": "doc-1", "status": "enhanced"},
        )
        monkeypatch.setattr(rr, "_merge_resume_with_suggestions", lambda *args, **kwargs: ("A" * 32000) + "\nImproved impact sentence\n")
        monkeypatch.setattr(rr, "_check_consent", lambda *args, **kwargs: None)
        with TestClient(app) as client:
            r = client.get("/bff/student/resume-review/rid-1/layout-check")
            assert r.status_code == 200
            body = r.json()
            codes = {it["code"] for it in body["issues"]}
            assert "chunk_truncation" in codes
            assert "prompt_truncation" in codes
    finally:
        app.dependency_overrides.clear()
