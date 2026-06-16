"""
Session Context — #trackguard channel history.

Per PRD Section 7: One Slack channel: #trackguard.
All agents and founder share this session.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import asyncpg

from src.config.database import get_database_url

log = logging.getLogger(__name__)

DATABASE_URL = get_database_url()


@dataclass
class SessionMessage:
    """A single message in the #trackguard session."""

    id: str | None
    tenant_id: str
    role: Literal["founder", "finance", "bi", "ops", "trackguard"]
    content: str
    agent_name: str | None
    created_at: datetime


async def get_session_context(
    tenant_id: str,
    limit: int = 10,
) -> list[SessionMessage]:
    """Get last N messages from #trackguard session.

    Per PRD Section 7: All agents read session context.
    Co-founder agent reads, employees write.

    Args:
        tenant_id: The tenant's session to fetch
        limit: Number of recent messages to return

    Returns:
        List of SessionMessage objects (newest first)
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        rows = await conn.fetch(
            """
            SELECT id, tenant_id, role, content, agent_name, created_at
            FROM session_messages
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            tenant_id,
            limit,
        )
        await conn.close()

        return [
            SessionMessage(
                id=str(row["id"]),
                tenant_id=row["tenant_id"],
                role=row["role"],
                content=row["content"],
                agent_name=row["agent_name"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
    except Exception as e:
        log.warning(f"Session context lookup failed for {tenant_id}: {e}")
        return []


async def write_session_message(
    tenant_id: str,
    role: Literal["founder", "finance", "bi", "ops", "trackguard"],
    content: str,
    agent_name: str | None = None,
) -> bool:
    """Write a message to the #trackguard session.

    Per PRD Section 7: Every message the founder types is context every agent reads.
    Agents self-activate when their domain keyword is triggered.

    Args:
        tenant_id: The tenant
        role: Who is speaking (founder or which agent)
        content: The message content
        agent_name: Name of agent if role is an agent

    Returns:
        True if successful
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            """
            INSERT INTO session_messages (tenant_id, role, content, agent_name, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            tenant_id,
            role,
            content,
            agent_name,
        )
        await conn.close()
        return True
    except Exception as e:
        log.error(f"Session message write failed: {e}")
        return False


# SQL for table creation (run once during migration)
SESSION_MESSAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    agent_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_messages_tenant_created
    ON session_messages(tenant_id, created_at DESC);
"""