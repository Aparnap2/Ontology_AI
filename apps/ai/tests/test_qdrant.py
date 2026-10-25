"""Tests for Qdrant Vector Service."""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestQdrantService:
    """Tests for the QdrantService class."""

    def test_qdrant_config(self):
        """Test Qdrant configuration."""
        from src.config import QdrantConfig

        config = QdrantConfig(
            url="http://localhost:6333",
            collection="feedback_items",
            similarity_threshold=0.85,
        )

        assert config.url == "http://localhost:6333"
        assert config.collection == "feedback_items"
        assert config.similarity_threshold == 0.85

    @pytest.mark.asyncio
    async def test_check_duplicate_not_duplicate(self):
        """Test duplicate check when no duplicate exists."""
        from src.services.qdrant import QdrantService

        with patch.object(QdrantService, "__init__", lambda x: None):
            service = QdrantService()
            service.config = MagicMock()
            service.config.url = "http://localhost:6333"
            service.config.collection = "feedback_items"
            service.config.similarity_threshold = 0.85
            service._collection_initialized = True
            service.client = AsyncMock()

            # Mock get_embedding
            service.get_embedding = AsyncMock(return_value=[0.1] * 768)

            # Mock query_points returning no results
            service.client.query_points = AsyncMock(
                return_value=SimpleNamespace(points=[])
            )

            is_duplicate, score = await service.check_duplicate("Test feedback")

            assert is_duplicate is False
            assert score == 0.0

    @pytest.mark.asyncio
    async def test_check_duplicate_found(self):
        """Test duplicate check when duplicate is found."""
        from src.services.qdrant import QdrantService

        with patch.object(QdrantService, "__init__", lambda x: None):
            service = QdrantService()
            service.config = MagicMock()
            service.config.url = "http://localhost:6333"
            service.config.collection = "feedback_items"
            service.config.similarity_threshold = 0.85
            service._collection_initialized = True
            service.client = AsyncMock()

            service.get_embedding = AsyncMock(return_value=[0.1] * 768)

            # Mock query_points returning a match
            mock_point = SimpleNamespace(id="test-id", score=0.92, payload={}, version=1)
            service.client.query_points = AsyncMock(
                return_value=SimpleNamespace(points=[mock_point])
            )

            is_duplicate, score = await service.check_duplicate("Test feedback")

            assert is_duplicate is True
            assert score == 0.92

    @pytest.mark.asyncio
    async def test_ensure_collection(self):
        """Test collection creation."""
        from src.services.qdrant import QdrantService

        with patch.object(QdrantService, "__init__", lambda x: None):
            service = QdrantService()
            service.config = MagicMock()
            service.config.url = "http://localhost:6333"
            service.config.collection = "feedback_items"
            service._collection_initialized = False
            service.client = AsyncMock()

            # Mock empty collections
            mock_collections = MagicMock()
            mock_collections.collections = []
            service.client.get_collections = AsyncMock(return_value=mock_collections)
            service.client.create_collection = AsyncMock()

            await service.ensure_collection()

            service.client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_feedback(self):
        """Test feedback indexing."""
        from src.services.qdrant import QdrantService

        with patch.object(QdrantService, "__init__", lambda x: None):
            service = QdrantService()
            service.config = MagicMock()
            service.config.url = "http://localhost:6333"
            service.config.collection = "feedback_items"
            service._collection_initialized = True
            service.client = AsyncMock()

            service.get_embedding = AsyncMock(return_value=[0.1] * 768)
            service.client.upsert = AsyncMock()

            await service.index_feedback(
                feedback_id="test-123",
                text="Test content",
                metadata={"source": "discord"},
            )

            service.client.upsert.assert_called_once()
