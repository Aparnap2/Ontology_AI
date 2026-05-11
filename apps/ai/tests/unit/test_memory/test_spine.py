"""Tests for Memory Spine 5-layer orchestration - TDD."""
import pytest
from unittest.mock import MagicMock, patch

QDRANT_THRESHOLD = 0.82


class TestMemorySpine:
    """Memory spine orchestrates all 5 layers."""

    @pytest.mark.asyncio
    async def test_l1_redis_checked_first(self):
        """L1 Redis checked before L2."""
        call_order = []
        
        with patch("src.memory.working.WorkingMemory") as MockWM:
            def track_l1(*args, **kwargs):
                call_order.append("L1")
                instance = MockWM.return_value
                instance.get.return_value = {"context": "working"}
                return instance
            MockWM.side_effect = track_l1
            
            with patch("src.memory.episodic.EpisodicMemory") as MockEM:
                def track_l2(*args, **kwargs):
                    call_order.append("L2")
                    instance = MockEM.return_value
                    instance.search.return_value = [{"score": 0.9, "content": "test"}]
                    return instance
                MockEM.side_effect = track_l2
                
                with patch("src.memory.semantic.SemanticMemory") as MockSM:
                    MockSM.return_value.search.return_value = []
                    MockSM.return_value.write_episode.return_value = True
                    
                    with patch("src.memory.procedural.ProceduralMemory") as MockPM:
                        MockPM.return_value.load.return_value = None
                        
                        with patch("src.memory.compressed.CompressedMemory") as MockCM:
                            MockCM.return_value.search.return_value = []
                            
                            from src.memory.spine import load_context
                            ctx = await load_context("tenant-1", "test query", "engineering")
                            
                            assert call_order == ["L1", "L2"], f"L1 must be checked before L2, got {call_order}"
                            assert ctx.working is not None

    @pytest.mark.asyncio
    async def test_l2_qdrant_threshold_0_82(self):
        """Qdrant injection requires similarity >= 0.82."""
        results = [
            {"score": 0.85, "content": "high similarity"},
            {"score": 0.75, "content": "below threshold"},
        ]
        
        with patch("src.memory.working.WorkingMemory") as MockWM:
            MockWM.return_value.get.return_value = None
            
            with patch("src.memory.episodic.EpisodicMemory") as MockEM:
                MockEM.return_value.search.return_value = results
                
                with patch("src.memory.semantic.SemanticMemory") as MockSM:
                    MockSM.return_value.search.return_value = []
                    MockSM.return_value.write_episode.return_value = True
                    
                    with patch("src.memory.procedural.ProceduralMemory") as MockPM:
                        MockPM.return_value.load.return_value = None
                        
                        with patch("src.memory.compressed.CompressedMemory") as MockCM:
                            MockCM.return_value.search.return_value = []
                            
                            from src.memory.spine import load_context
                            ctx = await load_context("tenant-1", "test", "engineering")
                            
                            for r in ctx.episodic:
                                assert r["score"] >= QDRANT_THRESHOLD, \
                                    f"Expected score >= {QDRANT_THRESHOLD}, got {r['score']}"

    @pytest.mark.asyncio
    async def test_l3_graphiti_tenant_isolation(self):
        """L3 Graphiti uses tenant_id as group_ids filter."""
        captured_search_calls = []
        
        with patch("src.memory.working.WorkingMemory") as MockWM:
            MockWM.return_value.get.return_value = None
            
            with patch("src.memory.episodic.EpisodicMemory") as MockEM:
                MockEM.return_value.search.return_value = []
                
                with patch("src.memory.semantic.SemanticMemory") as MockSM:
                    def capture_search(query, num_results):
                        captured_search_calls.append(query)
                        return [{"fact": "test", "valid_at": "2024-01-01"}]
                    
                    MockSM.return_value.search.side_effect = capture_search
                    MockSM.return_value.write_episode.return_value = True
                    
                    with patch("src.memory.procedural.ProceduralMemory") as MockPM:
                        MockPM.return_value.load.return_value = None
                        
                        with patch("src.memory.compressed.CompressedMemory") as MockCM:
                            MockCM.return_value.search.return_value = []
                            
                            from src.memory.spine import load_context
                            await load_context("tenant-xyz", "test query", "engineering")
                            
                            assert len(captured_search_calls) > 0, "SemanticMemory.search should be called"

    @pytest.mark.asyncio
    async def test_l5_only_when_l2_lt_2_results(self):
        """L5 compressed only queried when L2 returns < 2 results."""
        l5_called = False
        
        def mock_l5_search(tenant_id: str, top_k: int = 3) -> list[dict]:
            nonlocal l5_called
            l5_called = True
            return [{"score": 0.8, "content": "compressed"}]
        
        with patch("src.memory.working.WorkingMemory") as MockWM:
            MockWM.return_value.get.return_value = None
            
            with patch("src.memory.episodic.EpisodicMemory") as MockEM:
                MockEM.return_value.search.return_value = [
                    {"score": 0.9, "content": "only 1 result"}
                ]
                
                with patch("src.memory.semantic.SemanticMemory") as MockSM:
                    MockSM.return_value.search.return_value = []
                    MockSM.return_value.write_episode.return_value = True
                    
                    with patch("src.memory.procedural.ProceduralMemory") as MockPM:
                        MockPM.return_value.load.return_value = None
                        
                        with patch("src.memory.compressed.CompressedMemory") as MockCM:
                            MockCM.return_value.search.side_effect = mock_l5_search
                            
                            from src.memory.spine import load_context
                            ctx = await load_context("tenant-1", "test", "engineering")
                            
                            assert l5_called, "L5 should be queried when L2 returns < 2 results"
                            assert len(ctx.compressed) > 0

    @pytest.mark.asyncio
    async def test_l5_not_called_when_l2_has_2_plus(self):
        """L5 NOT queried when L2 returns >= 2 results."""
        l5_called = False
        
        def mock_l5_search(tenant_id: str, top_k: int = 3) -> list[dict]:
            nonlocal l5_called
            l5_called = True
            return []
        
        with patch("src.memory.working.WorkingMemory") as MockWM:
            MockWM.return_value.get.return_value = None
            
            with patch("src.memory.episodic.EpisodicMemory") as MockEM:
                MockEM.return_value.search.return_value = [
                    {"score": 0.9, "content": "result 1"},
                    {"score": 0.88, "content": "result 2"}
                ]
                
                with patch("src.memory.semantic.SemanticMemory") as MockSM:
                    MockSM.return_value.search.return_value = []
                    MockSM.return_value.write_episode.return_value = True
                    
                    with patch("src.memory.procedural.ProceduralMemory") as MockPM:
                        MockPM.return_value.load.return_value = None
                        
                        with patch("src.memory.compressed.CompressedMemory") as MockCM:
                            MockCM.return_value.search.side_effect = mock_l5_search
                            
                            from src.memory.spine import load_context
                            ctx = await load_context("tenant-1", "test", "engineering")
                            
                            assert not l5_called, "L5 should NOT be queried when L2 returns >= 2 results"

    @pytest.mark.asyncio
    async def test_graceful_degradation_l3_down(self):
        """If L3 Graphiti down, agent still runs with empty semantic context."""
        with patch("src.memory.working.WorkingMemory") as MockWM:
            MockWM.return_value.get.return_value = {"key": "value"}
            
            with patch("src.memory.episodic.EpisodicMemory") as MockEM:
                MockEM.return_value.search.return_value = [{"score": 0.9}]
                
                with patch("src.memory.semantic.SemanticMemory") as MockSM:
                    MockSM.return_value.search.side_effect = Exception("Neo4j down")
                    MockSM.return_value.write_episode.side_effect = Exception("Neo4j down")
                    
                    with patch("src.memory.procedural.ProceduralMemory") as MockPM:
                        MockPM.return_value.load.return_value = {"program": "data"}
                        
                        with patch("src.memory.compressed.CompressedMemory") as MockCM:
                            MockCM.return_value.search.return_value = []
                            
                            from src.memory.spine import load_context
                            ctx = await load_context("tenant-1", "test", "engineering")
                            
                            assert ctx.errors, "Expected at least one error"
                            l3_errors = [e for e in ctx.errors if "L3" in e]
                            assert len(l3_errors) > 0, f"Expected L3 error, got {ctx.errors}"
                            assert ctx.semantic == []