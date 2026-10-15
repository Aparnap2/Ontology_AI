"""Regression: send_message_sync must not drive an already-running event loop.

Issue #71 (FG-1) root cause. The deterministic gate hung on
tests/deterministic/test_trajectory_verification.py::test_connector_order[all_healthy].

Call chain:
    run_startup_guardian (async)
      -> SlackAlertForwarder.forward_mission_alert (SYNC)
        -> send_message_sync
          -> loop.run_until_complete(...) on the CALLER'S LIVE loop

run_until_complete cannot be called on a loop that is already running. The
old code did exactly that inside a ThreadPoolExecutor, which either raised
"RuntimeError: This event loop is already running" (leaking the coroutine, so
the alert was silently dropped by run_startup_guardian's bare except) or hung
the caller indefinitely.

This is a production defect, not a test-only artifact: the same path runs in
the real startup guardian.

The test asserts the call RETURNS and reports its delivery outcome. It does
not assert a network call happened.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from src.integrations.slack import send_message_sync


def _call_from_running_loop(timeout: float = 10.0):
    """Invoke send_message_sync from inside an already-running event loop."""
    result: dict[str, object] = {}

    async def _entry() -> None:
        result["value"] = send_message_sync(
            text="startup guardian alert (regression test)",
            blocks=None,
        )

    def _runner() -> None:
        try:
            asyncio.run(_entry())
        except BaseException as exc:  # noqa: BLE001 - recorded for assertion
            result["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    return thread.is_alive(), result


class TestSendMessageSyncNoLoopDeadlock:
    def test_returns_instead_of_deadlocking(self) -> None:
        hung, result = _call_from_running_loop()

        assert not hung, (
            "send_message_sync hung for 10s when called from a running event "
            "loop — it is driving the caller's live loop"
        )
        assert "error" not in result, (
            f"send_message_sync raised from a running loop: "
            f"{result.get('error')!r}"
        )
        assert "value" in result, "send_message_sync returned no result"
        assert isinstance(result["value"], dict)

    def test_does_not_leak_unawaited_coroutine(self) -> None:
        """Pre-fix this emitted: coroutine 'send_message' was never awaited."""
        hung, result = _call_from_running_loop()
        assert not hung

        import gc

        gc.collect()
        pending = [
            type(o).__name__
            for o in gc.get_objects()
            if type(o).__name__ == "coroutine"
            and getattr(o, "cr_frame", None) is not None
            and o.cr_frame.f_code.co_name == "send_message"
        ]
        assert not pending, f"unawaited send_message coroutine leaked: {pending}"
        assert "error" not in result


class TestSendMessageSyncNoLoop:
    def test_still_works_without_a_running_loop(self) -> None:
        """The ordinary (no running loop) path must not regress."""

        async def _entry() -> None:
            return send_message_sync(text="no-loop regression")

        result = asyncio.run(_entry())
        assert isinstance(result, dict)


@pytest.mark.parametrize("timeout", [10.0])
def test_callable_from_worker_thread_inside_running_loop(timeout: float) -> None:
    hung, result = _call_from_running_loop(timeout=timeout)
    assert not hung
    assert "error" not in result