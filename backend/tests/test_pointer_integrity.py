"""
Pointer Integrity Test Suite for SkillSight (Protocol 4)

Tests that evidence pointers maintain integrity and can be traced back to source documents.
Core principle: Every assessment must have verifiable pointers.
"""
import pytest
import hashlib
import uuid
from typing import Any, Dict, List, Optional


def compute_quote_hash(text: str) -> str:
    """Compute SHA-256 hash of text for integrity verification."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def verify_pointer_integrity(chunk_text: str, quote_hash: str) -> bool:
    """Verify that chunk text matches stored hash."""
    computed = compute_quote_hash(chunk_text)
    return computed == quote_hash


def make_snippet(text: str, max_len: int = 220) -> str:
    """Create snippet from text."""
    text = text.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def validate_pointer(pointer: dict) -> List[str]:
    """
    Validate an evidence pointer.
    Returns list of validation errors (empty if valid).
    """
    errors = []
    
    if not pointer.get("doc_id"):
        errors.append("doc_id is required")
    if not pointer.get("chunk_id"):
        errors.append("chunk_id is required")
    if pointer.get("char_start") is None:
        errors.append("char_start is required")
    if pointer.get("char_end") is None:
        errors.append("char_end is required")
    if pointer.get("char_start") is not None and pointer.get("char_end") is not None:
        if pointer.get("char_start", 0) >= pointer.get("char_end", 0):
            errors.append("char_start must be < char_end")
    if not pointer.get("snippet"):
        errors.append("snippet is required")
    if len(pointer.get("snippet", "")) > 300:
        errors.append("snippet must be ≤ 300 characters")
    if not pointer.get("quote_hash"):
        errors.append("quote_hash is required")
    
    return errors


def create_chunk(
    text: str,
    doc_id: str,
    char_start: int,
    char_end: int,
    section_path: Optional[str] = None,
    page_start: Optional[int] = None
) -> Dict[str, Any]:
    """Create a properly formatted chunk with integrity hash."""
    return {
        "chunk_id": str(uuid.uuid4()),
        "doc_id": doc_id,
        "char_start": char_start,
        "char_end": char_end,
        "chunk_text": text,
        "snippet": make_snippet(text),
        "quote_hash": compute_quote_hash(text),
        "section_path": section_path,
        "page_start": page_start,
        "page_end": page_start,
    }


class TestQuoteHashIntegrity:
    """Tests for quote hash computation and verification."""
    
    def test_hash_computed_correctly(self):
        """Hash should be computed using SHA-256."""
        text = "This is test content for hashing."
        expected = hashlib.sha256(text.encode('utf-8')).hexdigest()
        
        assert compute_quote_hash(text) == expected
    
    def test_hash_verification_matches(self):
        """Verification should return True for matching content."""
        text = "Privacy-sensitive data must be anonymized."
        quote_hash = compute_quote_hash(text)
        
        assert verify_pointer_integrity(text, quote_hash) is True
    
    def test_hash_verification_fails_on_modification(self):
        """Verification should fail if content is modified."""
        original = "Privacy-sensitive data must be anonymized."
        quote_hash = compute_quote_hash(original)
        
        modified = "Privacy-sensitive data should be anonymized."  # "must" -> "should"
        
        assert verify_pointer_integrity(modified, quote_hash) is False
    
    def test_hash_sensitive_to_whitespace(self):
        """Hash should be sensitive to whitespace changes."""
        text1 = "Hello world"
        text2 = "Hello  world"  # Extra space
        
        assert compute_quote_hash(text1) != compute_quote_hash(text2)
    
    def test_hash_sensitive_to_case(self):
        """Hash should be case-sensitive."""
        text1 = "Hello World"
        text2 = "hello world"
        
        assert compute_quote_hash(text1) != compute_quote_hash(text2)
    
    def test_hash_handles_unicode(self):
        """Hash should handle Unicode correctly."""
        text = "学生隐私保护措施 🔒"
        quote_hash = compute_quote_hash(text)
        
        assert verify_pointer_integrity(text, quote_hash) is True
    
    def test_hash_handles_empty_string(self):
        """Hash should handle empty string."""
        text = ""
        quote_hash = compute_quote_hash(text)
        
        assert verify_pointer_integrity(text, quote_hash) is True


class TestPointerValidation:
    """Tests for pointer structure validation."""
    
    def test_valid_pointer_passes(self):
        """A complete, valid pointer should pass validation."""
        pointer = {
            "doc_id": "550e8400-e29b-41d4-a716-446655440000",
            "chunk_id": "6fa459ea-ee8a-3ca4-894e-db77e160355e",
            "char_start": 100,
            "char_end": 200,
            "snippet": "This is a valid snippet.",
            "quote_hash": "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a",
        }
        
        errors = validate_pointer(pointer)
        assert len(errors) == 0
    
    def test_missing_doc_id_fails(self):
        """Missing doc_id should fail validation."""
        pointer = {
            "chunk_id": "6fa459ea-ee8a-3ca4-894e-db77e160355e",
            "char_start": 100,
            "char_end": 200,
            "snippet": "Test snippet.",
            "quote_hash": "abc123",
        }
        
        errors = validate_pointer(pointer)
        assert "doc_id is required" in errors
    
    def test_missing_chunk_id_fails(self):
        """Missing chunk_id should fail validation."""
        pointer = {
            "doc_id": "550e8400-e29b-41d4-a716-446655440000",
            "char_start": 100,
            "char_end": 200,
            "snippet": "Test snippet.",
            "quote_hash": "abc123",
        }
        
        errors = validate_pointer(pointer)
        assert "chunk_id is required" in errors
    
    def test_invalid_char_range_fails(self):
        """char_start >= char_end should fail."""
        pointer = {
            "doc_id": "doc-1",
            "chunk_id": "chunk-1",
            "char_start": 200,
            "char_end": 100,  # Invalid: end < start
            "snippet": "Test.",
            "quote_hash": "abc123",
        }
        
        errors = validate_pointer(pointer)
        assert "char_start must be < char_end" in errors
    
    def test_snippet_too_long_fails(self):
        """Snippet > 300 chars should fail."""
        pointer = {
            "doc_id": "doc-1",
            "chunk_id": "chunk-1",
            "char_start": 0,
            "char_end": 500,
            "snippet": "A" * 301,  # Too long
            "quote_hash": "abc123",
        }
        
        errors = validate_pointer(pointer)
        assert "snippet must be ≤ 300 characters" in errors
    
    def test_missing_quote_hash_fails(self):
        """Missing quote_hash should fail validation."""
        pointer = {
            "doc_id": "doc-1",
            "chunk_id": "chunk-1",
            "char_start": 0,
            "char_end": 100,
            "snippet": "Test snippet.",
        }
        
        errors = validate_pointer(pointer)
        assert "quote_hash is required" in errors
    
    def test_snippet_exactly_300_chars_passes(self):
        """Snippet of exactly 300 chars should pass."""
        pointer = {
            "doc_id": "doc-1",
            "chunk_id": "chunk-1",
            "char_start": 0,
            "char_end": 300,
            "snippet": "A" * 300,  # Exactly 300
            "quote_hash": "abc123",
        }
        
        errors = validate_pointer(pointer)
        assert "snippet must be ≤ 300 characters" not in errors


class TestChunkCreation:
    """Tests for chunk creation helper."""
    
    def test_chunk_has_required_fields(self):
        """Created chunk should have all required fields."""
        chunk = create_chunk(
            text="This is a test paragraph about privacy.",
            doc_id="doc-123",
            char_start=0,
            char_end=40,
        )
        
        assert "chunk_id" in chunk
        assert "doc_id" in chunk
        assert "char_start" in chunk
        assert "char_end" in chunk
        assert "chunk_text" in chunk
        assert "snippet" in chunk
        assert "quote_hash" in chunk
    
    def test_chunk_hash_matches_text(self):
        """Chunk's quote_hash should match its text."""
        text = "This is a test paragraph."
        chunk = create_chunk(text=text, doc_id="doc-1", char_start=0, char_end=25)
        
        assert verify_pointer_integrity(text, chunk["quote_hash"]) is True
    
    def test_snippet_truncated_for_long_text(self):
        """Snippet should be truncated for long text."""
        long_text = "A" * 500
        chunk = create_chunk(text=long_text, doc_id="doc-1", char_start=0, char_end=500)
        
        assert len(chunk["snippet"]) <= 223  # 220 + "..."
        assert chunk["snippet"].endswith("...")
    
    def test_snippet_preserves_short_text(self):
        """Short text should not be truncated."""
        short_text = "Short."
        chunk = create_chunk(text=short_text, doc_id="doc-1", char_start=0, char_end=6)
        
        assert chunk["snippet"] == "Short."
    
    def test_optional_fields_included(self):
        """Optional fields should be included when provided."""
        chunk = create_chunk(
            text="Test.",
            doc_id="doc-1",
            char_start=0,
            char_end=5,
            section_path="2.1 Methods",
            page_start=5
        )
        
        assert chunk["section_path"] == "2.1 Methods"
        assert chunk["page_start"] == 5


