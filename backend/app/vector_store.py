"""
Vector store module for SkillSight.
Uses Qdrant for vector similarity search.
Controlled degradation: curl fallback only when QDRANT_FALLBACK_CURL=1.
"""
import json
import logging
import os
import subprocess
import threading
import time
import warnings
from typing import Any, List, Optional

COLLECTION = "chunks_v1"
_client = None
_qdrant_available = None
_client_lock = threading.Lock()

# Config
QDRANT_TIMEOUT = float(os.getenv("QDRANT_TIMEOUT", "30"))
QDRANT_RETRIES = int(os.getenv("QDRANT_RETRIES", "3"))
QDRANT_RETRY_BASE_DELAY = float(os.getenv("QDRANT_RETRY_BASE_DELAY", "1.0"))
QDRANT_FALLBACK_CURL = os.getenv("QDRANT_FALLBACK_CURL", "").strip().lower() in ("1", "true", "yes")

logger = logging.getLogger(__name__)


def _check_qdrant():
    """Check if Qdrant client is available."""
    global _qdrant_available
    if _qdrant_available is None:
        try:
            from qdrant_client import QdrantClient  # noqa: F401
            _qdrant_available = True
        except ImportError:
            logger.warning("qdrant-client not installed, vector search disabled")
            _qdrant_available = False
    return _qdrant_available


def get_client():
    """Get or create Qdrant client with timeout settings (thread-safe)."""
    global _client

    if not _check_qdrant():
        return None

    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client
        try:
            from qdrant_client import QdrantClient

            qdrant_url = os.getenv("QDRANT_URL", "").strip()
            qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip() or None

            if qdrant_url:
                # Qdrant Cloud: URL + optional API Key
                _client = QdrantClient(
                    url=qdrant_url,
                    api_key=qdrant_api_key,
                    timeout=QDRANT_TIMEOUT,
                    prefer_grpc=False,
                )
            else:
                host = os.getenv("QDRANT_HOST", "localhost")
                port = int(os.getenv("QDRANT_PORT", "6333"))
                _client = QdrantClient(
                    host=host,
                    port=port,
                    timeout=QDRANT_TIMEOUT,
                    prefer_grpc=False,
                    trust_env=False,
                )
        except Exception as e:
            logger.warning("Failed to connect to Qdrant: %s", e)
            return None

    return _client


def _get_qm():
    """Lazy import of qdrant models."""
    if not _check_qdrant():
        return None
    from qdrant_client.http import models as qm
    return qm


# For backwards compatibility
qm = None
try:
    from qdrant_client.http import models as qm
except ImportError:
    pass


def ensure_collection(client, dim: int):
    """Ensure collection exists in Qdrant, with payload indexes for filtering."""
    if client is None:
        return
    qm = _get_qm()
    if qm is None:
        return
    created = False
    try:
        client.get_collection(COLLECTION)
    except Exception as exc:
        logger.warning("collection check failed, will create: %s", exc)
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )
        created = True

    _ensure_payload_index(client, qm, "doc_id", qm.PayloadSchemaType.KEYWORD)
    if created:
        _ensure_payload_index(client, qm, "chunk_id", qm.PayloadSchemaType.KEYWORD)


def _ensure_payload_index(client, qm, field_name: str, schema_type):
    """Create a payload index if it doesn't already exist."""
    try:
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field_name,
            field_schema=schema_type,
        )
        logger.info("Created payload index for '%s' on collection '%s'", field_name, COLLECTION)
    except Exception as exc:
        if "already exists" in str(exc).lower():
            return
        logger.warning("Payload index creation for '%s' failed (non-fatal): %s", field_name, exc)


def upsert_points(client, points: list):
    """Upsert points to Qdrant collection."""
    if client is None:
        return
    client.upsert(collection_name=COLLECTION, points=points)


