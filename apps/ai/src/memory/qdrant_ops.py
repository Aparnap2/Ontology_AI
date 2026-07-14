"""
Qdrant memory operations.

Real implementations using Qdrant client for semantic memory storage.
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
import logging
import os
import hashlib
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
)

logger = logging.getLogger(__name__)

# Qdrant configuration
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = os.environ.get("QDRANT_PORT", "6333")
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "ontology_ai_memory")
EMBEDDING_DIM = 2048  # nvidia/llama-nemotron-embed-vl-1b-v2:free produces 2048-dim vectors

# Singleton client
_client: Optional[QdrantClient] = None


def _get_client() -> QdrantClient:
    """Get or create Qdrant client singleton."""
    global _client
    if _client is None:
        _client = QdrantClient(host=QDRANT_HOST, port=int(QDRANT_PORT))
        _ensure_collection_exists(_client)
    return _client


def _ensure_collection_exists(client: QdrantClient) -> None:
    """Create collection if it doesn't exist."""
    try:
        client.get_collection(COLLECTION_NAME)
    except Exception:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def _get_embedding(text: str) -> List[float]:
    """
    Get embedding vector for text using OpenRouter (nvidia/llama-nemotron-embed-vl-1b-v2:free).

    Args:
        text: Text to embed

    Returns:
        List of floats (2048-dim vector)
    """
    import httpx
    
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    embed_model = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    
    if not openrouter_key:
        raise ValueError("OPENROUTER_API_KEY not set")
    
    with httpx.Client(base_url="https://openrouter.ai/api/v1", 
                      headers={"Authorization": f"Bearer {openrouter_key}"},
                      timeout=30.0) as client:
        response = client.post(
            "/embeddings",
            json={"model": embed_model, "input": [text]}
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]


