"""
Refusal Test Suite for SkillSight (Protocol 6)

Tests that the system correctly refuses to make claims when evidence is insufficient.
Core principle: "No pointer, no claim."
"""
import pytest
import json
from typing import Any, Dict, List

# Import validation functions from the AI router
# These will be tested in isolation without requiring full server

def validate_demonstration_output(
    output: Dict[str, Any],
    valid_chunk_ids: List[str]
) -> Dict[str, Any]:
    """
    Validate and normalize demonstration output.
    Copied from routers/ai.py for isolated testing.
    """
    label = output.get("label", "not_enough_information")
    if label not in ["demonstrated", "mentioned", "not_enough_information"]:
        label = "not_enough_information"
    
    evidence_ids = output.get("evidence_chunk_ids", [])
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    
    # Filter to only valid chunk IDs
    valid_set = set(valid_chunk_ids)
    evidence_ids = [cid for cid in evidence_ids if cid in valid_set]
    
    rationale = output.get("rationale", "")
    refusal_reason = output.get("refusal_reason")
    
    # Enforce refusal rules
    if label == "not_enough_information":
        evidence_ids = []
        if not refusal_reason:
            refusal_reason = "Evidence insufficient or irrelevant to demonstrate this skill."
    else:
        if not evidence_ids:
            # If no valid evidence but claiming demonstrated/mentioned, downgrade to not_enough_information
            label = "not_enough_information"
            refusal_reason = "No valid evidence chunk IDs provided."
    
    return {
        "label": label,
        "evidence_chunk_ids": evidence_ids,
        "rationale": rationale[:500] if rationale else "",
        "refusal_reason": refusal_reason,
    }


def validate_proficiency_output(
    output: Dict[str, Any],
    valid_chunk_ids: List[str],
    valid_criteria: List[str]
) -> Dict[str, Any]:
    """
    Validate and normalize proficiency output.
    Copied from routers/ai.py for isolated testing.
    """
    level = output.get("level", 0)
    if not isinstance(level, int) or level < 0 or level > 3:
        level = 0
    
    label_map = {0: "novice", 1: "developing", 2: "proficient", 3: "advanced"}
    label = output.get("label", label_map.get(level, "novice"))
    if label not in label_map.values():
        label = label_map.get(level, "novice")
    
    evidence_ids = output.get("evidence_chunk_ids", [])
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    valid_set = set(valid_chunk_ids)
    evidence_ids = [cid for cid in evidence_ids if cid in valid_set]
    
    matched_criteria = output.get("matched_criteria", [])
    if not isinstance(matched_criteria, list):
        matched_criteria = []
    if valid_criteria:
        valid_criteria_set = set(valid_criteria)
        matched_criteria = [c for c in matched_criteria if c in valid_criteria_set]
    
    why = output.get("why", "")
    
    # Enforce: if no evidence, level must be 0
    if not evidence_ids and level > 0:
        level = 0
        label = "novice"
    
    return {
        "level": level,
        "label": label,
        "matched_criteria": matched_criteria,
        "evidence_chunk_ids": evidence_ids,
        "why": why[:500] if why else "",
    }


