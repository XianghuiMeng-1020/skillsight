from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

COLLECTION = "chunks_v1"

def get_client() -> QdrantClient:
    return QdrantClient(host="localhost", port=6333)

def ensure_collection(client: QdrantClient, dim: int):
    try:
        client.get_collection(COLLECTION)
        return
    except Exception:
        pass
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
    )

def upsert_points(client: QdrantClient, points: list[qm.PointStruct]):
    client.upsert(collection_name=COLLECTION, points=points)

def delete_by_doc_id(client: QdrantClient, doc_id: str):
    client.delete(
        collection_name=COLLECTION,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))]
            )
        ),
    )

def search(client: QdrantClient, query_vec: list[float], top_k: int, flt: qm.Filter | None):
    """
    Version-tolerant search wrapper for qdrant-client.
    - Some versions expect `query_filter=...`
    - Some expect `filter=...`
    - Some use `search_points` instead of `search`
    """
    kwargs = {
        "collection_name": COLLECTION,
        "query_vector": query_vec,
        "limit": top_k,
        "with_payload": True,
        "with_vectors": False,
    }

    # Try client.search first
    if hasattr(client, "search"):
        try:
            if flt is not None:
                return client.search(**kwargs, query_filter=flt)
            return client.search(**kwargs)
        except TypeError:
            # fallback for older/newer signature using `filter=...`
            if flt is not None:
                return client.search(**kwargs, filter=flt)
            return client.search(**kwargs)

    # Fallback: some clients expose search_points
    if hasattr(client, "search_points"):
        if flt is not None:
            return client.search_points(collection_name=COLLECTION, query=query_vec, limit=top_k, query_filter=flt, with_payload=True)
        return client.search_points(collection_name=COLLECTION, query=query_vec, limit=top_k, with_payload=True)

    raise AttributeError("Qdrant client has no search or search_points method")
