"""
Centralized Temporal task queue configuration for OntologyAI V5.1.

The canonical queue is ``ONTOLOGYAI-MAIN-QUEUE``. It is env-overridable via
``TEMPORAL_TASK_QUEUE`` and falls back to the legacy ``TRACKGUARD-MAIN-QUEUE``
name so the pilot never hard-fails on queue misconfiguration (V5.1 OQ §8.4).
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("ontology_ai.queue")

# Canonical V5.1 task queue name.
ONTOLOGYAI_MAIN_QUEUE = "ONTOLOGYAI-MAIN-QUEUE"

# Legacy fallback queue retained for one version.
LEGACY_TASK_QUEUE = "TRACKGUARD-MAIN-QUEUE"

# Final fallback if even the legacy queue is unavailable.
DEFAULT_TASK_QUEUE = "default"


def resolve_task_queue() -> str:
    """Resolve the task queue to use, in priority order:

    1. ``TEMPORAL_TASK_QUEUE`` env var (if non-empty)
    2. ``ONTOLOGYAI_MAIN_QUEUE`` (canonical)
    3. ``LEGACY_TASK_QUEUE`` (TRACKGUARD-MAIN-QUEUE)

    The pilot must never crash on queue misconfiguration, so this always
    returns a usable queue name.
    """
    env = os.getenv("TEMPORAL_TASK_QUEUE", "").strip()
    if env:
        return env
    return ONTOLOGYAI_MAIN_QUEUE


def resolve_task_queue_with_fallback(connect_fn=None) -> str:
    """Resolve the task queue, attempting the primary queue first and falling
    back defensively if a connection to the primary queue cannot be established.

    ``connect_fn`` is an optional callable that accepts a queue name and returns
    a Temporal client/worker (or ``None``) and raises on failure. If it raises
    (or returns ``None``), we fall back to the legacy queue, then to
    ``"default"``. The pilot never hard-fails.
    """
    primary = resolve_task_queue()
    candidates = [primary, LEGACY_TASK_QUEUE, DEFAULT_TASK_QUEUE]
    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered = [q for q in candidates if not (q in seen or seen.add(q))]  # type: ignore[func-returns-value]

    for queue in ordered:
        if connect_fn is None:
            return queue
        try:
            result = connect_fn(queue)
            if result is not None:
                return queue
            log.warning("Task queue %s returned no client; trying fallback", queue)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("Task queue %s unavailable: %s; trying fallback", queue, exc)
    # Should never reach here because "default" is always valid.
    return DEFAULT_TASK_QUEUE
