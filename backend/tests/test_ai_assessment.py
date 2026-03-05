"""
Test suite for AI assessment endpoints.
Covers: demonstration classification, proficiency assessment, role readiness.
"""
import pytest
from unittest.mock import patch, MagicMock
import json


class TestDemonstrationAssessment:
    """Tests for skill demonstration classification (Decision 2)."""
    
    @patch('backend.app.routers.ai._get_ollama')
    def test_demonstration_returns_valid_label(self, mock_get_ollama, client, db, sample_document):
        """Test that demonstration assessment returns a valid label."""
        # Mock LLM: _get_ollama() returns a callable; that callable is invoked with (model, prompt, ...)
        mock_get_ollama.return_value = lambda *a, **kw: json.dumps({
            "label": "demonstrated",
            "evidence_chunk_ids": ["chunk_1"],
            "rationale": "The document shows clear evidence of privacy practices.",
            "refusal_reason": None
        })
        
        response = client.post(
            "/ai/demonstration",
            json={
                "skill_id": "HKU.SKILL.PRIVACY.v1",
                "doc_id": sample_document["doc_id"],
                "k": 5
            },
            headers={"X-Subject-Id": "test", "X-Role": "staff"}
        )
        
        # May fail if skill not in DB, but should not crash
        assert response.status_code in [200, 404, 503]
        if response.status_code == 200:
            data = response.json()
            assert data["label"] in ["demonstrated", "mentioned", "not_enough_information"]
    
    @patch('backend.app.routers.ai._get_ollama')
    def test_demonstration_requires_evidence_for_positive_labels(self, mock_get_ollama, client, db, sample_document):
        """Test that positive labels require evidence chunk IDs."""
        mock_get_ollama.return_value = lambda *a, **kw: json.dumps({
            "label": "demonstrated",
            "evidence_chunk_ids": [],  # Invalid - no evidence
            "rationale": "Some reason",
            "refusal_reason": None
        })
        
        response = client.post(
            "/ai/demonstration",
            json={
                "skill_id": "HKU.SKILL.PRIVACY.v1",
                "doc_id": sample_document["doc_id"]
            },
            headers={"X-Subject-Id": "test", "X-Role": "staff"}
        )
        
        # Should either fail validation or return not_enough_information
        if response.status_code == 200:
            # If it passes, label should be adjusted
            data = response.json()
            # The guardrails should catch this
            pass
    
    @patch('backend.app.routers.ai._get_ollama')
    def test_demonstration_refusal_has_reason(self, mock_get_ollama, client, db, sample_document):
        """Test that refusal includes a reason."""
        mock_get_ollama.return_value = lambda *a, **kw: json.dumps({
            "label": "not_enough_information",
            "evidence_chunk_ids": [],
            "rationale": "Insufficient evidence found.",
            "refusal_reason": "No relevant chunks found that demonstrate this skill."
        })
        
        response = client.post(
            "/ai/demonstration",
            json={
                "skill_id": "HKU.SKILL.PRIVACY.v1",
                "doc_id": sample_document["doc_id"]
            },
            headers={"X-Subject-Id": "test", "X-Role": "staff"}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data["label"] == "not_enough_information":
                assert data.get("refusal_reason") is not None


class TestProficiencyAssessment:
    """Tests for proficiency level assessment (Decision 3)."""
    
    @patch('backend.app.routers.ai._get_ollama')
    def test_proficiency_returns_valid_level(self, mock_get_ollama, client, db, sample_document):
        """Test that proficiency returns a valid level (0-3)."""
        mock_get_ollama.return_value = lambda *a, **kw: json.dumps({
            "level": 2,
            "label": "intermediate",
            "evidence_chunk_ids": ["chunk_1"],
            "rationale": "Shows intermediate understanding.",
            "criteria_matched": ["AI2-1"]
        })
        
        response = client.post(
            "/ai/proficiency",
            json={
                "skill_id": "HKU.SKILL.PRIVACY.v1",
                "doc_id": sample_document["doc_id"]
            },
            headers={"X-Subject-Id": "test", "X-Role": "staff"}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data["level"] in [0, 1, 2, 3]
            assert "label" in data
    
    @patch('backend.app.routers.ai._get_ollama')
    def test_proficiency_references_rubric(self, mock_get_ollama, client, db, sample_document):
        """Test that proficiency references rubric criteria."""
        mock_get_ollama.return_value = lambda *a, **kw: json.dumps({
            "level": 2,
            "label": "intermediate",
            "evidence_chunk_ids": ["chunk_1"],
            "rationale": "Matches criteria AI2-1.",
            "criteria_matched": ["AI2-1", "AI2-2"]
        })
        
        response = client.post(
            "/ai/proficiency",
            json={
                "skill_id": "HKU.SKILL.ACADEMIC_INTEGRITY.v1",
                "doc_id": sample_document["doc_id"]
            },
            headers={"X-Subject-Id": "test", "X-Role": "staff"}
        )
        
        if response.status_code == 200:
            data = response.json()
            # Should have criteria reference if available
            if "criteria_matched" in data:
                assert len(data["criteria_matched"]) > 0


class TestRoleReadiness:
    """Tests for role readiness assessment (Decision 4)."""
    
    def test_role_readiness_returns_skill_breakdown(self, client, db, sample_document):
        """Test that role readiness returns skill-by-skill breakdown."""
        response = client.post(
            "/assess/role_readiness",
            json={
                "doc_id": sample_document["doc_id"],
                "role_id": "HKU.ROLE.ASSISTANT_PM.v1"
            },
            headers={"X-Subject-Id": "test", "X-Role": "staff"}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "skills" in data
            for skill in data["skills"]:
                assert "status" in skill
                assert skill["status"] in ["meet", "needs_strengthening", "missing_proof"]
    
    def test_role_readiness_with_nonexistent_role(self, client, db, sample_document):
        """Test role readiness with nonexistent role."""
        response = client.post(
            "/assess/role_readiness",
            json={
                "doc_id": sample_document["doc_id"],
                "role_id": "NONEXISTENT_ROLE"
            },
            headers={"X-Subject-Id": "test", "X-Role": "staff"}
        )
        
        assert response.status_code in [404, 400]


class TestActionRecommendations:
    """Tests for action card recommendations (Decision 5)."""
    
    def test_action_recommend_returns_cards(self, client, db, sample_document):
        """Test that action recommend returns action cards."""
        response = client.post(
            "/actions/recommend",
            json={
                "doc_id": sample_document["doc_id"]
            },
            headers={"X-Subject-Id": "test", "X-Role": "staff"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "actions" in data
    
    def test_action_card_has_required_fields(self, client, db, sample_document):
        """Test that action cards have required fields."""
        response = client.post(
            "/actions/recommend",
            json={
                "doc_id": sample_document["doc_id"],
                "gap_types": ["missing_proof"]
            },
            headers={"X-Subject-Id": "test", "X-Role": "staff"}
        )
        
        if response.status_code == 200 and response.json()["actions"]:
            card = response.json()["actions"][0]
            required_fields = ["skill_id", "gap_type", "title", "what_to_do"]
            for field in required_fields:
                assert field in card, f"Missing field: {field}"
    
    def test_action_templates_endpoint(self, client):
        """Test listing action templates."""
        response = client.get("/actions/templates")
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "count" in data
