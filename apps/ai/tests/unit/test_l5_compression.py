"""Tests for L5 compression trigger - TDD Red phase."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


class TestL5CompressionTrigger:
    """L5 compression triggers after 50 writes."""

    def test_compression_triggered_at_50_writes(self):
        """After 50 writes, compression is triggered."""
        from src.memory.compressed import should_compress, CompressionStats
        stats = CompressionStats(write_count=50, tenant_id="test-001", collection_name="test")
        assert should_compress(stats) == True

    def test_no_compression_before_50_writes(self):
        """Before 50 writes, no compression."""
        from src.memory.compressed import should_compress, CompressionStats
        stats = CompressionStats(write_count=49, tenant_id="test-001", collection_name="test")
        assert should_compress(stats) == False

    def test_compressed_memory_triggers_at_threshold(self):
        """CompressedMemory class triggers compression when write_count reaches 50."""
        from src.memory.compressed import CompressedMemory
        with patch("src.memory.compressed.trigger_compression") as mock_trigger:
            mock_trigger.return_value = {"tenant_id": "test-001", "compressed": True}
            cm = CompressedMemory()
            for i in range(49):
                cm.write_count += 1
            assert cm.write_count == 49
            cm.track_write("test-001")
            mock_trigger.assert_called_once_with("test-001")
            assert cm.write_count == 0

    def test_compressed_memory_resets_after_compression(self):
        """Write count resets to 0 after compression."""
        from src.memory.compressed import CompressedMemory
        with patch("src.memory.compressed.trigger_compression") as mock_trigger:
            mock_trigger.return_value = {"tenant_id": "test-001", "compressed": True}
            cm = CompressedMemory()
            cm.write_count = 50
            cm.trigger_compression("test-001")
            assert cm.write_count == 0