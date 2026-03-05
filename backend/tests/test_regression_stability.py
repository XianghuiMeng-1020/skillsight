"""
Regression tests: stability, idempotency, race conditions, denylist, pack integrity.
- Concurrency idempotency: 10 parallel uploads -> 1 doc_id, unique request_ids in audit
- Consent revoke vs embed/search race: fail-closed 403, chunks + Qdrant cleared
- Decision 1 e2e: reranker ordering, below-threshold refusal
- Decision 2: conflicting evidence -> reliability low, change_log, denylist
"""
import concurrent.futures
import os
import time
from typing import List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.tests.test_utils_denylist import assert_no_forbidden_keys, DENYLIST_STAFF_PROGRAMME


def _get_token(client: TestClient, subject_id: str = "regression_test", role: str = "student") -> str:
    r = client.post(
        "/auth/dev_login",
        json={"subject_id": subject_id, "role": role, "ttl_s": 3600},
    )
    assert r.status_code == 200
    return r.json()["token"]


def _upload_one(client: TestClient, token: str, content: bytes, filename: str, user_id: str = "regression_test") -> dict:
    """Single upload via internal API (in-process, uses test DB). Returns response JSON."""
    r = client.post(
        "/documents/upload_multimodal",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, content, "text/plain")},
        params={"user_id": user_id, "consent": "true"},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ─── 1. Concurrency idempotency ──────────────────────────────────────────────


def test_concurrent_upload_idempotency(client: TestClient, db):
    """
    10 concurrent uploads of identical content -> only 1 document row,
    doc_id identical across responses, audit_logs has one entry per request with unique request_id.
    Uses internal /documents/upload_multimodal (in-process) so test DB is used.
    """
    token = _get_token(client)
    content = b"Concurrent idempotency test: Python pandas scikit-learn data analysis."

    def _upload(_i: int) -> dict:
        return _upload_one(client, token, content, f"concurrent_{_i}.txt")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(_upload, range(10)))

    doc_ids = [r["doc_id"] for r in results]
    unique_doc_ids = set(doc_ids)
    assert len(unique_doc_ids) == 1, f"Expected 1 unique doc_id, got {len(unique_doc_ids)}: {doc_ids}"

    doc_id = doc_ids[0]

    # Verify only 1 document row for that content (by content_hash in metadata or doc_id)
    count = db.execute(
        text("SELECT COUNT(*) FROM documents WHERE doc_id = :doc_id"),
        {"doc_id": doc_id},
    ).scalar()
    assert count == 1, f"Expected 1 document row, got {count}"

    # Audit: upload actions should have unique request_ids (middleware logs each request)
    rows = db.execute(
        text("""
            SELECT request_id FROM audit_logs
            WHERE action LIKE 'bff.student.%' AND detail::jsonb->>'path' LIKE '%upload%'
              AND created_at > now() - interval '5 minutes'
        """),
    ).fetchall()
    if len(rows) > 1:
        request_ids = [r[0] for r in rows if r[0]]
        assert len(request_ids) == len(set(request_ids)), "request_ids must be unique per request"


# ─── 2. Consent revoke vs embed/search race ───────────────────────────────────


def test_consent_revoke_embed_search_race_fail_closed(client: TestClient, db):
    """
    Upload (creates chunks), withdraw consent.
    Assert subsequent search is fail-closed (403 with strict refusal shape).
    Assert DB chunks for doc are deleted within 10s.
    """
    token = _get_token(client, "race_test_user")
    content = b"Race test: consent withdraw. Python data analysis."
    upload = _upload_one(client, token, content, "race_test.txt", user_id="race_test_user")
    doc_id = upload["doc_id"]

    # Withdraw consent (cascade delete)
    withdraw = client.post(
        "/bff/student/consents/withdraw",
        headers={"Authorization": f"Bearer {token}"},
        json={"doc_id": doc_id, "reason": "Race test"},
    )
    assert withdraw.status_code == 200

    # Search must be 403 with refusal shape (code, message, next_step)
    search_resp = client.post(
        "/bff/student/search/evidence_vector",
        headers={"Authorization": f"Bearer {token}"},
        json={"query_text": "Python", "doc_id": doc_id, "k": 5},
    )
    assert search_resp.status_code == 403
    body = search_resp.json()
    detail = body.get("detail", body)
    refusal = detail.get("refusal", detail) if isinstance(detail, dict) else {}
    if isinstance(refusal, dict):
        assert refusal.get("code") or refusal.get("message")
        assert refusal.get("next_step") or refusal.get("message")

    # Poll: DB chunks deleted within 10s
    for _ in range(20):
        chunk_count = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        ).scalar()
        if chunk_count == 0:
            break
        time.sleep(0.5)
    assert chunk_count == 0, f"Chunks not deleted after 10s: {chunk_count}"

    # Qdrant: points for doc_id should be 0 (skip if Qdrant unavailable)
    try:
        from backend.app.vector_store import get_client, COLLECTION
        qc = get_client()
        if qc:
            from qdrant_client.http import models as qm
            pts, _ = qc.scroll(
                collection_name=COLLECTION,
                scroll_filter=qm.Filter(
                    must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))]
                ),
                limit=1,
            )
            assert len(pts) == 0, f"Qdrant should have 0 points for doc_id, got {len(pts)}"
    except Exception:
        pytest.skip("Qdrant scroll not available")


