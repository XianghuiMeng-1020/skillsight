"""
Test suite for document management endpoints.
Covers: upload, parsing, chunking, multimodal support.
"""
import pytest
from unittest.mock import patch, MagicMock
import io


class TestDocumentUpload:
    """Tests for document upload functionality."""
    
    def test_upload_txt_creates_document(self, client, db):
        """Test that uploading a TXT file creates a document record."""
        content = b"This is a test document with sufficient length for chunking.\n\nIt has multiple paragraphs that exceed the minimum chunk size of 50 characters each."
        files = {"file": ("test.txt", io.BytesIO(content), "text/plain")}
        
        response = client.post(
            "/documents/upload?doc_type=demo&user_id=test_user&consent=true",
            files=files
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "doc_id" in data
        assert data["filename"] == "test.txt"
        assert data["chunks_created"] > 0
    
    def test_upload_without_consent_fails(self, client):
        """Test that upload without consent is rejected."""
        content = b"Test content"
        files = {"file": ("test.txt", io.BytesIO(content), "text/plain")}
        
        response = client.post(
            "/documents/upload?doc_type=demo&user_id=test_user&consent=false",
            files=files
        )
        
        assert response.status_code == 400
        assert "consent" in response.json()["detail"].lower()
    
    def test_upload_empty_file_fails(self, client):
        """Test that empty file upload is rejected."""
        files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
        
        response = client.post(
            "/documents/upload?doc_type=demo&user_id=test_user&consent=true",
            files=files
        )
        
        assert response.status_code == 400
    
    def test_upload_unsupported_format_fails(self, client):
        """Test that unsupported file format is rejected."""
        files = {"file": ("test.xyz", io.BytesIO(b"content"), "application/octet-stream")}
        
        response = client.post(
            "/documents/upload?doc_type=demo&user_id=test_user&consent=true",
            files=files
        )
        
        assert response.status_code == 400


class TestDocumentChunking:
    """Tests for document chunking functionality."""
    
    def test_txt_chunking_by_paragraphs(self):
        """Test that TXT files are chunked by paragraphs."""
        from app.parsers import parse_txt_to_chunks
        
        content = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
        chunks = parse_txt_to_chunks(content, min_chunk_len=10)
        
        assert len(chunks) == 3
        assert chunks[0]["chunk_text"] == "First paragraph here."
        assert chunks[1]["char_start"] > chunks[0]["char_end"]
    
    def test_chunk_has_required_fields(self):
        """Test that chunks have all required fields."""
        from app.parsers import parse_txt_to_chunks
        
        content = "This is a sufficiently long paragraph for testing purposes."
        chunks = parse_txt_to_chunks(content, min_chunk_len=10)
        
        required_fields = ["idx", "char_start", "char_end", "chunk_text", "snippet", "quote_hash"]
        for chunk in chunks:
            for field in required_fields:
                assert field in chunk, f"Missing field: {field}"
    
    def test_quote_hash_is_consistent(self):
        """Test that quote_hash is deterministic."""
        from backend.app.parsers import parse_txt_to_chunks
        
        content = "Test paragraph content that is long enough for min_chunk_len default."
        chunks1 = parse_txt_to_chunks(content)
        chunks2 = parse_txt_to_chunks(content)
        
        assert len(chunks1) > 0, "parse_txt_to_chunks should return at least one chunk"
        assert chunks1[0]["quote_hash"] == chunks2[0]["quote_hash"]


class TestMultimodalParsing:
    """Tests for multimodal file parsing."""
    
    def test_code_file_parsing(self):
        """Test that code files are parsed with syntax awareness."""
        from app.parsers_multimodal import parse_multimodal_file
        
        code_content = b'''def hello():
    """Say hello."""
    print("Hello, World!")

def goodbye():
    """Say goodbye."""
    print("Goodbye!")
'''
        
        result = parse_multimodal_file(
            file_bytes=code_content,
            filename="test.py",
            min_chunk_len=10
        )
        
        assert result["media_type"] == "code"
        assert len(result["chunks"]) > 0
    
    def test_image_without_ocr_returns_placeholder(self):
        """Test that images without OCR return a placeholder."""
        from app.parsers_multimodal import parse_image_to_chunks
        
        # Create a minimal PNG header (not a real image)
        fake_image = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        
        chunks = parse_image_to_chunks(file_bytes=fake_image)
        
        # Should return placeholder if OCR is not available
        assert len(chunks) > 0
        assert "media_type" in chunks[0] or "image" in chunks[0].get("chunk_text", "").lower()


class TestDocumentRetrieval:
    """Tests for document retrieval functionality."""
    
    def test_list_documents(self, client, db):
        """Test listing all documents."""
        response = client.get("/documents?limit=10", headers={"X-Subject-Id": "test", "X-Role": "staff"})
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "count" in data
    
    def test_get_document_chunks(self, client, db, sample_document):
        """Test getting chunks for a document."""
        doc_id = sample_document["doc_id"]
        
        response = client.get(f"/documents/{doc_id}/chunks", headers={"X-Subject-Id": "test", "X-Role": "staff"})
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    def test_get_nonexistent_document_fails(self, client):
        """Test that getting a nonexistent document returns 404."""
        response = client.get("/documents/00000000-0000-0000-0000-000000000000", headers={"X-Subject-Id": "test", "X-Role": "staff"})
        
        assert response.status_code == 404
