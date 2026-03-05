"""
Pytest configuration and fixtures for SkillSight tests.
"""
import pytest
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Set test environment (use 127.0.0.1 to avoid IPv6 localhost resolution issues)
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "postgresql+psycopg2://skillsight:skillsight@127.0.0.1:55432/skillsight_test"


@pytest.fixture(scope="session")
def db_engine():
    """Create test database engine."""
    from sqlalchemy import create_engine
    
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://skillsight:skillsight@localhost:55432/skillsight"
    )
    
    engine = create_engine(database_url)
    return engine


@pytest.fixture
def db(db_engine):
    """Create a database session for testing."""
    from sqlalchemy.orm import sessionmaker
    
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db):
    """Create a test client with database dependency override."""
    from fastapi.testclient import TestClient
    
    try:
        from fastapi import Depends
        from backend.app.main import app
        from backend.app.db.deps import get_db
        from backend.app.security import require_auth, get_identity, Identity
    except ImportError:
        from fastapi import Depends
        from app.main import app
        from app.db.deps import get_db
        from app.security import require_auth, get_identity, Identity
    
    def override_get_db():
        try:
            db.rollback()  # Clear any aborted transaction from previous request
            yield db
        finally:
            pass
    
    def _testing_require_auth(ident: Identity = Depends(get_identity)):
        """Accept any identity (including header-based) when TESTING."""
        return ident
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = _testing_require_auth
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_document(db):
    """Create a sample document for testing."""
    from sqlalchemy import text
    
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    # Insert document
    db.execute(text("""
        INSERT INTO documents (doc_id, filename, stored_path, created_at, doc_type)
        VALUES (:doc_id, :filename, :stored_path, :created_at, :doc_type)
        ON CONFLICT DO NOTHING
    """), {
        "doc_id": doc_id,
        "filename": "test_document.txt",
        "stored_path": f"upload://{doc_id}/test_document.txt",
        "created_at": now,
        "doc_type": "txt"
    })
    
    # Insert chunks
    for i in range(3):
        chunk_id = str(uuid.uuid4())
        db.execute(text("""
            INSERT INTO chunks (chunk_id, doc_id, idx, char_start, char_end, snippet, quote_hash, created_at, chunk_text)
            VALUES (:chunk_id, :doc_id, :idx, :char_start, :char_end, :snippet, :quote_hash, :created_at, :chunk_text)
            ON CONFLICT DO NOTHING
        """), {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "idx": i,
            "char_start": i * 100,
            "char_end": (i + 1) * 100,
            "snippet": f"Test chunk {i} content for testing purposes.",
            "quote_hash": f"hash_{i}",
            "created_at": now,
            "chunk_text": f"Test chunk {i} full content for testing purposes. This is sample text."
        })
    
    db.commit()
    
    yield {"doc_id": doc_id, "filename": "test_document.txt"}
    
    # Cleanup
    db.execute(text("DELETE FROM chunks WHERE doc_id = :doc_id"), {"doc_id": doc_id})
    db.execute(text("DELETE FROM documents WHERE doc_id = :doc_id"), {"doc_id": doc_id})
    db.commit()


@pytest.fixture
def sample_skill(db):
    """Create a sample skill for testing."""
    from sqlalchemy import text
    
    skill_id = "TEST.SKILL.001.v1"
    
    db.execute(text("""
        INSERT INTO skills (skill_id, canonical_name, definition, version)
        VALUES (:skill_id, :canonical_name, :definition, :version)
        ON CONFLICT (skill_id) DO NOTHING
    """), {
        "skill_id": skill_id,
        "canonical_name": "Test Skill",
        "definition": "A skill used for testing purposes.",
        "version": "v1"
    })
    db.commit()
    
    yield {"skill_id": skill_id}
    
    # Cleanup
    db.execute(text("DELETE FROM skills WHERE skill_id = :skill_id"), {"skill_id": skill_id})
    db.commit()


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant client for testing."""
    with patch('backend.app.vector_store.get_client') as mock:
        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_embeddings():
    """Mock embeddings function for testing."""
    with patch('backend.app.embeddings.embed_texts') as mock:
        mock.return_value = [[0.1] * 384]  # Mock 384-dim embedding
        yield mock


@pytest.fixture
def mock_ollama():
    """Mock Ollama LLM for testing."""
    with patch('backend.app.ollama_client.call_ollama') as mock:
        mock.return_value = '{"label": "demonstrated", "evidence_chunk_ids": [], "rationale": "test"}'
        yield mock