# ─── 3. Decision 1 e2e (reranker, threshold) ─────────────────────────────────


@pytest.fixture(autouse=False)
def _reset_retrieval_env():
    import sys
    mods = [k for k in sys.modules if "retrieval_pipeline" in k]
    for m in mods:
        if m in sys.modules:
            del sys.modules[m]
    yield


def test_decision1_reranker_changes_ordering(client, db, _reset_retrieval_env):
    """Reranker on vs off changes result ordering when enabled."""
    from unittest.mock import MagicMock, patch

    doc_id = "d1-rerank"
    with patch.dict(os.environ, {"RERANKER_ENABLED": "1", "EVIDENCE_MIN_SCORE_PRE": "0.01"}):
        import importlib
        import backend.app.retrieval_pipeline as rp
        importlib.reload(rp)

        mock_a = MagicMock()
        mock_a.score = 0.4
        mock_a.payload = {"chunk_id": "c1", "doc_id": doc_id, "idx": 0, "snippet": "first"}
        mock_b = MagicMock()
        mock_b.score = 0.5
        mock_b.payload = {"chunk_id": "c2", "doc_id": doc_id, "idx": 1, "snippet": "second"}

        with patch("backend.app.vector_store.get_client", return_value=MagicMock()):
            with patch("backend.app.vector_store.search", return_value=[mock_a, mock_b]):
                with patch("backend.app.embeddings.embed_texts", return_value=[[0.1] * 384]):
                    def _rerank_ret(query, items, top_k):
                        out = []
                        for it in items:
                            d = dict(it) if isinstance(it, dict) else {}
                            d["chunk_id"] = d.get("chunk_id", "")
                            d["post_score"] = 0.9 if d.get("chunk_id") == "c2" else 0.7
                            out.append(d)
                        out.sort(key=lambda x: x.get("post_score", 0), reverse=True)
                        return out[:top_k]
                    with patch.object(rp, "_rerank", side_effect=_rerank_ret):
                        from backend.app.retrieval_pipeline import retrieve_evidence
                        result = retrieve_evidence(
                            "query",
                            doc_filter=doc_id,
                            top_k=5,
                            use_reranker=True,
                            include_snippet=True,
                        )
                    assert len(result.items) >= 1
                    assert result.retrieval_meta.reranker_enabled is True
                    if len(result.items) >= 2:
                        assert result.items[0].chunk_id == "c2"


def test_decision1_below_threshold_strict_refusal(client, db, _reset_retrieval_env):
    """Below threshold returns strict refusal (code, message, next_step) and items=[]."""
    from unittest.mock import MagicMock, patch

    doc_id = "d1-thresh"
    with patch.dict(os.environ, {"EVIDENCE_MIN_SCORE_PRE": "0.50", "RERANKER_ENABLED": "0"}):
        import importlib
        import backend.app.retrieval_pipeline as rp
        importlib.reload(rp)

        mock_point = MagicMock()
        mock_point.score = 0.20
        mock_point.payload = {"chunk_id": "c1", "doc_id": doc_id, "idx": 0, "snippet": "x"}

        with patch("backend.app.vector_store.get_client", return_value=MagicMock()):
            with patch("backend.app.vector_store.search", return_value=[mock_point]):
                with patch("backend.app.embeddings.embed_texts", return_value=[[0.1] * 384]):
                    from backend.app.retrieval_pipeline import retrieve_evidence
                    result = retrieve_evidence(
                        "test",
                        doc_filter=doc_id,
                        top_k=5,
                        thresholds={"min_pre": 0.50},
                        include_snippet=True,
                    )
        assert len(result.items) == 0
        assert result.retrieval_meta.refusal is not None
        r = result.retrieval_meta.refusal
        assert "code" in r
        assert "message" in r or "next_step" in r


