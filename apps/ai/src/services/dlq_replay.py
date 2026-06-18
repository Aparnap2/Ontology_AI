"""DLQ replay — re-execute failed operations from the Dead Letter Queue.

Provides utilities to retry connector calls that were recorded in the DLQ,
and to mark entries as replayed on success.

Usage:
    from src.services.dlq_replay import replay_connector_failure

    # Replay a failed HubSpot connector call
    result = replay_connector_failure(
        dlq_id="dlq-20260618120000-hubspot",
        connector_fn=get_hubspot_snapshot,
        tenant_id="tenant_abc",
    )
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from .dead_letter import get_dlq_entries, mark_replayed

logger = logging.getLogger(__name__)


def replay_connector_failure(
    dlq_id: str,
    connector_fn: Callable[..., Any],
    tenant_id: str,
) -> dict[str, Any]:
    """Replay a failed connector call from DLQ.

    Looks up the DLQ entry by ID, re-invokes the connector function,
    and marks the entry as replayed on success.

    Args:
        dlq_id: The DLQ entry ID to replay.
        connector_fn: The connector function to call. Receives `tenant_id` as argument.
        tenant_id: Tenant identifier to pass to the connector.

    Returns:
        Dict with keys:
            - success (bool): Whether the replay succeeded.
            - result: The connector result on success, or None on failure.
            - error (str): Error message on failure, or None on success.
    """
    entries = get_dlq_entries(tenant_id=tenant_id)
    entry = next((e for e in entries if e["id"] == dlq_id), None)

    if not entry:
        return {"success": False, "result": None, "error": "DLQ entry not found"}

    if entry.get("replayed"):
        return {"success": False, "result": None, "error": "DLQ entry already replayed"}

    try:
        result = connector_fn(tenant_id)
        mark_replayed(dlq_id)
        logger.info(
            "DLQ replay success: id=%s source=%s operation=%s",
            dlq_id, entry["source"], entry["operation"],
        )
        return {"success": True, "result": result, "error": None}
    except Exception as exc:
        logger.error(
            "DLQ replay failed: id=%s source=%s operation=%s error=%s",
            dlq_id, entry["source"], entry["operation"], exc,
        )
        return {"success": False, "result": None, "error": str(exc)}


def replay_all_failures(
    source: str,
    connector_fn: Callable[..., Any],
    tenant_id: str,
    max_replays: int = 10,
) -> dict[str, Any]:
    """Replay all unreplayed failures for a given connector source.

    Args:
        source: Connector source name (e.g., "hubspot").
        connector_fn: The connector function to call.
        tenant_id: Tenant identifier to pass to the connector.
        max_replays: Maximum number of entries to replay (safety limit).

    Returns:
        Dict with keys:
            - attempted (int): Number of entries attempted.
            - succeeded (int): Number of successful replays.
            - failed (int): Number of failed replays.
            - results (list): Individual results for each replay attempt.
    """
    entries = get_dlq_entries(source=source, tenant_id=tenant_id)
    unreplayed = [e for e in entries if not e.get("replayed")][:max_replays]

    results: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0

    for entry in unreplayed:
        result = replay_connector_failure(
            dlq_id=entry["id"],
            connector_fn=connector_fn,
            tenant_id=tenant_id,
        )
        results.append({"entry_id": entry["id"], **result})
        if result["success"]:
            succeeded += 1
        else:
            failed += 1

    return {
        "attempted": len(unreplayed),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