def delete_by_doc_id(client, doc_id: str):
    """Delete all points for a document."""
    if client is None:
        return
    qm = _get_qm()
    if qm is None:
        return
    client.delete(
        collection_name=COLLECTION,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))]
            )
        ),
    )


def collection_exists(client) -> bool:
    """Check if the collection exists."""
    if client is None:
        return False
    try:
        client.get_collection(COLLECTION)
        return True
    except Exception as exc:
        logger.warning("collection_exists check failed: %s", exc)
        return False


def _search_with_retry(client, query_vec: list[float], top_k: int, flt=None, request_id: str = "", doc_id: str = ""):
    """Search with exponential backoff retries."""
    last_err = None
    for attempt in range(QDRANT_RETRIES):
        try:
            # qdrant-client >= 1.7: query_points() replaces the deprecated search()
            if hasattr(client, "query_points"):
                resp = client.query_points(
                    collection_name=COLLECTION,
                    query=query_vec,
                    limit=top_k,
                    query_filter=flt,
                    with_payload=True,
                    with_vectors=False,
                )
                return resp.points
            # Legacy fallback for qdrant-client < 1.7
            if hasattr(client, "search"):
                kwargs = {
                    "collection_name": COLLECTION,
                    "query_vector": query_vec,
                    "limit": top_k,
                    "with_payload": True,
                    "with_vectors": False,
                }
                if flt is not None:
                    return client.search(**kwargs, query_filter=flt)
                return client.search(**kwargs)
        except Exception as e:
            last_err = e
            logger.warning(
                "Qdrant search attempt %d failed request_id=%s doc_id=%s: %s",
                attempt + 1, request_id, doc_id, e,
            )
        if attempt < QDRANT_RETRIES - 1:
            delay = QDRANT_RETRY_BASE_DELAY * (2 ** attempt)
            time.sleep(delay)
    raise last_err or RuntimeError("Qdrant search failed")


def search(client, query_vec: list[float], top_k: int, flt=None, request_id: str = "", doc_id: str = ""):
    """
    Search with retries. Returns empty list if client/collection unavailable.
    Raises on failure when client exists but search fails (caller may try curl fallback).
    """
    if client is None:
        return []

    if not collection_exists(client):
        return []

    return _search_with_retry(client, query_vec, top_k, flt, request_id, doc_id)


def _qdrant_base_url() -> str:
    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    if qdrant_url:
        return qdrant_url.rstrip("/")
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    return f"http://{host}:{port}"


def search_via_curl(query_vec: list[float], top_k: int, doc_id: Optional[str] = None) -> list:
    """Fallback: search Qdrant via curl. Only used when QDRANT_FALLBACK_CURL=1."""
    if not QDRANT_FALLBACK_CURL:
        return []
    url = f"{_qdrant_base_url()}/collections/{COLLECTION}/points/search"
    body = {"vector": query_vec, "limit": top_k, "with_payload": True, "with_vector": False}
    if doc_id:
        body["filter"] = {"must": [{"key": "doc_id", "match": {"value": doc_id}}]}
    body_str = json.dumps(body)
    curl_cmd = ["curl", "-sS", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", body_str]
    api_key = os.getenv("QDRANT_API_KEY", "").strip()
    if api_key:
        curl_cmd.extend(["-H", f"api-key: {api_key}"])
    r = subprocess.run(
        curl_cmd,
        capture_output=True,
        text=True,
        timeout=int(QDRANT_TIMEOUT),
    )
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout or "{}")
        hits = data.get("result", [])
        return [type("ScoredPoint", (), {"score": h.get("score", 0), "payload": h.get("payload", {})})() for h in hits]
    except Exception as exc:
        logger.warning("curl search response parse failed: %s", exc)
        return []


def qdrant_health() -> dict:
    """Check Qdrant health. Returns {ok: bool, error?: str}."""
    try:
        client = get_client()
        if client is None:
            return {"ok": False, "error": "Qdrant client unavailable"}
        client.get_collections()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