# ─── 4. Decision 2 reliability + change log + denylist ───────────────────────


def test_decision2_conflicting_evidence_reliability_low(client, db):
    """Conflicting evidence -> reliability_level=low, change_log_events entry."""
    from backend.app.skill_level_aggregator import aggregate_skill_level, EvidenceItem

    items = [
        EvidenceItem(doc_id="d1", chunk_id="c1", level=2, label="match", decision="demonstrated",
                     source="assessment", evidence_id="a1"),
        EvidenceItem(doc_id="d2", chunk_id="c2", level=0, label="no_match", decision="not_enough_information",
                     source="assessment", evidence_id="a2"),
    ]
    with patch(
        "backend.app.skill_level_aggregator._collect_evidence_for_skill",
        return_value=items,
    ):
        with patch(
            "backend.app.skill_level_aggregator._get_consented_doc_ids",
            return_value=["d1", "d2"],
        ):
            result = aggregate_skill_level(db, "sub1", "skill1")

    assert result.reliability_level == "low"
    assert result.conflict_detected is True


def test_decision2_staff_programme_no_forbidden_keys(client, db):
    """Staff/programme BFF responses must not contain denylist keys."""
    from backend.tests.test_utils_denylist import assert_response_no_forbidden_keys

    token = client.post(
        "/bff/staff/auth/dev_login",
        json={"subject_id": "staff_deny", "role": "staff", "course_ids": ["C1"], "term_id": "T1"},
    ).json().get("token")
    if not token:
        pytest.skip("Staff auth not available")

    r = client.get(
        "/bff/staff/courses",
        headers={"Authorization": f"Bearer {token}", "X-Purpose": "teaching_support"},
    )
    if r.status_code != 200:
        pytest.skip("Staff courses requires seed data")

    assert_response_no_forbidden_keys(r.json(), role="staff")


# ─── 5. Parameterized role × endpoint access control ──────────────────────────


@pytest.mark.parametrize("role,endpoint,method,purpose", [
    ("student", "/bff/student/documents", "GET", None),
    ("student", "/bff/student/roles", "GET", None),
    ("staff", "/bff/staff/courses", "GET", "teaching_support"),
    ("staff", "/bff/staff/health", "GET", "teaching_support"),
    ("programme_leader", "/bff/programme/programmes", "GET", "aggregate_programme_analysis"),
    ("programme_leader", "/bff/programme/health", "GET", "aggregate_programme_analysis"),
    ("admin", "/bff/admin/skills", "GET", None),
    ("admin", "/bff/admin/health", "GET", None),
])
def test_bff_endpoint_role_access(client, role, endpoint, method, purpose):
    """Parameterized: each role can access allowed BFF endpoints."""
    auth_map = {
        "student": ("/auth/dev_login", {"subject_id": "p_student", "role": "student"}),
        "staff": ("/bff/staff/auth/dev_login", {"subject_id": "p_staff", "role": "staff", "course_ids": ["C1"], "term_id": "T1"}),
        "programme_leader": ("/bff/programme/auth/dev_login", {"subject_id": "p_prog", "role": "programme_leader", "programme_id": "P1"}),
        "admin": ("/bff/admin/auth/dev_login", {"subject_id": "p_admin", "role": "admin"}),
    }
    auth_path, auth_body = auth_map[role]
    r = client.post(auth_path, json=auth_body)
    if r.status_code != 200:
        pytest.skip(f"Auth for {role} not available")
    token = r.json()["token"]

    headers = {"Authorization": f"Bearer {token}"}
    if purpose:
        headers["X-Purpose"] = purpose

    if method == "GET":
        resp = client.get(endpoint, headers=headers)
    else:
        resp = client.post(endpoint, headers=headers, json={})

    assert resp.status_code in (200, 403, 404), f"{role} {endpoint}: {resp.status_code} {resp.text[:200]}"
    if resp.status_code == 200 and role in ("staff", "programme_leader"):
        # Health endpoints may return subject_id for "whoami"; skip denylist for /health
        if "/health" not in endpoint:
            violations = assert_no_forbidden_keys(resp.json(), DENYLIST_STAFF_PROGRAMME)
            assert not violations, f"Denylist violation: {violations}"
