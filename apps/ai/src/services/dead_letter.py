"""Dead Letter Queue for failed connector calls and agent actions.

Provides an in-memory DLQ store with optional PostgreSQL persistence.
When PostgreSQL is available, entries are persisted for durability.
When unavailable, entries are stored in-memory and logged.

Usage:
    from src.services.dead_letter import send_to_dlq, get_dlq_entries

    # Record a failure
    entry = send_to_dlq(
        source="hubspot",
        operation="get_hubspot_snapshot",
        error="Connection timeout after 30s",
        tenant_id="tenant_abc",
    )

    # Query failures
    failures = get_dlq_entries(source="hubspot", tenant_id="tenant_abc")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory DLQ store (fallback when PostgreSQL is unavailable)
# ---------------------------------------------------------------------------
_dlq_store: list[dict[str, Any]] = []

# Optional PostgreSQL connection (set via configure_dlq_db)
_pg_conn: Any = None


def configure_pg_dsn(dsn: str) -> None:
    """Configure PostgreSQL DSN for DLQ persistence.

    If the connection fails, the DLQ falls back to in-memory storage.
    This is a synchronous wrapper — callers should use asyncio.to_thread
    when calling from async contexts.
    """
    global _pg_conn
    try:
        import psycopg2  # noqa: F811 — conditional import

        _pg_conn = psycopg2.connect(dsn)
        logger.info("DLQ: PostgreSQL connection established")
    except Exception as exc:
        logger.warning("DLQ: PostgreSQL unavailable (%s), using in-memory store", exc)
        _pg_conn = None


def send_to_dlq(
    source: str,
    operation: str,
    error: str,
    payload: Optional[dict[str, Any]] = None,
    tenant_id: str = "",
    retry_count: int = 0,
) -> dict[str, Any]:
    """Record a failed operation in the Dead Letter Queue.

    Args:
        source: The connector or service that failed (e.g., "hubspot", "erpnext").
        operation: The specific operation that failed (e.g., "get_hubspot_snapshot").
        error: Error message or exception string.
        payload: Optional payload that was being processed when failure occurred.
        tenant_id: Tenant identifier for filtering.
        retry_count: Number of retries already attempted.

    Returns:
        The created DLQ entry dict.
    """
    now = datetime.now(timezone.utc)
    entry: dict[str, Any] = {
        "id": f"dlq-{now.strftime('%Y%m%d%H%M%S')}-{source}",
        "source": source,
        "operation": operation,
        "error": str(error),
        "payload": payload or {},
        "tenant_id": tenant_id,
        "retry_count": retry_count,
        "created_at": now.isoformat(),
        "replayed": False,
    }

    # Try PostgreSQL persistence
    if _pg_conn is not None:
        try:
            with _pg_conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO dlq_entries (source, operation, error_msg, payload, tenant_id, retry_count, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (
                        source,
                        operation,
                        str(error),
                        json.dumps(payload or {}),
                        tenant_id,
                        retry_count,
                        now,
                    ),
                )
                _pg_conn.commit()
                logger.info(
                    "DLQ persisted: source=%s operation=%s tenant=%s",
                    source, operation, tenant_id,
                )
        except Exception as exc:
            logger.warning("DLQ: PostgreSQL insert failed (%s), falling back to in-memory", exc)
            # Fall through to in-memory

    # Fallback: in-memory + structured log
    _dlq_store.append(entry)
    logger.error(
        "DLQ: source=%s operation=%s error=%s tenant=%s retries=%d",
        source, operation, error, tenant_id, retry_count,
    )
    return entry


def get_dlq_entries(
    source: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Retrieve DLQ entries with optional filtering.

    Args:
        source: Filter by connector source name.
        tenant_id: Filter by tenant.
        limit: Maximum entries to return (most recent).

    Returns:
        List of DLQ entry dicts, most recent last.
    """
    entries = list(_dlq_store)
    if source:
        entries = [e for e in entries if e["source"] == source]
    if tenant_id:
        entries = [e for e in entries if e["tenant_id"] == tenant_id]
    return entries[-limit:]


def mark_replayed(dlq_id: str) -> bool:
    """Mark a DLQ entry as replayed.

    Args:
        dlq_id: The DLQ entry ID to mark.

    Returns:
        True if the entry was found and marked, False otherwise.
    """
    for entry in _dlq_store:
        if entry["id"] == dlq_id:
            entry["replayed"] = True
            return True
    return False


def dlq_count(source: Optional[str] = None) -> int:
    """Count DLQ entries, optionally filtered by source.

    Args:
        source: Filter by connector source name, or None for total count.

    Returns:
        Number of DLQ entries matching the filter.
    """
    if source:
        return len([e for e in _dlq_store if e["source"] == source])
    return len(_dlq_store)


def clear_dlq() -> int:
    """Clear all DLQ entries (for testing).

    Returns:
        Number of entries cleared.
    """
    count = len(_dlq_store)
    _dlq_store.clear()
    return count
