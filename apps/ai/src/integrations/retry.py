"""Retry utilities with exponential backoff and circuit breaker for connectors.

Provides two resilience primitives consumed by every connector in this package:

* ``circuit_breaker`` — decorator that trips after *failure_threshold*
  consecutive failures and self-heals after *recovery_timeout* seconds.
* ``retry_with_backoff`` — helper that re-invokes a zero-arg callable with
  jittered exponential backoff.  An optional *retry_if* predicate lets callers
  distinguish transient from permanent exceptions (e.g. HTTP 5xx vs 4xx).

Both are pure-stdlib — no external dependencies.
"""

import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConnectorError(Exception):
    """Raised when a connector fails after exhausting all retry attempts."""


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is in the *open* state."""


# ---------------------------------------------------------------------------
# Circuit breaker (module-level state, in-process only)
# ---------------------------------------------------------------------------

_circuit_state: dict[str, dict] = {}


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
):
    """Decorator implementing the circuit breaker pattern.

    After *failure_threshold* consecutive failures the circuit **opens** and
    all subsequent calls raise ``CircuitBreakerOpen`` for *recovery_timeout*
    seconds.  After that window a single **half-open** probe is allowed;
    success resets the circuit, another failure re-opens it.

    State lives in the module-level ``_circuit_state`` dict and is therefore
    scoped to the current process — acceptable for a single-worker deployment.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            state = _circuit_state.setdefault(
                name, {"failures": 0, "open": False, "last_failure": 0.0}
            )

            if state["open"]:
                if time.time() - state["last_failure"] > recovery_timeout:
                    state["open"] = False
                    state["failures"] = 0
                    logger.info(
                        "Circuit breaker %s: half-open, allowing probe request",
                        name,
                    )
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit breaker {name} is open"
                    )

            try:
                result = func(*args, **kwargs)
                state["failures"] = 0
                return result
            except Exception:
                state["failures"] += 1
                state["last_failure"] = time.time()
                if state["failures"] >= failure_threshold:
                    state["open"] = True
                    logger.error(
                        "Circuit breaker %s: opened after %d consecutive failures",
                        name,
                        state["failures"],
                    )
                raise

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Backoff helpers
# ---------------------------------------------------------------------------

def compute_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
) -> float:
    """Return a jittered exponential-backoff delay for *attempt* (0-indexed).

    The formula is::

        delay = min(base * factor^attempt, max) * uniform(0.5, 1.5)

    Adding jitter (the ``* uniform(...)``) prevents thundering-herd effects
    when multiple workers retry in lock-step.
    """
    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
    delay *= 0.5 + random.random()  # jitter: [0.5, 1.5) × delay
    return delay


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def retry_with_backoff(
    func: Callable[..., T],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    retry_if: Optional[Callable[[Exception], bool]] = None,
) -> T:
    """Execute *func* with jittered exponential-backoff retry.

    Parameters
    ----------
    func:
        Zero-argument callable to execute.
    max_attempts:
        Total number of attempts (1 = no retry).
    base_delay / max_delay / backoff_factor:
        Backoff tuning knobs (see :func:`compute_backoff_delay`).
    exceptions:
        Tuple of exception types eligible for retry.
    retry_if:
        Optional predicate ``(exc) -> bool``.  When provided, only exceptions
        for which the predicate returns *True* are retried; all others are
        re-raised immediately.  When ``None`` (the default), every exception
        matching the *exceptions* tuple is retried.

    Raises
    ------
    ConnectorError
        If all attempts fail.
    """
    last_exception: Optional[Exception] = None

    for attempt in range(max_attempts):
        try:
            return func()
        except exceptions as exc:
            # honour the optional retry predicate
            if retry_if is not None and not retry_if(exc):
                raise

            last_exception = exc

            if attempt < max_attempts - 1:
                delay = compute_backoff_delay(
                    attempt, base_delay, max_delay, backoff_factor
                )
                logger.warning(
                    "Retry %d/%d for %s: %s (waiting %.1fs)",
                    attempt + 1,
                    max_attempts,
                    getattr(func, "__name__", str(func)),
                    exc,
                    delay,
                )
                time.sleep(delay)

    raise ConnectorError(
        f"Failed after {max_attempts} attempts: {last_exception}"
    )


# ---------------------------------------------------------------------------
# Test helper — resets all circuit breaker state between tests
# ---------------------------------------------------------------------------

def reset_circuit_state() -> None:
    """Clear all circuit breaker counters.  Intended for test teardown."""
    _circuit_state.clear()
