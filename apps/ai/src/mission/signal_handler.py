"""Signal handler — in-memory HITL signal bridge.

The runtime emits a signal (e.g. ``"hitl-approval"``) and suspends until the
human resolves it.  Temporal binds via :meth:`SignalHandler.emit`; for tests
the :class:`InMemorySignalHandler` resolves instantly.
"""
from __future__ import annotations

import asyncio
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SignalHandler(Protocol):
    """Minimal contract for HITL signal transport."""

    def emit(self, name: str, payload: dict[str, Any]) -> None: ...

    async def await_decision(self, name: str) -> dict[str, Any]: ...

    def resolve(self, decision: dict[str, Any]) -> None: ...


class InMemorySignalHandler:
    """Deterministic in-memory signal handler for tests and local mode.

    ``resolve()`` unblocks *every* pending ``await_decision`` caller at once
    so that parallel WAIT steps all proceed (or all halt) together.
    """

    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict[str, Any]]] = []
        self._decisions: list[dict[str, Any]] = []
        self._futures: list[asyncio.Future[dict[str, Any]]] = []

    def emit(self, name: str, payload: dict[str, Any]) -> None:
        """Record the signal (instant — test can poll emitted immediately)."""
        self.emitted.append((name, payload))

    async def await_decision(self, name: str) -> dict[str, Any]:
        """Suspend until :meth:`resolve` is called with a decision dict."""
        if self._decisions:
            return self._decisions.pop(0)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._futures.append(fut)
        return await fut

    def resolve(self, decision: dict[str, Any]) -> None:
        """Unblock every pending ``await_decision`` caller."""
        for fut in list(self._futures):
            if not fut.done():
                fut.set_result(decision)
        self._futures.clear()