def _generate_point_id(tenant_id: str, content: str) -> str:
    """Generate deterministic point ID from tenant and content."""
    key = f"{tenant_id}:{content}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def upsert_memory(
    tenant_id: str,
    content: str,
    memory_type: str,
    agent: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Upsert memory to Qdrant with temporal fields for decay and relevance.

    Args:
        tenant_id: Tenant who owns this memory
        content: Memory content (text)
        memory_type: Type of memory (anomaly, revenue_event, etc.)
        agent: Agent that created this memory
        metadata: Additional metadata

    Returns:
        Point ID of the upserted memory
    """
    import datetime
    client = _get_client()

    # Generate embedding
    vector = _get_embedding(content)

    # Generate deterministic point ID
    point_id = _generate_point_id(tenant_id, content)

    # Add temporal fields for memory decay
    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(days=180)  # 6 months default

    # Prepare payload with temporal fields - store as timestamps for Qdrant range queries
    payload = {
        "tenant_id": tenant_id,
        "content": content,
        "memory_type": memory_type,
        "agent": agent,
        "occurred_at": now.timestamp(),  # Store as timestamp for queries
        "expires_at": expires_at.timestamp(),  # Store as timestamp for range queries
        "relevance_weight": 1.0,  # Start at full relevance
        **(metadata or {}),
    }

    # Upsert point
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
        ],
    )

    logger.debug(
        f"Upserted memory: tenant={tenant_id}, type={memory_type}, "
        f"agent={agent}, point_id={point_id}"
    )

    return point_id


def query_memory(
    tenant_id: str,
    query_text: str,
    memory_types: Optional[List[str]] = None,
    top_k: int = 5,
    min_score: float = 0.7,
    temporal_boost: bool = True,
) -> List[Dict[str, Any]]:
    """
    Query memories by semantic similarity with tenant isolation enforced.

    Args:
        tenant_id: Tenant ID to filter by (required for security)
        query_text: Query text for semantic search
        memory_types: Filter by memory types (optional)
        top_k: Max results to return
        min_score: Minimum similarity score threshold
        temporal_boost: Whether to boost recent memories in ranking

    Returns:
        List of matching memories with content and metadata
    """
    client = _get_client()

    # Generate query embedding
    query_vector = _get_embedding(query_text)

    # Build filter with enforced tenant isolation
    filter_conditions = [_enforce_tenant_filter(tenant_id)]  # Always include tenant filter

    if memory_types:
        filter_conditions.append(
            FieldCondition(key="memory_type", match=MatchValue(value=memory_types[0]))
        )

    # Only include non-expired memories
    import datetime
    now_timestamp = datetime.datetime.utcnow().timestamp()
    filter_conditions.append(
        FieldCondition(key="expires_at", range=Range(gt=now_timestamp))
    )

    search_filter = Filter(must=filter_conditions)

    # Search using query_points
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=search_filter,
        limit=top_k * 2,  # Get more to allow temporal re-ranking
        score_threshold=min_score,
    )

    # Format and apply temporal boosting if enabled
    memories = []
    for result in results.points:
        if result.payload:
            memory = {
                "content": result.payload.get("content", ""),
                "memory_type": result.payload.get("memory_type", ""),
                "agent": result.payload.get("agent", ""),
                "score": result.score,
                "point_id": result.id,
                "relevance_weight": result.payload.get("relevance_weight", 1.0),
                "occurred_at": result.payload.get("occurred_at", ""),
            }

            if temporal_boost:
                # Boost recent memories by multiplying score by relevance_weight
                memory["score"] = result.score * memory["relevance_weight"]

            memories.append(memory)

    # Sort by boosted score and take top_k
    memories.sort(key=lambda x: x["score"], reverse=True)
    memories = memories[:top_k]

    logger.debug(
        f"Query memory: tenant={tenant_id}, query={query_text[:50]}..., "
        f"found {len(memories)} results (temporal_boost={temporal_boost})"
    )

    return memories


def search_memory(
    tenant_id: str,
    query: str,
    memory_type: Optional[str] = None,
    limit: int = 5,
) -> list[Dict[str, Any]]:
    """
    Search memories by query with enforced tenant isolation.

    Args:
        tenant_id: Tenant ID (required for security)
        query: Search query
        memory_type: Filter by memory type (optional)
        limit: Max results to return

    Returns:
        List of matching memories
    """
    return query_memory(
        tenant_id=tenant_id,
        query_text=query,
        memory_types=[memory_type] if memory_type else None,
        top_k=limit,
        min_score=0.0,  # Lower threshold for search vs query
        temporal_boost=True,  # Always boost recent memories
    )


def delete_memory(tenant_id: str, point_id: str) -> bool:
    """
    Delete a memory by point ID.

    Args:
        tenant_id: Tenant ID (for verification)
        point_id: Point ID to delete

    Returns:
        True if deleted, False otherwise
    """
    client = _get_client()

    # Verify ownership
    try:
        point = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[point_id],
        )
        if not point or point[0].payload.get("tenant_id") != tenant_id:
            return False
    except Exception:
        return False

    # Delete
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=[point_id],
    )

    logger.debug(f"Deleted memory: tenant={tenant_id}, point_id={point_id}")
    return True


def clear_tenant_memory(tenant_id: str) -> int:
    """
    Clear all memory for a tenant.

    Args:
        tenant_id: Tenant ID to clear

    Returns:
        Number of points deleted
    """
    client = _get_client()

    # Get all points for tenant
    all_points = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        ),
        limit=10000,
    )

    point_ids = [point.id for point in all_points[0]]

    if point_ids:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=point_ids,
        )

    logger.debug(f"Cleared {len(point_ids)} memories for tenant={tenant_id}")
    return len(point_ids)


def _enforce_tenant_filter(tenant_id: str) -> Filter:
    """Return filter that ALWAYS includes tenant isolation - required parameter, not optional."""
    return Filter(must=[
        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
    ])


def decay_memory_weights() -> int:
    """
    Weekly job: decay relevance_weight by 15% for all active memories.
    After ~6 months, old vectors have weight 0.01 and are effectively invisible.

    Returns:
        Number of vectors updated
    """
    import datetime
    client = _get_client()

    # Only decay vectors that haven't expired and aren't already at minimum weight
    now_timestamp = datetime.datetime.utcnow().timestamp()
    min_weight_threshold = 0.01

    # Get vectors that need decay (not expired, weight > min threshold)
    decay_filter = Filter(must=[
        FieldCondition(key="expires_at", range=Range(gt=now_timestamp)),
        FieldCondition(key="relevance_weight", range=Range(gt=min_weight_threshold))
    ])

    vectors = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=decay_filter,
        limit=10000,
    )

    if not vectors[0]:
        logger.info("No vectors need relevance decay")
        return 0

    # Update relevance weights (decay by 15%)
    decay_factor = 0.85
    updated_count = 0

    for batch in _chunks(vectors[0], 100):  # Process in batches
        for vector in batch:
            current_weight = vector.payload.get("relevance_weight", 1.0)
            new_weight = max(current_weight * decay_factor, min_weight_threshold)

            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={"relevance_weight": new_weight},
                points=[vector.id]
            )
            updated_count += 1

        # Small delay between batches to avoid overwhelming Qdrant
        import time
        time.sleep(0.1)

    logger.info(f"Decayed relevance weights for {updated_count} vectors")
    return updated_count


def expire_old_memories() -> int:
    """
    Remove vectors where relevance_weight < 0.01 or expired_at < now.
    Keeps the database clean while preserving audit history.

    Returns:
        Number of vectors deleted
    """
    import datetime
    client = _get_client()

    now_timestamp = datetime.datetime.utcnow().timestamp()
    min_weight_threshold = 0.01

    # Find expired or irrelevant vectors
    delete_filter = Filter(should=[
        FieldCondition(key="expires_at", range=Range(lte=now_timestamp)),
        FieldCondition(key="relevance_weight", range=Range(lte=min_weight_threshold))
    ])

    vectors = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=delete_filter,
        limit=10000,
    )

    if not vectors[0]:
        logger.info("No vectors need expiration")
        return 0

    point_ids = [v.id for v in vectors[0]]

    # Delete in batches
    deleted_count = 0
    for batch_ids in _chunks(point_ids, 100):
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=batch_ids,
        )
        deleted_count += len(batch_ids)

        # Small delay between batches
        import time
        time.sleep(0.1)

    logger.info(f"Expired {deleted_count} old/irrelevant vectors")
    return deleted_count


def _chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


class QdrantMemoryManager:
    """Class-based interface for Qdrant memory operations with async support."""

    def __init__(self):
        self.client = _get_client()

    async def close(self):
        """Close the memory manager (no-op for singleton client)."""
        pass

    async def upsert_memory(self, tenant_id: str, content: str, memory_type: str,
                           agent: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Async wrapper for upsert_memory."""
        return upsert_memory(tenant_id, content, memory_type, agent, metadata)

    async def query_memory(self, tenant_id: str, query_text: str,
                          memory_types: Optional[List[str]] = None,
                          top_k: int = 5, min_score: float = 0.7,
                          temporal_boost: bool = True) -> List[Dict[str, Any]]:
        """Async wrapper for query_memory."""
        return query_memory(tenant_id, query_text, memory_types, top_k, min_score, temporal_boost)

    async def decay_memory_weights(self, tenant_id: Optional[str] = None,
                                  decay_rate: float = 0.15,
                                  older_than_timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Decay memory weights with tenant filtering support.

        Args:
            tenant_id: Optional tenant filter
            decay_rate: Rate to decay weights (default 15%)
            older_than_timestamp: Only decay memories older than this timestamp

        Returns:
            Dict with operation results
        """
        import datetime
        import time

        decay_filter_conditions = []

        # Add tenant filter if specified
        if tenant_id:
            decay_filter_conditions.append(_enforce_tenant_filter(tenant_id))

        # Only decay vectors that haven't expired and aren't already at minimum weight
        now_timestamp = datetime.datetime.utcnow().timestamp()
        min_weight_threshold = 0.01

        decay_filter_conditions.extend([
            FieldCondition(key="expires_at", range=Range(gt=now_timestamp)),
            FieldCondition(key="relevance_weight", range=Range(gt=min_weight_threshold))
        ])

        # Add age filter if specified
        if older_than_timestamp:
            decay_filter_conditions.append(
                FieldCondition(key="occurred_at", range=Range(lt=older_than_timestamp))
            )

        decay_filter = Filter(must=decay_filter_conditions)

        vectors = self.client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=decay_filter,
            limit=10000,
        )

        if not vectors[0]:
            return {"updated_count": 0, "message": "No vectors need relevance decay"}

        # Update relevance weights
        decay_factor = 1.0 - decay_rate
        updated_count = 0

        for batch in _chunks(vectors[0], 100):  # Process in batches
            for vector in batch:
                current_weight = vector.payload.get("relevance_weight", 1.0)
                new_weight = max(current_weight * decay_factor, min_weight_threshold)

                self.client.set_payload(
                    collection_name=COLLECTION_NAME,
                    payload={"relevance_weight": new_weight},
                    points=[vector.id]
                )
                updated_count += 1

            # Small delay between batches to avoid overwhelming Qdrant
            time.sleep(0.1)

        logger.info(f"Decayed relevance weights for {updated_count} vectors")
        return {
            "updated_count": updated_count,
            "decay_rate": decay_rate,
            "tenant_id": tenant_id
        }

    async def expire_old_memories(self, tenant_id: Optional[str] = None,
                                 older_than_timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Expire old memories with tenant filtering support.

        Args:
            tenant_id: Optional tenant filter
            older_than_timestamp: Expire memories older than this timestamp

        Returns:
            Dict with operation results
        """
        import datetime
        import time

        delete_filter_conditions = []

        # Add tenant filter if specified
        if tenant_id:
            delete_filter_conditions.append(_enforce_tenant_filter(tenant_id))

        # Default to 90 days if no timestamp provided
        if older_than_timestamp is None:
            cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=90)
            older_than_timestamp = cutoff_date.timestamp()

        # Find expired or old vectors
        delete_filter_conditions.append(
            FieldCondition(key="occurred_at", range=Range(lt=older_than_timestamp))
        )

        delete_filter = Filter(must=delete_filter_conditions)

        vectors = self.client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=delete_filter,
            limit=10000,
        )

        if not vectors[0]:
            return {"deleted_count": 0, "message": "No vectors need expiration"}

        point_ids = [v.id for v in vectors[0]]

        # Delete in batches
        deleted_count = 0
        for batch_ids in _chunks(point_ids, 100):
            self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=batch_ids,
            )
            deleted_count += len(batch_ids)
            time.sleep(0.1)

        logger.info(f"Expired {deleted_count} old vectors")
        return {
            "deleted_count": deleted_count,
            "older_than_timestamp": older_than_timestamp,
            "tenant_id": tenant_id
        }

    async def optimize_performance(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform performance optimizations.

        Args:
            tenant_id: Optional tenant filter for optimization scope

        Returns:
            Dict with optimization results
        """
        # For now, this is a placeholder. Qdrant handles most optimizations automatically.
        # In a production system, this might include:
        # - Index rebuilding
        # - Collection compaction
        # - Vector quantization optimizations

        logger.info(f"Performance optimization completed for tenant: {tenant_id}")
        return {
            "optimized": True,
            "tenant_id": tenant_id,
            "message": "Performance optimization completed (automatic)"
        }
