"""Qdrant Vector Service for semantic duplicate detection."""

import os
import uuid
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from src import config

logger = structlog.get_logger(__name__)


class QdrantService:
    """Service for managing vector embeddings and similarity search."""

    def __init__(self):
        """Initialize Qdrant client."""
        self.config = config.get_config().qdrant
        self.client = AsyncQdrantClient(url=self.config.url)
        self._collection_initialized = False

    async def ensure_collection(self) -> None:
        """Ensure the feedback collection exists with proper configuration."""
        if self._collection_initialized:
            return

        collections = await self.client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if self.config.collection not in collection_names:
            logger.info("Creating Qdrant collection", collection=self.config.collection)
            await self.client.create_collection(
                collection_name=self.config.collection,
                vectors_config={
                    "content": {
                        "size": 2048,
                        "distance": "Cosine",
                    }
                },
            )
            logger.info("Qdrant collection created", collection=self.config.collection)

        self._collection_initialized = True

    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding for text using OpenRouter's embeddings API.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (2048 dimensions)
        """
        openrouter_config = config.get_config().openrouter
        api_key = openrouter_config.api_key or os.environ.get("OPENROUTER_API_KEY", "")
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            response = await http_client.post(
                f"{openrouter_config.base_url}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": openrouter_config.embedding_model,
                    "input": text,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

    async def check_duplicate(self, text: str) -> tuple[bool, float]:
        """Check if text is semantically similar to existing feedback.

        Args:
            text: Feedback text to check

        Returns:
            Tuple of (is_duplicate: bool, similarity_score: float)
        """
        await self.ensure_collection()

        # Get embedding for the text
        embedding = await self.get_embedding(text)

        # Search for similar items
        search_results = await self.client.query_points(
            collection_name=self.config.collection,
            query=embedding,
            using="content",
            limit=1,
            with_payload=True,
        )
        search_results = search_results.points

        if search_results:
            score = search_results[0].score
            is_duplicate = score >= self.config.similarity_threshold
            logger.info(
                "Duplicate check completed",
                text_preview=text[:50],
                score=score,
                is_duplicate=is_duplicate,
            )
            return is_duplicate, score

        return False, 0.0

    async def index_feedback(
        self,
        feedback_id: str,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """Index feedback for future duplicate detection.

        Args:
            feedback_id: Unique identifier for the feedback
            text: Feedback text content
            metadata: Optional additional metadata
        """
        await self.ensure_collection()

        embedding = await self.get_embedding(text)

        point = PointStruct(
            id=uuid.uuid5(uuid.NAMESPACE_DNS, feedback_id),
            vector={"content": embedding},
            payload={
                "feedback_id": feedback_id,
                "text": text,
                **(metadata or {}),
            },
        )

        await self.client.upsert(
            collection_name=self.config.collection,
            points=[point],
        )

        logger.info("Feedback indexed", feedback_id=feedback_id)

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        await self.client.close()


# Global service instance
_qdrant_service: QdrantService | None = None


async def get_qdrant_service() -> QdrantService:
    """Get the global Qdrant service instance."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
