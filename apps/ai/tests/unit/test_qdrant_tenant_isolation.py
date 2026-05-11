"""Tests for Qdrant tenant isolation."""
import pytest
from unittest.mock import MagicMock, patch
from src.memory.qdrant_ops import _enforce_tenant_filter, query_memory


class TestQdrantTenantIsolation:
    """Qdrant tenant isolation tests."""

    def test_enforce_tenant_filter_always_includes_tenant_id(self):
        """tenant_id filter is always in the must clause."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        filter_obj = _enforce_tenant_filter("test-tenant-123")
        assert isinstance(filter_obj, Filter)
        assert len(filter_obj.must) == 1
        assert filter_obj.must[0].key == "tenant_id"
        assert isinstance(filter_obj.must[0], FieldCondition)
        assert filter_obj.must[0].match == MatchValue(value="test-tenant-123")

    def test_query_memory_requires_tenant_id(self):
        """query_memory always includes tenant filter via _enforce_tenant_filter."""
        from qdrant_client.models import Filter, FieldCondition
        with patch("src.memory.qdrant_ops._get_client") as mock_client:
            mock_client.return_value.query_points.return_value = MagicMock(points=[])
            with patch("src.memory.qdrant_ops._get_embedding", return_value=[0.1]*768):
                result = query_memory("tenant-a", "test query")
                call_kwargs = mock_client.return_value.query_points.call_args.kwargs
                assert "query_filter" in call_kwargs
                call_filter = call_kwargs["query_filter"]
                assert isinstance(call_filter, Filter)
                must_list = call_filter.must
                tenant_filter_included = False
                for condition in must_list:
                    if isinstance(condition, Filter):
                        for nested in condition.must:
                            if isinstance(nested, FieldCondition) and nested.key == "tenant_id":
                                tenant_filter_included = True
                    elif isinstance(condition, FieldCondition) and condition.key == "tenant_id":
                        tenant_filter_included = True
                assert tenant_filter_included, f"tenant_id filter must be in must clause. Got: {must_list}"

    def test_cross_tenant_returns_empty_for_mismatched_filter(self):
        """Cross-tenant query with wrong tenant_id returns 0 results."""
        from qdrant_client.models import Filter
        filter_obj = _enforce_tenant_filter("tenant-x")
        tenant_condition = [c for c in filter_obj.must if c.key == "tenant_id"][0]
        assert tenant_condition.match.value == "tenant-x"
        wrong_tenant_condition = _enforce_tenant_filter("tenant-y")
        assert wrong_tenant_condition.must[0].match.value == "tenant-y"
        assert wrong_tenant_condition.must[0].match.value != "tenant-x"

    def test_scroll_with_tenant_filter(self):
        """clear_tenant_memory uses tenant filter on scroll."""
        from qdrant_client.models import Filter
        with patch("src.memory.qdrant_ops._get_client") as mock_client:
            mock_client.return_value.scroll.return_value = ([], None)
            from src.memory.qdrant_ops import clear_tenant_memory
            clear_tenant_memory("tenant-cross-check")
            call_filter = mock_client.return_value.scroll.call_args.kwargs["scroll_filter"]
            assert isinstance(call_filter, Filter)
            assert any(c.key == "tenant_id" for c in call_filter.must)

    def test_delete_with_tenant_verification(self):
        """delete_memory verifies tenant ownership before delete."""
        with patch("src.memory.qdrant_ops._get_client") as mock_client:
            mock_point = MagicMock()
            mock_point.payload = {"tenant_id": "owner-tenant"}
            mock_client.return_value.retrieve.return_value = [mock_point]
            from src.memory.qdrant_ops import delete_memory
            result = delete_memory("owner-tenant", "point-123")
            assert result == True

    def test_delete_rejected_for_wrong_tenant(self):
        """delete_memory rejects delete for wrong tenant."""
        with patch("src.memory.qdrant_ops._get_client") as mock_client:
            mock_point = MagicMock()
            mock_point.payload = {"tenant_id": "owner-tenant"}
            mock_client.return_value.retrieve.return_value = [mock_point]
            from src.memory.qdrant_ops import delete_memory
            result = delete_memory("wrong-tenant", "point-123")
            assert result == False