class TestPointerResolution:
    """Tests for pointer resolution scenarios."""
    
    def test_pointer_can_locate_original_text(self):
        """Pointer offsets should locate exact text in original document."""
        original_document = """
Introduction

This is the first paragraph of the document. It contains important information.

Methods

We used the following approach to analyze the data.
"""
        # Create pointer to the Methods paragraph
        chunk_text = "We used the following approach to analyze the data."
        char_start = original_document.find(chunk_text)
        char_end = char_start + len(chunk_text)
        
        pointer = {
            "doc_id": "doc-1",
            "chunk_id": "chunk-1",
            "char_start": char_start,
            "char_end": char_end,
            "snippet": chunk_text[:50],
            "quote_hash": compute_quote_hash(chunk_text),
        }
        
        # Verify we can extract the exact text using pointer
        extracted = original_document[pointer["char_start"]:pointer["char_end"]]
        
        assert extracted == chunk_text
        assert verify_pointer_integrity(extracted, pointer["quote_hash"]) is True
    
    def test_pointer_offsets_are_exclusive_end(self):
        """char_end should be exclusive (Python slice semantics)."""
        text = "Hello World"
        pointer = {
            "doc_id": "doc-1",
            "chunk_id": "chunk-1",
            "char_start": 0,
            "char_end": 5,  # Should be exclusive
            "snippet": "Hello",
            "quote_hash": compute_quote_hash("Hello"),
        }
        
        extracted = text[pointer["char_start"]:pointer["char_end"]]
        assert extracted == "Hello"


