"""Producer lifecycle regression tests (issue #71 — producer leak).

Covers the required scenarios with a fake producer injected at the
``AIOKafkaProducer`` symbol, so no broker, network, or container is involved:

  1. successful publish            -> producer is closed
  2. publish failure               -> producer is closed AND the failure is preserved
  3. task cancellation             -> cleanup runs AND cancellation propagates
  4. repeated/competing cleanup    -> no double-stop, no invalid lifecycle transition

The regression these lock: producers were previously created and referenced
before ``start()``, left unclosed when ``start()`` failed, and silently
overwritten (leaking the previous live producer) when ``connect()`` was called
more than once.
"""
from __future__ import annotations

import asyncio

import pytest

from src.events import redpanda as rp


class FakeProducer:
    """Minimal AIOKafkaProducer stand-in that records its lifecycle."""

    def __init__(self, *, start_error: Exception | None = None,
                 send_error: Exception | None = None,
                 stop_error: Exception | None = None) -> None:
        self.start_error = start_error
        self.send_error = send_error
        self.stop_error = stop_error
        self.started = 0
        self.stops = 0
        self.sends = 0
        self.stopped_before_send = False

    async def start(self) -> None:
        self.started += 1
        if self.start_error is not None:
            raise self.start_error

    async def send_and_wait(self, topic, value, key=None):
        self.sends += 1
        if self.stop_error is not None and self.stops:
            self.stopped_before_send = True
        if self.send_error is not None:
            raise self.send_error
        return type("MD", (), {"topic": topic, "partition": 0, "offset": 0})()

    async def stop(self) -> None:
        self.stops += 1
        if self.stop_error is not None:
            raise self.stop_error


def _install(monkeypatch, factory) -> list[FakeProducer]:
    created: list[FakeProducer] = []

    def _make(**kwargs):
        p = factory(**kwargs)
        created.append(p)
        return p

    monkeypatch.setattr(rp, "AIOKafkaProducer", _make)
    return created


# 1. Successful publish -> producer closed
@pytest.mark.asyncio
async def test_successful_publish_closes_producer(monkeypatch):
    created = _install(monkeypatch, lambda **kw: FakeProducer())
    assert await rp.publish_guardian_result("t1", "a1", "approve") is True
    assert len(created) == 1
    assert created[0].started == 1, "producer never started"
    assert created[0].stops == 1, "producer not closed after successful publish"


# 2a. Publish failure -> producer closed, failure preserved (returns False, no raise)
@pytest.mark.asyncio
async def test_publish_failure_closes_producer_and_is_reported_false(monkeypatch):
    boom = RuntimeError("broker rejected the record")
    created = _install(monkeypatch, lambda **kw: FakeProducer(send_error=boom))
    result = await rp.publish_guardian_result("t1", "a1", "approve")
    assert result is False, "publish failure must NOT be reported as success"
    assert created[0].stops == 1, "producer not closed after publish failure"


# 2b. connect() failure -> the half-started producer is still stopped
@pytest.mark.asyncio
async def test_connect_failure_stops_half_started_producer(monkeypatch):
    created = _install(
        monkeypatch, lambda **kw: FakeProducer(start_error=RuntimeError("no broker"))
    )
    assert await rp.publish_guardian_result("t1", "a1", "approve") is False
    assert len(created) == 1
    assert created[0].stops == 1, (
        "producer whose start() failed was never stopped (resource leak)"
    )


# 3. Cancellation -> cleanup runs and CancelledError propagates
@pytest.mark.asyncio
async def test_cancellation_runs_cleanup_and_propagates(monkeypatch):
    gate = asyncio.Event()

    class BlockingProducer(FakeProducer):
        async def send_and_wait(self, topic, value, key=None):
            self.sends += 1
            await gate.wait()  # never completes -> task can be cancelled
            raise AssertionError("unreachable")

    created = _install(monkeypatch, lambda **kw: BlockingProducer())

    task = asyncio.create_task(rp.publish_guardian_result("t1", "a1", "approve"))
    await asyncio.sleep(0.05)  # let it reach the blocked publish
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert created[0].stops == 1, "cleanup did not run on cancellation"


# 4. Repeated cleanup / competing exit paths -> no double-stop
@pytest.mark.asyncio
async def test_repeated_close_is_idempotent(monkeypatch):
    created = _install(monkeypatch, lambda **kw: FakeProducer())
    publisher = rp.RedpandaPublisher()
    assert await publisher.connect() is True

    await publisher.close()
    await publisher.close()
    await publisher.close()

    assert created[0].stops == 1, f"double-stop: {created[0].stops}"


# 4b. connect() twice -> previous producer is closed, not leaked
@pytest.mark.asyncio
async def test_reconnect_closes_previous_producer(monkeypatch):
    created = _install(monkeypatch, lambda **kw: FakeProducer())
    publisher = rp.RedpandaPublisher()
    assert await publisher.connect() is True
    assert await publisher.connect() is True

    assert len(created) == 2, "expected a second producer"
    assert created[0].stops == 1, (
        "the previous live producer was overwritten without being stopped (leak)"
    )
    assert created[1].stops == 0, "current producer stopped while still in use"

    await publisher.close()
    assert created[1].stops == 1


# 4c. cleanup errors must not mask the original failure
@pytest.mark.asyncio
async def test_cleanup_error_does_not_mask_publish_failure(monkeypatch):
    created = _install(
        monkeypatch,
        lambda **kw: FakeProducer(
            send_error=RuntimeError("original publish failure"),
            stop_error=RuntimeError("cleanup blew up too"),
        ),
    )
    # Must not raise the cleanup error, and must not report success.
    assert await rp.publish_guardian_result("t1", "a1", "approve") is False
    assert created[0].stops == 1


# 4d. DLQ producer: start() failure must not leak
@pytest.mark.asyncio
async def test_dlq_producer_start_failure_does_not_leak(monkeypatch):
    created = _install(
        monkeypatch, lambda **kw: FakeProducer(start_error=RuntimeError("dlq down"))
    )
    consumer = rp.RedpandaConsumer()
    assert await consumer._ensure_dlq_producer() is None
    assert created[0].stops == 1, "DLQ producer leaked on start() failure"