class TestDemonstrationRefusal:
    """Tests for Decision 2 (Demonstration) refusal logic."""
    
    VALID_CHUNK_IDS = ["chunk-001", "chunk-002", "chunk-003"]
    
    def test_empty_evidence_must_refuse(self):
        """If LLM claims 'demonstrated' but provides no evidence, must refuse."""
        output = {
            "label": "demonstrated",
            "evidence_chunk_ids": [],
            "rationale": "The document clearly shows privacy practices.",
            "refusal_reason": None
        }
        result = validate_demonstration_output(output, self.VALID_CHUNK_IDS)
        
        assert result["label"] == "not_enough_information"
        assert result["evidence_chunk_ids"] == []
        assert result["refusal_reason"] is not None
    
    def test_invalid_chunk_ids_must_refuse(self):
        """If LLM provides chunk IDs that don't exist, must refuse."""
        output = {
            "label": "demonstrated",
            "evidence_chunk_ids": ["fake-001", "fake-002"],
            "rationale": "Evidence found in chunks.",
            "refusal_reason": None
        }
        result = validate_demonstration_output(output, self.VALID_CHUNK_IDS)
        
        assert result["label"] == "not_enough_information"
        assert result["evidence_chunk_ids"] == []
        assert result["refusal_reason"] is not None
    
    def test_mixed_valid_invalid_chunks_filters(self):
        """Valid chunks should be kept, invalid filtered."""
        output = {
            "label": "demonstrated",
            "evidence_chunk_ids": ["chunk-001", "fake-001", "chunk-002"],
            "rationale": "Evidence found.",
            "refusal_reason": None
        }
        result = validate_demonstration_output(output, self.VALID_CHUNK_IDS)
        
        assert result["label"] == "demonstrated"
        assert result["evidence_chunk_ids"] == ["chunk-001", "chunk-002"]
        assert result["refusal_reason"] is None
    
    def test_explicit_refusal_clears_evidence(self):
        """When label is 'not_enough_information', evidence must be empty."""
        output = {
            "label": "not_enough_information",
            "evidence_chunk_ids": ["chunk-001"],  # LLM error: shouldn't have this
            "rationale": "Not enough evidence.",
            "refusal_reason": "Document doesn't address this skill."
        }
        result = validate_demonstration_output(output, self.VALID_CHUNK_IDS)
        
        assert result["label"] == "not_enough_information"
        assert result["evidence_chunk_ids"] == []
        assert result["refusal_reason"] is not None
    
    def test_mentioned_with_valid_evidence_allowed(self):
        """'mentioned' with valid evidence should pass."""
        output = {
            "label": "mentioned",
            "evidence_chunk_ids": ["chunk-001"],
            "rationale": "Skill mentioned but not demonstrated.",
            "refusal_reason": None
        }
        result = validate_demonstration_output(output, self.VALID_CHUNK_IDS)
        
        assert result["label"] == "mentioned"
        assert result["evidence_chunk_ids"] == ["chunk-001"]
    
    def test_invalid_label_defaults_to_refusal(self):
        """Unknown labels should default to refusal."""
        output = {
            "label": "maybe",  # Invalid label
            "evidence_chunk_ids": ["chunk-001"],
            "rationale": "Uncertain.",
            "refusal_reason": None
        }
        result = validate_demonstration_output(output, self.VALID_CHUNK_IDS)
        
        assert result["label"] == "not_enough_information"
    
    def test_valid_demonstrated_passes(self):
        """Valid 'demonstrated' with evidence should pass."""
        output = {
            "label": "demonstrated",
            "evidence_chunk_ids": ["chunk-001", "chunk-002"],
            "rationale": "Clear privacy practices shown.",
            "refusal_reason": None
        }
        result = validate_demonstration_output(output, self.VALID_CHUNK_IDS)
        
        assert result["label"] == "demonstrated"
        assert len(result["evidence_chunk_ids"]) == 2
        assert result["refusal_reason"] is None


