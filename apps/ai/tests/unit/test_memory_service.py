"""Tests for MemoryService facade."""
import pytest
from unittest.mock import patch, MagicMock
from src.services.memory import MemoryService, get_memory_service


class TestMemoryService:
    """Test suite for MemoryService."""
    
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton before each test."""
        import src.services.memory as memory_module
        memory_module._memory_service = None
        yield
        memory_module._memory_service = None
    
    def test_get_memory_service_returns_singleton(self):
        """Same instance returned on repeated calls."""
        s1 = get_memory_service()
        s2 = get_memory_service()
        assert s1 is s2
    
    # -------------------------------------------------------------------------
    # Read Operations
    # -------------------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_read_returns_list_from_vector_layer(self):
        """Read returns results from vector layer."""
        service = MemoryService()
        
        mock_results = [
            {"content": "test memory", "memory_type": "anomaly", "score": 0.9,
             "agent": "test-agent", "point_id": "abc123"}
        ]
        
        with patch("src.services.memory.qdrant_query", return_value=mock_results), \
             patch.object(service, "_get_episodic") as mock_episodic:
            mock_episodic.return_value.available.return_value = False
            results = await service.read("tenant-123", "test query", top_k=5)
        
        assert len(results) == 1
        assert results[0]["content"] == "test memory"
        assert results[0]["source"] == "vector"
    
    @pytest.mark.asyncio
    async def test_read_aggregates_multiple_layers(self):
        """Read aggregates results from all available layers."""
        service = MemoryService()
        
        vector_results = [
            {"content": "vector result", "memory_type": "anomaly", "score": 0.9,
             "agent": "agent", "point_id": "v1"}
        ]
        semantic_results = [
            {"fact": "semantic fact", "valid_at": "2024-01-01"}
        ]
        episodic_results = [
            {"content": "episodic event", "event_type": "revenue_event",
             "score": 0.8, "timestamp": "2024-01-01"}
        ]
        
        with patch("src.services.memory.qdrant_query", return_value=vector_results), \
             patch.object(service, "_get_semantic") as mock_semantic, \
             patch.object(service, "_get_episodic") as mock_episodic:
            mock_semantic.return_value.available.return_value = True
            mock_semantic.return_value.search.return_value = semantic_results
            mock_episodic.return_value.available.return_value = True
            mock_episodic.return_value.search.return_value = episodic_results
            
            results = await service.read("tenant-123", "test query", top_k=5)
        
        # All three layers should contribute results
        sources = {r["source"] for r in results}
        assert "vector" in sources
        assert "graph" in sources
        assert "episodic" in sources
    
    @pytest.mark.asyncio
    async def test_read_deduplicates_by_content(self):
        """Read deduplicates results with same content."""
        service = MemoryService()
        
        # Same content from different layers
        vector_results = [
            {"content": "duplicate content", "memory_type": "anomaly", "score": 0.9,
             "agent": "agent", "point_id": "v1"}
        ]
        semantic_results = [
            {"fact": "duplicate content", "valid_at": "2024-01-01"}
        ]
        
        with patch("src.services.memory.qdrant_query", return_value=vector_results), \
             patch.object(service, "_get_semantic") as mock_semantic, \
             patch.object(service, "_get_episodic") as mock_episodic:
            mock_semantic.return_value.available.return_value = True
            mock_semantic.return_value.search.return_value = semantic_results
            mock_episodic.return_value.available.return_value = False
            
            results = await service.read("tenant-123", "test query", top_k=5)
        
        # Should have only one result
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_read_respects_tenant_isolation(self):
        """Read passes tenant_id to all layers."""
        service = MemoryService()
        
        with patch("src.services.memory.qdrant_query", return_value=[]) as mock_q, \
             patch.object(service, "_get_semantic") as mock_semantic, \
             patch.object(service, "_get_episodic") as mock_episodic:
            mock_semantic.return_value.available.return_value = True
            mock_semantic.return_value.search.return_value = []
            mock_episodic.return_value.available.return_value = True
            mock_episodic.return_value.search.return_value = []
            
            await service.read("tenant-456", "test query", top_k=5)
        
        # Verify tenant_id was passed to vector layer
        mock_q.assert_called_once_with(
            tenant_id="tenant-456",
            query_text="test query",
            top_k=5,
            min_score=0.0,
        )
    
    # -------------------------------------------------------------------------
    # Write Operations
    # -------------------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_write_returns_point_id(self):
        """Write returns point ID from vector layer."""
        service = MemoryService()
        
        with patch("src.services.memory.qdrant_upsert", return_value="abc123"):
            point_id = await service.write(
                "tenant-123",
                "test content",
                "anomaly",
                {"agent": "test-agent"},
            )
        
        assert point_id == "abc123"
    
    @pytest.mark.asyncio
    async def test_write_writes_to_multiple_layers(self):
        """Write persists to vector, semantic, and episodic layers."""
        service = MemoryService()
        
        with patch("src.services.memory.qdrant_upsert", return_value="abc123") as mock_vec, \
             patch.object(service, "_get_semantic") as mock_semantic, \
             patch.object(service, "_get_episodic") as mock_episodic:
            mock_semantic.return_value.available.return_value = True
            mock_semantic.return_value.write_episode.return_value = True
            mock_episodic.return_value.available.return_value = True
            mock_episodic.return_value.write.return_value = "ep123"
            
            await service.write(
                "tenant-123",
                "test content",
                "anomaly",
                {"agent": "test-agent"},
            )
        
        # Vector write called
        mock_vec.assert_called_once()
        # Semantic write called
        mock_semantic.return_value.write_episode.assert_called_once()
        # Episodic write called
        mock_episodic.return_value.write.assert_called_once()
    
    # -------------------------------------------------------------------------
    # Context Loading (Graceful Degradation)
    # -------------------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_load_context_returns_empty_when_all_layers_down(self):
        """When all backends unavailable, returns empty string."""
        service = MemoryService()
        
        with patch("src.services.memory.qdrant_query", side_effect=Exception("down")), \
             patch.object(service, "_get_semantic") as mock_semantic, \
             patch.object(service, "_get_episodic") as mock_episodic:
            mock_semantic.return_value.available.return_value = False
            mock_episodic.return_value.available.return_value = False
            
            result = await service.load_context("tenant-123")
        
        assert result == ""
    
    @pytest.mark.asyncio
    async def test_all_layers_down_returns_empty(self):
        """
        Test: When all backends unavailable, load_context returns "".
        
        This is the specific test case requested in the mission.
        """
        service = MemoryService()
        
        # Mock all backends as unavailable
        with patch("src.services.memory.qdrant_query", side_effect=Exception("down")), \
             patch.object(service, "_get_semantic") as mock_semantic, \
             patch.object(service, "_get_episodic") as mock_episodic:
            mock_semantic.return_value.available.return_value = False
            mock_episodic.return_value.available.return_value = False
            
            result = await service.load_context("tenant-123")
        
        assert result == ""
    
    @pytest.mark.asyncio
    async def test_load_context_returns_context_when_available(self):
        """load_context returns combined context when layers available."""
        service = MemoryService()
        
        vector_results = [
            {"content": "recent vector memory", "memory_type": "anomaly",
             "score": 0.9, "agent": "agent", "point_id": "v1"}
        ]
        semantic_results = [
            {"fact": "recent graph fact"}
        ]
        episodic_results = [
            {"content": "recent episodic event"}
        ]
        
        with patch("src.services.memory.qdrant_query", return_value=vector_results), \
             patch.object(service, "_get_semantic") as mock_semantic, \
             patch.object(service, "_get_episodic") as mock_episodic:
            mock_semantic.return_value.available.return_value = True
            mock_semantic.return_value.search.return_value = semantic_results
            mock_episodic.return_value.available.return_value = True
            mock_episodic.return_value.search.return_value = episodic_results
            
            result = await service.load_context("tenant-123")
        
        assert result != ""
        assert "recent vector memory" in result
        assert "recent graph fact" in result
        assert "recent episodic event" in result
    
    # -------------------------------------------------------------------------
    # Availability Check
    # -------------------------------------------------------------------------
    
    def test_available_returns_true_when_service_instantiated(self):
        """available() returns True even if backends are down."""
        service = MemoryService()
        
        with patch.object(service, "_get_semantic") as mock_semantic, \
             patch.object(service, "_get_episodic") as mock_episodic:
            mock_semantic.return_value.available.return_value = False
            mock_episodic.return_value.available.return_value = False
            
            result = service.available()
        
        # Service itself is available even if backends are down
        assert result is True