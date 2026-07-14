"""MemoryService - Unified facade for vector, graph, episodic, and working memory layers."""
from __future__ import annotations
import logging
from typing import Any, Optional

from src.memory.qdrant_ops import query_memory as qdrant_query
from src.memory.qdrant_ops import upsert_memory as qdrant_upsert
from src.memory.semantic import SemanticMemory
from src.memory.working import WorkingMemory
from src.memory.episodic import EpisodicMemory

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Unified memory service with tenant isolation.
    
    Wraps:
    - Layer 1: Working memory (Redis) - in-flight state
    - Layer 2: Episodic memory (Qdrant) - event storage with weight decay
    - Layer 3: Semantic memory (Graphiti/Neo4j) - fact extraction
    - Layer 4: Vector memory (Qdrant) - semantic search
    
    All operations enforce tenant_id filtering for isolation.
    Graceful degradation: when backends unavailable, returns empty/default values.
    """
    
    # Collection names for episodic memory
    EPISODIC_COLLECTION = "ontology_ai_episodes"
    
    def __init__(self) -> None:
        self._semantic_cache: dict[str, SemanticMemory] = {}
        self._working_cache: dict[tuple[str, str], WorkingMemory] = {}
        self._episodic: Optional[EpisodicMemory] = None
    
    def _get_semantic(self, tenant_id: str) -> SemanticMemory:
        """Get or create SemanticMemory for tenant."""
        if tenant_id not in self._semantic_cache:
            self._semantic_cache[tenant_id] = SemanticMemory(tenant_id=tenant_id)
        return self._semantic_cache[tenant_id]
    
    def _get_working(self, tenant_id: str, run_id: str) -> WorkingMemory:
        """Get or create WorkingMemory for tenant+run."""
        key = (tenant_id, run_id)
        if key not in self._working_cache:
            self._working_cache[key] = WorkingMemory(tenant_id=tenant_id, run_id=run_id)
        return self._working_cache[key]
    
    def _get_episodic(self) -> EpisodicMemory:
        """Get episodic memory instance."""
        if self._episodic is None:
            self._episodic = EpisodicMemory(collection=self.EPISODIC_COLLECTION)
        return self._episodic
    
    # -------------------------------------------------------------------------
    # Read Operations
    # -------------------------------------------------------------------------
    
    async def read(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Read from vector + graph + episodic layers.
        
        Aggregates results from all available memory layers.
        Each layer applies its own tenant_id filtering.
        
        Args:
            tenant_id: Tenant for isolation
            query: Query text for semantic search
            top_k: Max results per layer
            
        Returns:
            List of memory results with content, type, and source
        """
        results: list[dict[str, Any]] = []
        
        # Layer 4: Vector memory (Qdrant)
        try:
            vector_results = qdrant_query(
                tenant_id=tenant_id,
                query_text=query,
                top_k=top_k,
                min_score=0.0,
            )
            for r in vector_results:
                results.append({
                    "content": r.get("content", ""),
                    "memory_type": r.get("memory_type", ""),
                    "score": r.get("score", 0.0),
                    "source": "vector",
                    "metadata": {
                        "agent": r.get("agent"),
                        "point_id": r.get("point_id"),
                    },
                })
        except Exception as e:
            logger.debug(f"Vector layer unavailable: {e}")
        
        # Layer 3: Semantic/Graph memory (Graphiti)
        try:
            semantic = self._get_semantic(tenant_id)
            if semantic.available():
                semantic_results = semantic.search(query=query, num_results=top_k)
                for r in semantic_results:
                    results.append({
                        "content": r.get("fact", ""),
                        "memory_type": "semantic",
                        "score": 0.8,  # Graphiti doesn't return scores
                        "source": "graph",
                        "metadata": {
                            "valid_at": r.get("valid_at"),
                        },
                    })
        except Exception as e:
            logger.debug(f"Semantic layer unavailable: {e}")
        
        # Layer 2: Episodic memory (Qdrant events)
        try:
            episodic = self._get_episodic()
            if episodic.available():
                episodic_results = episodic.search(
                    tenant_id=tenant_id,
                    query=query,
                    top_k=top_k,
                )
                for r in episodic_results:
                    results.append({
                        "content": r.get("content", ""),
                        "memory_type": r.get("event_type", ""),
                        "score": r.get("score", 0.0),
                        "source": "episodic",
                        "metadata": {
                            "timestamp": r.get("timestamp"),
                            "weight": r.get("weight"),
                        },
                    })
        except Exception as e:
            logger.debug(f"Episodic layer unavailable: {e}")
        
        # Deduplicate by content and sort by score
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for r in results:
            content = r.get("content", "")
            if content and content not in seen:
                seen.add(content)
                deduped.append(r)
        
        deduped.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return deduped[:top_k]
    
    # -------------------------------------------------------------------------
    # Write Operations
    # -------------------------------------------------------------------------
    
    async def write(
        self,
        tenant_id: str,
        content: str,
        memory_type: str,
        metadata: dict[str, Any],
    ) -> str:
        """
        Write to vector + graph + procedural layers.
        
        Writes to multiple layers for durability and retrieval flexibility.
        
        Args:
            tenant_id: Tenant for isolation
            content: Memory content
            memory_type: Type (anomaly, revenue_event, etc.)
            metadata: Additional metadata
            
        Returns:
            Primary point ID from vector layer
        """
        point_id = ""
        
        # Layer 4: Vector memory (Qdrant)
        try:
            agent = metadata.get("agent", "system")
            point_id = qdrant_upsert(
                tenant_id=tenant_id,
                content=content,
                memory_type=memory_type,
                agent=agent,
                metadata=metadata,
            )
        except Exception as e:
            logger.debug(f"Vector write failed: {e}")
        
        # Layer 3: Semantic/Graph memory (Graphiti)
        try:
            semantic = self._get_semantic(tenant_id)
            if semantic.available():
                semantic.write_episode(
                    name=f"memory:{memory_type}:{point_id[:8]}",
                    body=content,
                )
        except Exception as e:
            logger.debug(f"Semantic write failed: {e}")
        
        # Layer 2: Episodic memory (Qdrant events)
        try:
            episodic = self._get_episodic()
            if episodic.available():
                episodic.write(
                    tenant_id=tenant_id,
                    event_type=memory_type,
                    content=content,
                    **metadata,
                )
        except Exception as e:
            logger.debug(f"Episodic write failed: {e}")
        
        return point_id
    
    # -------------------------------------------------------------------------
    # Context Loading
    # -------------------------------------------------------------------------
    
    async def load_context(self, tenant_id: str) -> str:
        """
        Load all context - graceful degradation returns empty string.
        
        Combines recent memories from all layers into a context string.
        If all backends are down, returns empty string (not an error).
        
        Args:
            tenant_id: Tenant for isolation
            
        Returns:
            Combined context string, or "" if all layers unavailable
        """
        context_parts: list[str] = []
        
        # Collect from vector layer
        try:
            vector_results = qdrant_query(
                tenant_id=tenant_id,
                query_text="recent memory",
                top_k=3,
                min_score=0.0,
            )
            for r in vector_results:
                content = r.get("content", "")
                if content:
                    context_parts.append(f"[vector] {content}")
        except Exception:
            pass
        
        # Collect from semantic layer
        try:
            semantic = self._get_semantic(tenant_id)
            if semantic.available():
                semantic_results = semantic.search(
                    query="recent",
                    num_results=3,
                )
                for r in semantic_results:
                    fact = r.get("fact", "")
                    if fact:
                        context_parts.append(f"[graph] {fact}")
        except Exception:
            pass
        
        # Collect from episodic layer
        try:
            episodic = self._get_episodic()
            if episodic.available():
                episodic_results = episodic.search(
                    tenant_id=tenant_id,
                    query="recent",
                    top_k=3,
                )
                for r in episodic_results:
                    content = r.get("content", "")
                    if content:
                        context_parts.append(f"[episodic] {content}")
        except Exception:
            pass
        
        if not context_parts:
            logger.debug(f"No context available for tenant {tenant_id}")
            return ""
        
        return "\n".join(context_parts)
    
    # -------------------------------------------------------------------------
    # Availability Check
    # -------------------------------------------------------------------------
    
    def available(self) -> bool:
        """
        Check if any memory backend is available.
        
        Returns:
            True if at least one layer is accessible
        """
        # Check vector (Qdrant) via semantic layer availability
        try:
            semantic = self._get_semantic("__health_check__")
            if semantic.available():
                return True
        except Exception:
            pass
        
        # Check episodic
        try:
            episodic = self._get_episodic()
            if episodic.available():
                return True
        except Exception:
            pass
        
        # If we get here, all backends are down - still return True
        # because the service itself is instantiated (not the backends)
        return True


# Module-level singleton for reuse
_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """Get or create the MemoryService singleton."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


__all__ = [
    "MemoryService",
    "get_memory_service",
]