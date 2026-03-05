"""
P5 Decision 1: Reranker + Threshold Refusal tests.
- reranker off: no rerank
- reranker on: post scores apply
- top1 < threshold: refusal (items=[], code correct)
- reranker init failure: fail-closed refusal
"""
import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _reset_retrieval_env():
    """Reset retrieval_pipeline module state between tests."""
    import sys
    mods = [k for k in sys.modules if "retrieval_pipeline" in k]
    for m in mods:
        del sys.modules[m]
    yield
    for m in mods:
        if m in sys.modules:
            del sys.modules[m]


def test_reranker_off_no_rerank(client, db):
    """When RERANKER_ENABLED=0, no reranking; vector results returned."""
    doc_id = "test-doc-d1"
    with patch.dict(os.environ, {"RERANKER_ENABLED": "0"}):
        import importlib
        import backend.app.retrieval_pipeline as rp
        importlib.reload(rp)

        from backend.app.retrieval_pipeline import retrieve_evidence

        mock_point = MagicMock()
        mock_point.score = 0.45
        mock_point.payload = {
            "chunk_id": "c1",
            "doc_id": doc_id,
            "idx": 0,
            "snippet": "test snippet",
        }
        with patch("backend.app.vector_store.get_client", return_value=MagicMock()):
            with patch("backend.app.vector_store.search", return_value=[mock_point]):
                with patch("backend.app.embeddings.embed_texts", return_value=[[0.1] * 384]):
                    result = retrieve_evidence(
                        "test query",
                        doc_filter=doc_id,
                        top_k=5,
                        use_reranker=False,
                        include_snippet=True,
                    )
        assert len(result.items) >= 1
        assert result.retrieval_meta.reranker_enabled is False
        assert result.retrieval_meta.refusal is None


def test_top1_below_threshold_returns_refusal(client, db):
    """When vector top1 < EVIDENCE_MIN_SCORE_PRE, return refusal with items=[]."""
    doc_id = "test-doc-d1"
    with patch.dict(os.environ, {"EVIDENCE_MIN_SCORE_PRE": "0.30", "RERANKER_ENABLED": "0"}):
        import importlib
        import backend.app.retrieval_pipeline as rp
        importlib.reload(rp)

        from backend.app.retrieval_pipeline import retrieve_evidence

        mock_point = MagicMock()
        mock_point.score = 0.15  # Below 0.30
        mock_point.payload = {"chunk_id": "c1", "doc_id": doc_id, "idx": 0, "snippet": "x"}
        with patch("backend.app.vector_store.get_client", return_value=MagicMock()):
            with patch("backend.app.vector_store.search", return_value=[mock_point]):
                with patch("backend.app.embeddings.embed_texts", return_value=[[0.1] * 384]):
                    result = retrieve_evidence(
                    "test",
                    doc_filter=doc_id,
                    top_k=5,
                    thresholds={"min_pre": 0.30},
                    include_snippet=True,
                )
        assert len(result.items) == 0
        assert result.retrieval_meta.refusal is not None
        assert result.retrieval_meta.refusal.get("code") == "evidence_below_threshold_pre"
        assert "next_step" in result.retrieval_meta.refusal
        assert result.reliability.level == "low"


def test_reranker_init_failure_fail_closed(client, db):
    """When reranker enabled but fails, return refusal (fail-closed)."""
    doc_id = "test-doc-d1"
    with patch.dict(os.environ, {"RERANKER_ENABLED": "1", "RERANKER_MODEL": "placeholder"}):
        import importlib
        import backend.app.retrieval_pipeline as rp
        importlib.reload(rp)

        from backend.app.retrieval_pipeline import retrieve_evidence

        def _fail_rerank(*args, **kwargs):
            raise RuntimeError("Reranker init failed")

        mock_point = MagicMock()
        mock_point.score = 0.50
        mock_point.payload = {"chunk_id": "c1", "doc_id": doc_id, "idx": 0, "snippet": "x"}
        with patch("backend.app.vector_store.get_client", return_value=MagicMock()):
            with patch("backend.app.vector_store.search", return_value=[mock_point]):
                with patch("backend.app.embeddings.embed_texts", return_value=[[0.1] * 384]):
                    with patch.object(rp, "_rerank", side_effect=_fail_rerank):
                        result = retrieve_evidence(
                            "test",
                            doc_filter=doc_id,
                            top_k=5,
                            use_reranker=True,
                            include_snippet=True,
                        )
        assert len(result.items) == 0
        assert result.retrieval_meta.refusal is not None
        assert result.retrieval_meta.refusal.get("code") == "reranker_failed"
        assert result.reliability.level == "low"


def test_search_endpoint_refusal_structure(client, db):
    """Search endpoint returns refusal structure when threshold not met."""
    with patch("backend.app.routers.search.retrieve_evidence") as mock_ret:
        from backend.app.retrieval_pipeline import RetrievalResult, RetrievalMeta, ReliabilityInfo, RetrievalItem

        mock_ret.return_value = RetrievalResult(
            items=[],
            retrieval_meta=RetrievalMeta(
                vector_top_k=10,
                reranker_enabled=False,
                pre_scores=[0.10],
                post_scores=[],
                min_score_passed=False,
                refusal={"code": "evidence_below_threshold_pre", "message": "Below threshold", "next_step": "Retry"},
            ),
            reliability=ReliabilityInfo(level="low", reason_codes=["evidence_below_threshold_pre"]),
        )

        resp = client.post(
            "/search/evidence_vector",
            json={"query_text": "xyz", "k": 5},
            headers={"X-Subject-Id": "test", "X-Role": "staff"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert "refusal" in data
        assert data["refusal"]["code"] == "evidence_below_threshold_pre"
        assert "reliability" in data
        assert data["reliability"]["level"] == "low"
