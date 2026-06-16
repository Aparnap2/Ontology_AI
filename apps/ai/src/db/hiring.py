"""
Database module for hiring/recruitment.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.config.database import get_database_url

log = logging.getLogger(__name__)

DATABASE_URL = get_database_url()


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(DATABASE_URL)


def create_role(
    tenant_id: str,
    title: str,
    description: str = None,
    requirements: str = None
) -> int:
    """Create a new role posting."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO roles (tenant_id, title, description, requirements)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (tenant_id, title, description, requirements))

    role_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return role_id


def get_roles(tenant_id: str) -> list[dict[str, Any]]:
    """Get all open roles for a tenant."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT id, tenant_id, title, description, requirements, created_at
        FROM roles
        WHERE tenant_id = %s
        ORDER BY created_at DESC
    """, (tenant_id,))

    results = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(row) for row in results]


def create_candidate(
    tenant_id: str,
    role_id: int,
    name: str,
    email: str,
    resume_url: str = None,
    source: str = None
) -> int:
    """Create a new candidate record."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO candidates 
        (tenant_id, role_id, name, email, resume_url, source, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'new')
        RETURNING id
    """, (tenant_id, role_id, name, email, resume_url, source))

    candidate_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return candidate_id


def get_candidates(tenant_id: str, role_id: int = None, status: str = None) -> list[dict[str, Any]]:
    """Get candidates with optional filters."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    query = """
        SELECT c.id, c.tenant_id, c.role_id, c.name, c.email, c.resume_url,
               c.source, c.status, c.score_overall, c.score_technical,
               c.culture_signals, c.red_flags, c.recommended_action,
               c.last_contact_at, c.created_at, r.title as role_title
        FROM candidates c
        LEFT JOIN roles r ON c.role_id = r.id
        WHERE c.tenant_id = %s
    """
    params = [tenant_id]

    if role_id:
        query += " AND c.role_id = %s"
        params.append(role_id)

    if status:
        query += " AND c.status = %s"
        params.append(status)

    query += " ORDER BY c.created_at DESC"

    cur.execute(query, params)

    results = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(row) for row in results]


def update_candidate_score(
    candidate_id: int,
    score_overall: float = None,
    score_technical: float = None,
    culture_signals: list[str] = None,
    red_flags: list[str] = None,
    recommended_action: str = None,
    status: str = None
) -> None:
    """Update candidate scores and assessment."""
    conn = get_db_connection()
    cur = conn.cursor()

    updates = []
    params = []

    if score_overall is not None:
        updates.append("score_overall = %s")
        params.append(score_overall)

    if score_technical is not None:
        updates.append("score_technical = %s")
        params.append(score_technical)

    if culture_signals is not None:
        updates.append("culture_signals = %s")
        params.append(culture_signals)

    if red_flags is not None:
        updates.append("red_flags = %s")
        params.append(red_flags)

    if recommended_action is not None:
        updates.append("recommended_action = %s")
        params.append(recommended_action)

    if status is not None:
        updates.append("status = %s")
        params.append(status)
        # Update last_contact_at when status changes
        updates.append("last_contact_at = NOW()")

    if not updates:
        return

    params.append(candidate_id)

    cur.execute(f"""
        UPDATE candidates
        SET {', '.join(updates)}
        WHERE id = %s
    """, params)

    conn.commit()
    cur.close()
    conn.close()


def get_cold_candidates(tenant_id: str, days_threshold: int = 7) -> list[dict[str, Any]]:
    """Get candidates who haven't been contacted recently."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    threshold_date = "NOW() - INTERVAL '%s days'" % days_threshold

    cur.execute(f"""
        SELECT c.id, c.tenant_id, c.role_id, c.name, c.email, c.status,
               c.last_contact_at, c.created_at, r.title as role_title
        FROM candidates c
        LEFT JOIN roles r ON c.role_id = r.id
        WHERE c.tenant_id = %s
          AND c.status NOT IN ('hired', 'rejected')
          AND (c.last_contact_at IS NULL OR c.last_contact_at < {threshold_date})
        ORDER BY c.created_at ASC
    """, (tenant_id,))

    results = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(row) for row in results]