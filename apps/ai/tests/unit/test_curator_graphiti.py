"""Tests for Curator → Graphiti write - TDD Red phase."""
import pytest
from unittest.mock import patch, MagicMock


class TestCuratorGraphitiWrite:
    """Curator updates Graphiti Strategy confidence scores from feedback."""

    @patch("src.memory.semantic.SemanticMemory")
    def test_acknowledge_increments_strategy_confidence(self, MockSM):
        """Acknowledged feedback should increment strategy confidence by +1.0."""
        from src.agents.cofounder.curator import update_strategy_confidence

        mock_mem = MagicMock()
        MockSM.return_value = mock_mem
        result = update_strategy_confidence("test-001", "finance", "acknowledged", 1.0)
        assert result.success is True
        assert result.confidence_delta == 1.0

    @patch("src.memory.semantic.SemanticMemory")
    def test_dispute_decrements_strategy_confidence(self, MockSM):
        """Disputed feedback should decrement strategy confidence by -1.0."""
        from src.agents.cofounder.curator import update_strategy_confidence

        mock_mem = MagicMock()
        MockSM.return_value = mock_mem
        result = update_strategy_confidence("test-001", "finance", "disputed", -1.0)
        assert result.success is True
        assert result.confidence_delta == -1.0

    def test_graphiti_unavailable_graceful_fallback(self):
        """Graphiti unavailable should not crash - graceful fallback."""
        from src.agents.cofounder.curator import update_strategy_confidence

        result = update_strategy_confidence("test-001", "finance", "acknowledged", 1.0)
        assert result is not None