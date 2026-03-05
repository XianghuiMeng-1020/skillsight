"""
Test suite for search endpoints.
Covers: vector search, keyword search, evidence retrieval.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestVectorSearch:
    """Tests for vector-based evidence search."""
    
    def test_search_with_skill_id(self, client, db):
        """Test searching with a skill ID."""
        response = client.post(
            "/search/evidence_vector",
            json={
                "skill_id": "HKU.SKILL.PRIVACY.v1",
                "k": 5
            },
            headers={"X-Subject-Id": "test_user", "X-Role": "staff"}
        )
        
        # May return 200 with empty results or 404 if skill not found
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "items" in data
            assert "query_text" in data
    
    def test_search_with_free_text(self, client, db):
        """Test searching with free text query."""
        response = client.post(
            "/search/evidence_vector",
            json={
                "query_text": "privacy data protection",
                "k": 5
            },
            headers={"X-Subject-Id": "test_user", "X-Role": "staff"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["query_text"] == "privacy data protection"
    
    def test_search_requires_skill_or_query(self, client, db):
        """Test that search requires either skill_id or query_text."""
        response = client.post(
            "/search/evidence_vector",
            json={"k": 5},
            headers={"X-Subject-Id": "test_user", "X-Role": "staff"}
        )
        
        assert response.status_code == 400
        assert "skill_id" in response.json()["detail"].lower() or "query" in response.json()["detail"].lower()
    
    def test_search_with_doc_filter(self, client, db, sample_document):
        """Test searching within a specific document."""
        doc_id = sample_document["doc_id"]
        
        response = client.post(
            "/search/evidence_vector",
            json={
                "query_text": "test content",
                "doc_id": doc_id,
                "k": 5
            },
            headers={"X-Subject-Id": "test_user", "X-Role": "staff"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["doc_id"] == doc_id
    
    def test_search_respects_min_score(self, client, db):
        """Test that min_score filters results."""
        response = client.post(
            "/search/evidence_vector",
            json={
                "query_text": "privacy",
                "k": 10,
                "min_score": 0.9  # High threshold
            },
            headers={"X-Subject-Id": "test_user", "X-Role": "staff"}
        )
        
        assert response.status_code == 200
        data = response.json()
        # All returned items should have score >= 0.9
        for item in data["items"]:
            assert item["score"] >= 0.9


class TestKeywordSearch:
    """Tests for keyword-based evidence search."""
    
    def test_keyword_search_basic(self, client, db):
        """Test basic keyword search."""
        response = client.post(
            "/search/evidence_keyword",
            json={
                "query_text": "privacy",
                "k": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    def test_keyword_search_with_doc_filter(self, client, db, sample_document):
        """Test keyword search within a document."""
        doc_id = sample_document["doc_id"]
        
        response = client.post(
            "/search/evidence_keyword",
            json={
                "query_text": "test",
                "doc_id": doc_id,
                "k": 5
            }
        )
        
        assert response.status_code == 200


class TestEvidenceItems:
    """Tests for evidence item structure."""
    
    def test_evidence_item_has_required_fields(self, client, db):
        """Test that evidence items have required fields."""
        response = client.post(
            "/search/evidence_vector",
            json={"query_text": "test", "k": 1},
            headers={"X-Subject-Id": "test_user", "X-Role": "staff"}
        )
        
        if response.status_code == 200 and response.json()["items"]:
            item = response.json()["items"][0]
            required_fields = ["chunk_id", "doc_id", "snippet", "score"]
            for field in required_fields:
                assert field in item, f"Missing required field: {field}"
    
    def test_evidence_item_has_position_info(self, client, db, sample_document):
        """Test that evidence items have position information."""
        response = client.post(
            "/search/evidence_keyword",
            json={
                "query_text": "test",
                "doc_id": sample_document["doc_id"],
                "k": 1
            }
        )
        
        if response.status_code == 200 and response.json()["items"]:
            item = response.json()["items"][0]
            # Position fields should be present (may be null)
            assert "char_start" in item or "idx" in item
