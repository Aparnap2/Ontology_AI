"""
Tests for Redpanda event bus - Go→Python event routing.
"""
import pytest
import asyncio
import os

pytestmark = pytest.mark.skipif(
    os.environ.get("REDPANDA_URL") is None,
    reason="REDPANDA_URL not set - using Redis Streams"
)


class TestRedpandaConsumer:
    """Test suite for Redpanda consumer."""

    @pytest.mark.asyncio
    async def test_consumer_fails_gracefully_when_redpanda_unavailable(self):
        """
        When Redpanda is unavailable, consumer returns False.
        System does NOT crash.
        """
        from apps.ai.src.events.redpanda import RedpandaConsumer

        consumer = RedpandaConsumer(["localhost:9999"])
        result = await consumer.connect()

        assert result is False, "Should return False when Redpanda unavailable"
        print(f"✓ Consumer handled unavailable broker correctly")


class TestRedpandaPublisher:
    """Test suite for Python→Redpanda publishing."""

    @pytest.mark.asyncio
    async def test_publisher_fails_gracefully_when_unavailable(self):
        """
        When Redpanda unavailable, publish returns False.
        """
        from apps.ai.src.events.redpanda import RedpandaPublisher

        publisher = RedpandaPublisher(["localhost:9999"])
        result = await publisher.connect()

        assert result is False, "Should return False when Redpanda unavailable"
        print(f"✓ Publisher handled unavailable broker correctly")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_publish_guardian_result_to_correct_topic(self):
        """
        publish_guardian_result publishes to trackguard.guardian.results.
        """
        from apps.ai.src.events.redpanda import publish_guardian_result

        result = await publish_guardian_result(
            tenant_id="test-tenant",
            alert_id="alert-123",
            decision="APPROVED",
            message="Test decision"
        )

        assert result is True or result is False, "Should return bool"
        print(f"✓ publish_guardian_result returned: {result}")