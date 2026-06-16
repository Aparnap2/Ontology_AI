"""
Database module for investor relationships.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from src.config.database import get_database_url

log = logging.getLogger(__name__)

DATABASE_URL = get_database_url()


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(DATABASE_URL)


def create_investor_relationship(
    tenant_id: str,
    investor_name: str,
    firm: str,
    warm_up_days: int = 30,
    raise_priority: int = 5,
    notes: str = None
) -> int:
    """Create a new investor relationship."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO investor_relationships 
        (tenant_id, investor_name, firm, warm_up_days, raise_priority, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (tenant_id, investor_name, firm, warm_up_days, raise_priority, notes))
    
    investor_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    return investor_id


def get_investor_relationships(tenant_id: str) -> list[dict[str, Any]]:
    """Get all investor relationships for a tenant."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT id, tenant_id, investor_name, firm, last_contact_at, 
               warm_up_days, raise_priority, notes, created_at
        FROM investor_relationships
        WHERE tenant_id = %s
        ORDER BY raise_priority DESC, last_contact_at ASC NULLS FIRST
    """, (tenant_id,))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return [dict(row) for row in results]


def get_investor_by_id(investor_id: int) -> dict[str, Any] | None:
    """Get a single investor by ID."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT id, tenant_id, investor_name, firm, last_contact_at,
               warm_up_days, raise_priority, notes, created_at
        FROM investor_relationships
        WHERE id = %s
    """, (investor_id,))
    
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    return dict(result) if result else None


def update_last_contact(investor_id: int) -> None:
    """Update last contact timestamp to now."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE investor_relationships
        SET last_contact_at = NOW()
        WHERE id = %s
    """, (investor_id,))
    
    conn.commit()
    cur.close()
    conn.close()


def get_cold_relationships(tenant_id: str, days_threshold: int = None) -> list[dict[str, Any]]:
    """Get relationships that need warming up."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if days_threshold is None:
        days_threshold = 30
    
    threshold_date = datetime.utcnow() - timedelta(days=days_threshold)
    
    cur.execute("""
        SELECT id, tenant_id, investor_name, firm, last_contact_at,
               warm_up_days, raise_priority, notes, created_at
        FROM investor_relationships
        WHERE tenant_id = %s
          AND (last_contact_at IS NULL OR last_contact_at < %s)
        ORDER BY raise_priority DESC
    """, (tenant_id, threshold_date))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return [dict(row) for row in results]


def add_interaction(
    tenant_id: str,
    investor_id: int,
    interaction_type: str,
    summary: str = None
) -> int:
    """Record an interaction with an investor."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO investor_interactions
        (tenant_id, investor_id, interaction_type, summary)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (tenant_id, investor_id, interaction_type, summary))
    
    interaction_id = cur.fetchone()[0]
    
    cur.execute("""
        UPDATE investor_relationships
        SET last_contact_at = NOW()
        WHERE id = %s
    """, (investor_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return interaction_id


def get_interactions(tenant_id: str, investor_id: int = None) -> list[dict[str, Any]]:
    """Get investor interactions."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if investor_id:
        cur.execute("""
            SELECT id, tenant_id, investor_id, interaction_type, summary, occurred_at
            FROM investor_interactions
            WHERE tenant_id = %s AND investor_id = %s
            ORDER BY occurred_at DESC
        """, (tenant_id, investor_id))
    else:
        cur.execute("""
            SELECT id, tenant_id, investor_id, interaction_type, summary, occurred_at
            FROM investor_interactions
            WHERE tenant_id = %s
            ORDER BY occurred_at DESC
            LIMIT 50
        """, (tenant_id,))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return [dict(row) for row in results]


def check_relationship_health(tenant_id: str) -> dict[str, Any]:
    """Check overall investor relationship health."""
    all_relationships = get_investor_relationships(tenant_id)
    cold_relationships = get_cold_relationships(tenant_id)
    
    total_investors = len(all_relationships)
    cold_count = len(cold_relationships)
    warm_count = total_investors - cold_count
    
    high_priority_cold = [
        r for r in cold_relationships 
        if r.get("raise_priority", 5) <= 2
    ]
    
    return {
        "total_investors": total_investors,
        "warm_relationships": warm_count,
        "cold_relationships": cold_count,
        "high_priority_cold": len(high_priority_cold),
        "cold_investors": cold_relationships[:5],
    }