class TestProficiencyRefusal:
    """Tests for Decision 3 (Proficiency) refusal logic."""
    
    VALID_CHUNK_IDS = ["chunk-001", "chunk-002", "chunk-003"]
    VALID_CRITERIA = ["PR0-1", "PR1-1", "PR2-1", "PR2-2", "PR3-1"]
    
    def test_no_evidence_forces_level_zero(self):
        """If no valid evidence, level must be 0 regardless of LLM claim."""
        output = {
            "level": 3,
            "label": "advanced",
            "matched_criteria": ["PR3-1"],
            "evidence_chunk_ids": [],
            "why": "Excellent demonstration."
        }
        result = validate_proficiency_output(output, self.VALID_CHUNK_IDS, self.VALID_CRITERIA)
        
        assert result["level"] == 0
        assert result["label"] == "novice"
        assert result["evidence_chunk_ids"] == []
    
    def test_invalid_level_defaults_to_zero(self):
        """Invalid level values should default to 0."""
        for invalid_level in [-1, 4, 100, "high", None]:
            output = {
                "level": invalid_level,
                "label": "advanced",
                "matched_criteria": [],
                "evidence_chunk_ids": ["chunk-001"],
                "why": "Test."
            }
            result = validate_proficiency_output(output, self.VALID_CHUNK_IDS, self.VALID_CRITERIA)
            
            assert result["level"] == 0
    
    def test_invalid_criteria_filtered(self):
        """Criteria not in valid list should be filtered."""
        output = {
            "level": 2,
            "label": "proficient",
            "matched_criteria": ["PR2-1", "FAKE-1", "PR2-2"],
            "evidence_chunk_ids": ["chunk-001"],
            "why": "Meets criteria."
        }
        result = validate_proficiency_output(output, self.VALID_CHUNK_IDS, self.VALID_CRITERIA)
        
        assert result["matched_criteria"] == ["PR2-1", "PR2-2"]
        assert "FAKE-1" not in result["matched_criteria"]
    
    def test_invalid_label_corrected(self):
        """Invalid labels should be corrected based on level."""
        output = {
            "level": 2,
            "label": "expert",  # Invalid
            "matched_criteria": ["PR2-1"],
            "evidence_chunk_ids": ["chunk-001"],
            "why": "Test."
        }
        result = validate_proficiency_output(output, self.VALID_CHUNK_IDS, self.VALID_CRITERIA)
        
        assert result["label"] == "proficient"  # Corrected to match level 2
    
    def test_valid_proficiency_passes(self):
        """Valid proficiency assessment should pass."""
        output = {
            "level": 2,
            "label": "proficient",
            "matched_criteria": ["PR2-1", "PR2-2"],
            "evidence_chunk_ids": ["chunk-001", "chunk-002"],
            "why": "Demonstrates concrete privacy practices."
        }
        result = validate_proficiency_output(output, self.VALID_CHUNK_IDS, self.VALID_CRITERIA)
        
        assert result["level"] == 2
        assert result["label"] == "proficient"
        assert len(result["evidence_chunk_ids"]) == 2
        assert len(result["matched_criteria"]) == 2
    
    def test_why_truncated_if_too_long(self):
        """Long 'why' should be truncated to 500 chars."""
        output = {
            "level": 1,
            "label": "developing",
            "matched_criteria": ["PR1-1"],
            "evidence_chunk_ids": ["chunk-001"],
            "why": "A" * 1000  # Very long
        }
        result = validate_proficiency_output(output, self.VALID_CHUNK_IDS, self.VALID_CRITERIA)
        
        assert len(result["why"]) <= 500


class TestEdgeCases:
    """Edge case tests for refusal logic."""
    
    def test_empty_valid_chunk_list(self):
        """When no chunks provided, any claim must refuse."""
        output = {
            "label": "demonstrated",
            "evidence_chunk_ids": ["chunk-001"],
            "rationale": "Found evidence.",
            "refusal_reason": None
        }
        result = validate_demonstration_output(output, valid_chunk_ids=[])
        
        assert result["label"] == "not_enough_information"
    
    def test_none_values_handled(self):
        """None values should be handled gracefully."""
        output = {
            "label": None,
            "evidence_chunk_ids": None,
            "rationale": None,
            "refusal_reason": None
        }
        result = validate_demonstration_output(output, ["chunk-001"])
        
        assert result["label"] == "not_enough_information"
        assert result["evidence_chunk_ids"] == []
    
    def test_unicode_in_rationale(self):
        """Unicode characters should be preserved."""
        output = {
            "label": "demonstrated",
            "evidence_chunk_ids": ["chunk-001"],
            "rationale": "学生展示了学术诚信的理解 🎓",
            "refusal_reason": None
        }
        result = validate_demonstration_output(output, ["chunk-001"])
        
        assert "学生" in result["rationale"]
        assert "🎓" in result["rationale"]


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
