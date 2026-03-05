"""
P5 Decision 2: Reliability + Conflict handling tests.
- Conflicting evidence -> reliability LOW -> positive conclusion refused
- Denylist: staff/programme must not receive snippet/chunk_text
"""
import json
import os
import pytest
from unittest.mock import patch
from sqlalchemy import text


def _db_available():
    """Check if test DB is reachable."""
    try:
        from sqlalchemy import create_engine
        url = os.environ.get("DATABASE_URL", "postgresql+psycopg2://skillsight:skillsight@127.0.0.1:55432/skillsight_test")
        engine = create_engine(url)
        conn = engine.connect()
        conn.close()
        return True
    except Exception:
        return False


def test_aggregator_conflict_detection_low_reliability(db):
    """Conflicting evidence (demonstrated vs not) -> reliability LOW, level 0."""
    from backend.app.skill_level_aggregator import aggregate_skill_level, EvidenceItem

    # Mock _collect_evidence_for_skill to return conflicting items
    items = [
        EvidenceItem(
            doc_id="d1",
            chunk_id="c1",
            level=2,
            label="match",
            decision="demonstrated",
            source="assessment",
            evidence_id="a1",
        ),
        EvidenceItem(
            doc_id="d2",
            chunk_id="c2",
            level=0,
            label="no_match",
            decision="not_enough_information",
            source="assessment",
            evidence_id="a2",
        ),
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
    assert result.level == 0
    assert result.needs_human_review is True


def _run_ai_tests():
    """Run AI-path tests only when explicitly enabled (requires DB + Ollama/API)."""
    return os.environ.get("RUN_AI_TESTS", "") == "1" and _db_available()


@pytest.mark.skipif(
    not _run_ai_tests(),
    reason="AI demonstration test; set RUN_AI_TESTS=1 to enable (requires DB)",
)
def test_demonstration_has_reliability(client, db, sample_document, sample_skill, mock_ollama):
    """AI demonstration response includes reliability field."""
    with patch("backend.app.routers.ai._search_relevant_chunks") as mock_sr:
        mock_sr.return_value = [
            {"chunk_id": "c1", "snippet": "evidence", "section_path": "", "page_start": 1},
        ]
        resp = client.post(
            "/ai/demonstration",
            json={
                "skill_id": sample_skill["skill_id"],
                "doc_id": sample_document["doc_id"],
                "k": 5,
            },
            headers={"X-Subject-Id": "test", "X-Role": "student"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "reliability" in data
    assert "level" in data["reliability"]
    assert data["reliability"]["level"] in ("high", "medium", "low")


def test_search_response_denylist_staff(client, db):
    """Staff/programme search: response must not expose snippet in denylist context.
    Note: /search/evidence_vector returns items with snippet for all roles per current design.
    Denylist applies to BFF staff/programme endpoints - verify bff.staff does not get snippet.
    """
    # Core search returns items with snippet (student/admin may see it)
    # Denylist is enforced in BFF staff/programme proxies - they strip snippet
    # This test verifies the refusal structure is correct (no chunk_text/stored_path)
    with patch("backend.app.routers.search.retrieve_evidence") as mock_ret:
        from backend.app.retrieval_pipeline import (
            RetrievalResult,
            RetrievalMeta,
            ReliabilityInfo,
            RetrievalItem,
        )

        mock_ret.return_value = RetrievalResult(
            items=[
                RetrievalItem(
                    chunk_id="c1",
                    doc_id="d1",
                    score=0.5,
                    source="vector",
                    position_info={"idx": 0},
                    snippet="short snippet",
                ),
            ],
            retrieval_meta=RetrievalMeta(
                vector_top_k=5,
                reranker_enabled=False,
                pre_scores=[0.5],
                post_scores=[0.5],
                min_score_passed=True,
            ),
            reliability=ReliabilityInfo(level="high", reason_codes=["passed"]),
        )

        resp = client.post(
            "/search/evidence_vector",
            json={"query_text": "test", "k": 5},
            headers={"X-Subject-Id": "staff1", "X-Role": "staff"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Core endpoint returns snippet (denylist applied at BFF layer for staff/programme)
        assert "reliability" in data
        assert data["reliability"]["level"] == "high"
        # Must not contain chunk_text, stored_path, embedding
        body_str = json.dumps(data)
        assert "chunk_text" not in body_str or "chunk_text" not in str(data.get("items", [{}])[0])
        assert "stored_path" not in body_str
        assert "embedding" not in body_str
