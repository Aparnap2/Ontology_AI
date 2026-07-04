"""Audit Logger — writes control plane audit events to PostgreSQL."""
from __future__ import annotations

import json
import logging

import asyncpg

from src.config.database import get_database_url
from src.schemas.control_plane import AuditEvent

log = logging.getLogger(__name__)

DATABASE_URL = get_database_url("iterateswarm")


class AuditLogger:
    """Logs agent actions to the audit_log table for inspection."""

    async def log_event(
        self,
        event: AuditEvent,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        """Persist an audit event to PostgreSQL.

        Args:
            event: The AuditEvent to log.
            conn: Optional existing connection for transaction reuse.

        Returns:
            True if logged successfully, False on failure.
        """
        own_conn = conn is None
        try:
            if own_conn:
                conn = await asyncpg.connect(DATABASE_URL)

            await conn.execute(
                """
                INSERT INTO audit_log (
                    tenant_id, agent_name, action, tool_name,
                    model_used, policy_decision, approval_state,
                    outcome, details, timestamp
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                """,
                event.tenant_id,
                event.agent_name,
                event.action,
                event.tool_name,
                event.model_used,
                json.dumps(
                    event.policy_decision.model_dump() if event.policy_decision else None
                ),
                event.approval_state,
                event.outcome,
                json.dumps(event.details) if event.details else None,
            )

            log.info(
                "Audit event logged: %s/%s -> %s",
                event.agent_name,
                event.action,
                event.outcome,
            )
            return True
        except Exception as e:
            log.warning(
                "Audit log failed for %s/%s: %s",
                event.agent_name,
                event.action,
                e,
            )
            return False
        finally:
            if own_conn and conn is not None:
                await conn.close()