"""Regression: event publication must never block its caller indefinitely.

Issue #71 (FG-1) root cause #2. The deterministic suite hung on
run_startup_guardian, which calls emit() after delivering an alert.

Reproduced in isolation, no test framework, broker reachable but wedged:

    connect() ok=True in 0.0s
    publish HUNG >15s

Redpanda advertised a metadata node whose host does not resolve
("Unable connect to node with id 0: Name or service not known"), so
AIOKafkaProducer.send_and_wait never returned. That wedges the startup
guardian permanently -- a production defect, not a test artifact.

Fix: bound the acknowledgement wait with asyncio.wait_for. On timeout,
publish() returns False (fail-closed) and the caller continues.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from src.events import redpanda as rp


class _WedgedProducer:
    """Stands in for a broker that accepts connect() but never acknowledges."""

    def __init__(self) -> None:
        self.calls = 0

    async def send_and_wait(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls += 1
        await asyncio.sleep(3600)  # never acknowledges
        raise AssertionError("unreachable")


class _DeadProducer:
    async def send_and_wait(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("broker down")


class _OkProducer:
    async def send_and_wait(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return object()


class TestPublishIsBounded:
    def _publisher(self, producer) -> rp.RedpandaPublisher:
        pub = rp.RedpandaPublisher(["localhost:1"])
        pub._producer = producer
        return pub

    def test_publish_returns_false_when_broker_never_acks(self, monkeypatch) -> None:
        monkeypatch.setattr(rp, "PUBLISH_TIMEOUT_SECONDS", 0.25)
        pub = self._publisher(_WedgedProducer())

        start = time.monotonic()
        result = asyncio.run(pub.publish("t", "tenant", "E", "s", {"a": 1}))
        elapsed = time.monotonic() - start

        assert result is False, "wedged broker must fail closed, not report success"
        assert elapsed < 5, (
            f"publish took {elapsed:.1f}s; it must be bounded by "
            "PUBLISH_TIMEOUT_SECONDS, not by broker health"
        )

    def test_publish_propagates_ordinary_failures_as_false(self, monkeypatch) -> None:
        monkeypatch.setattr(rp, "PUBLISH_TIMEOUT_SECONDS", 5.0)
        result = asyncio.run(
            self._publisher(_DeadProducer()).publish("t", "tenant", "E", "s", {})
        )
        assert result is False

    def test_publish_reports_success_when_broker_acks(self, monkeypatch) -> None:
        monkeypatch.setattr(rp, "PUBLISH_TIMEOUT_SECONDS", 5.0)
        result = asyncio.run(
            self._publisher(_OkProducer()).publish("t", "tenant", "E", "s", {})
        )
        assert result is True

    def test_publish_without_producer_is_false(self) -> None:
        pub = rp.RedpandaPublisher(["localhost:1"])
        pub._producer = None
        assert asyncio.run(pub.publish("t", "tenant", "E", "s", {})) is False


def test_publish_timeout_constant_is_configurable() -> None:
    """The bound must be tunable without editing code."""
    assert rp.PUBLISH_TIMEOUT_SECONDS > 0


@pytest.mark.parametrize("timeout", [0.25, 1.0])
def test_emit_does_not_hang_on_wedged_broker(monkeypatch, timeout: float) -> None:
    """End-to-end: emit() must return even against a wedged broker."""
    monkeypatch.setattr(rp, "PUBLISH_TIMEOUT_SECONDS", timeout)
    pub = rp.RedpandaPublisher(["localhost:1"])
    pub._producer = _WedgedProducer()

    import src.events as events

    async def _emit() -> bool:
        return await events.emit("topic", "tenant", {"a": 1})

    monkeypatch.setattr("src.events.get_producer", _stub_get_producer(pub))
    start = time.monotonic()
    result = asyncio.run(_emit())
    assert result is False
    assert time.monotonic() - start < 5


def _stub_get_producer(pub):
    async def _get():
        return pub

    return _get