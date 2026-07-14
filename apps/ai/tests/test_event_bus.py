"""
Tests for Redis Streams event bus tenant isolation.

Verifies:
1. Tenant-A events never appear in tenant-B stream
2. Full emit → consume → ack round-trip
"""
import pytest
import asyncio
import json
import os

# Skip if Redis not available
pytestmark = pytest.mark.skipif(
    os.environ.get("REDIS_URL") is None,
    reason="REDIS_URL not set"
)

from apps.ai.src.events.bus import emit, consume, acknowledge, get_event_bus


@pytest.fixture
def redis_url():
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


@pytest.mark.asyncio
async def test_tenant_streams_are_isolated(redis_url):
    """
    Events emitted for tenant-A must NEVER appear in tenant-B's stream.
    """
    tenant_a = "isolation-test-tenant-A"
    tenant_b = "isolation-test-tenant-B"

    # Emit for tenant A
    result_a = await emit(
        "guardian.alert_delivered",
        tenant_a,
        {"msg": "A's alert", "alert_id": "alert-123"}
    )
    assert result_a is not None, "Emit for tenant A failed"

    # Small delay to ensure message is written
    await asyncio.sleep(0.1)

    # Tenant B reads its own stream — must see nothing
    messages = await consume(
        topic="guardian.alert_delivered",
        tenant_id=tenant_b,
        group="test-isolation",
        consumer="test-consumer",
        block_ms=100,
    )

    events = []
    for _stream, entries in (messages or {}):
        for _mid, fields in entries:
            events.append(fields)

    assert len(events) == 0, \
        f"ISOLATION BREACH: tenant-B stream received tenant-A events: {events}"

    # Cleanup: read and ack the message from tenant A
    messages_a = await consume(
        topic="guardian.alert_delivered",
        tenant_id=tenant_a,
        group="test-isolation",
        consumer="test-cleanup",
        block_ms=100,
    )
    for _stream, entries in (messages_a or {}):
        for mid, fields in entries:
            await acknowledge("guardian.alert_delivered", tenant_a, "test-isolation", mid)


@pytest.mark.asyncio
async def test_emit_consume_ack_round_trip(redis_url):
    """Full round-trip: emit → consume → ack, message disappears from pending."""
    from apps.ai.src.events.bus import EventBus

    bus = EventBus(redis_url)
    tenant_id = "roundtrip-test-tenant"
    topic = "test.roundtrip"
    group = "test-roundtrip-group"
    consumer = "test-consumer"

    try:
        # Emit
        msg_id = await emit(topic, tenant_id, {"key": "value", "test": "roundtrip"})
        assert msg_id is not None, "Emit returned None"

        # Consume
        await asyncio.sleep(0.1)
        messages = await consume(
            topic=topic,
            tenant_id=tenant_id,
            group=group,
            consumer=consumer,
            block_ms=200,
        )

        found = False
        found_msg_id = None
        for _stream, entries in (messages or {}):
            for mid, fields in entries:
                payload = json.loads(fields["payload"])
                if payload.get("key") == "value":
                    found = True
                    found_msg_id = mid
                    # Acknowledge this message
                    await acknowledge(topic, tenant_id, group, mid)

        assert found, "Emitted event not consumed"

        # Verify pending count is now 0
        client = await bus._get_client()
        stream = f"ontology_ai:{tenant_id}:{topic}"
        pending = await client.xpending(stream, group)

        assert pending.get("pending", 0) == 0, \
            f"Message not acknowledged — still in PEL: {pending}"

    finally:
        # Cleanup: delete stream
        try:
            client = await bus._get_client()
            await client.delete(stream)
        except Exception:
            pass
        await bus.close()


@pytest.mark.asyncio
async def test_stream_maxlen_trimming(redis_url):
    """Verify Redis Streams respect maxlen=1000."""
    from apps.ai.src.events.bus import EventBus

    bus = EventBus(redis_url)
    tenant_id = "maxlen-test-tenant"
    topic = "test.maxlen"

    try:
        # Emit more than 1000 messages (will use approximate trimming)
        for i in range(1005):
            await emit(topic, tenant_id, {"seq": i})

        await asyncio.sleep(0.5)

        # Check stream length
        client = await bus._get_client()
        stream = f"ontology_ai:{tenant_id}:{topic}"
        length = await client.xlen(stream)

        # Should be around 1000 (Redis uses approximate trimming)
        assert length <= 1010, f"Stream exceeds maxlen: {length} > 1010"

    finally:
        # Cleanup
        try:
            client = await bus._get_client()
            await client.delete(stream)
        except Exception:
            pass
        await bus.close()