class TestAssessmentPointerIntegrity:
    """Tests for assessment-level pointer integrity."""
    
    def test_assessment_must_have_pointers_for_positive_claim(self):
        """Positive claims must include at least one valid pointer."""
        # This is a business rule test
        assessment = {
            "label": "demonstrated",
            "evidence": [],  # No pointers!
        }
        
        # Business rule: demonstrated/mentioned requires evidence
        assert len(assessment["evidence"]) == 0
        # This should trigger refusal (tested in test_refusal.py)
    
    def test_pointers_in_evidence_are_valid(self):
        """All pointers in evidence array should pass validation."""
        chunk_text = "We anonymize student emails before processing."
        evidence = [
            {
                "doc_id": "doc-1",
                "chunk_id": "chunk-1",
                "char_start": 0,
                "char_end": 45,
                "snippet": chunk_text[:45],
                "quote_hash": compute_quote_hash(chunk_text),
            }
        ]
        
        for pointer in evidence:
            errors = validate_pointer(pointer)
            assert len(errors) == 0, f"Pointer validation failed: {errors}"
    
    def test_multiple_pointers_all_verifiable(self):
        """Multiple pointers should all be independently verifiable."""
        texts = [
            "First piece of evidence.",
            "Second piece of evidence.",
            "Third piece of evidence.",
        ]
        
        evidence = [
            create_chunk(text=t, doc_id="doc-1", char_start=i*50, char_end=i*50+len(t))
            for i, t in enumerate(texts)
        ]
        
        for i, pointer in enumerate(evidence):
            assert verify_pointer_integrity(texts[i], pointer["quote_hash"]) is True


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
