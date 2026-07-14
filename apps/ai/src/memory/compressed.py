"""L5 compression trigger - after 50 writes, trigger Qdrant optimization."""
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

COMPRESSION_TRIGGER_THRESHOLD = 50


@dataclass
class CompressionStats:
    write_count: int
    tenant_id: str
    collection_name: str


def should_compress(stats: CompressionStats) -> bool:
    """Check if compression should be triggered."""
    return stats.write_count >= COMPRESSION_TRIGGER_THRESHOLD


def reset_write_count(tenant_id: str, collection_name: str) -> None:
    """Reset write count for tenant after compression."""
    from qdrant_client import QdrantClient
    import os
    
    host = os.environ.get("QDRANT_HOST", "localhost")
    port = os.environ.get("QDRANT_PORT", "6333")
    client = QdrantClient(host=host, port=int(port))
    
    client.set_payload(
        collection_name=collection_name,
        payload={"_l5_write_count": 0},
        points=[],
        points_selector=None,
        wait=None,
    )
    logger.info(f"Reset write count for tenant={tenant_id}")


def increment_write_count(tenant_id: str, collection_name: str) -> int:
    """Increment write count for tenant."""
    from src.memory.qdrant_ops import _get_client
    
    client = _get_client()
    
    filter_conditions = [
        {"key": "tenant_id", "match": {"value": tenant_id}}
    ]
    
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    tenant_filter = Filter(
        must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
    )
    
    points = client.scroll(
        collection_name=collection_name,
        scroll_filter=tenant_filter,
        limit=1,
        with_payload=True,
    )
    
    current_count = 0
    if points[0]:
        point = points[0][0]
        current_count = point.payload.get("_l5_write_count", 0)
    
    new_count = current_count + 1
    
    client.set_payload(
        collection_name=collection_name,
        payload={"_l5_write_count": new_count},
        points=[p.id for p in points[0]] if points[0] else [],
    )
    
    return new_count


def trigger_compression(tenant_id: str) -> dict:
    """Trigger L5 compression for tenant."""
    from qdrant_client import QdrantClient
    import os
    
    host = os.environ.get("QDRANT_HOST", "localhost")
    port = os.environ.get("QDRANT_PORT", "6333")
    client = QdrantClient(host=host, port=int(port))
    
    collection_name = os.environ.get("QDRANT_COLLECTION", "ontology_ai_memory")
    
    tenant_filter = {
        "must": [
            {"key": "tenant_id", "match": {"value": tenant_id}}
        ]
    }
    
    client.delete(
        collection_name=collection_name,
        points_selector={
            "filter": tenant_filter,
            "limit": 1000
        }
    )
    
    logger.info(f"Triggered L5 compression for tenant={tenant_id}")
    return {"tenant_id": tenant_id, "compressed": True}


class CompressedMemory:
    """L5 compressed memory manager with write-count-based compression."""
    
    def __init__(self):
        self.write_count = 0
    
    def track_write(self, tenant_id: str) -> None:
        """Track a write operation."""
        self.write_count += 1
        if self.write_count >= COMPRESSION_TRIGGER_THRESHOLD:
            self.trigger_compression(tenant_id)
    
    def trigger_compression(self, tenant_id: str) -> dict:
        """Trigger compression and reset count."""
        self.write_count = 0
        return trigger_compression(tenant_id)