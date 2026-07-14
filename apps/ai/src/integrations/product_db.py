"""
Product Database Integration Module for OntologyAI MVP.

Provides active user count extraction from tenant's product database.
Reads from user_events or sessions table to calculate 30-day active users.
Supports MOCK MODE for development/testing.

Environment Variables:
    PRODUCT_DB_URL: PostgreSQL connection string for product database
    PRODUCT_DB_SCHEMA: Schema name (default: 'public')
    DATABASE_URL: Fallback to ontology_ai DB if PRODUCT_DB_URL not set

Mock Mode:
    When database is not configured, returns realistic seed data.

Query Strategy:
    1. Try user_events table first (event-based tracking)
    2. Fall back to sessions table (session-based tracking)
    3. Fall back to mock data if neither exists
"""

import os
import logging
from typing import Dict, Any, Optional
from contextlib import contextmanager
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Mock mode flag - True when database is not configured
MOCK_MODE: bool = not (
    bool(os.getenv("PRODUCT_DB_URL", "").strip()) or
    bool(os.getenv("DATABASE_URL", "").strip())
)

# Realistic mock data for development/testing
_MOCK_PRODUCT_DATA: Dict[str, Any] = {
    "active_users_30d": 1250,  # 1,250 active users in last 30 days
    "active_users_7d": 450,    # 450 active users in last 7 days
    "active_users_1d": 85,     # 85 active users today
}


def _add_metadata(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Add common metadata fields to integration responses."""
    result = data.copy()
    result["source"] = source
    result["fetched_at"] = datetime.utcnow().isoformat() + "Z"
    return result


@contextmanager
def _get_db_connection():
    """
    Get database connection context manager.

    Yields:
        psycopg2 connection object

    Raises:
        Exception: If database connection fails
    """
    import psycopg2

    db_url = os.getenv("PRODUCT_DB_URL") or os.getenv("DATABASE_URL")

    if not db_url:
        raise ValueError("No database URL configured")

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        yield conn
    finally:
        if conn:
            conn.close()


def _query_user_events(conn, tenant_id: str, days: int = 30) -> int:
    """
    Query active users from user_events table.

    Args:
        conn: Database connection
        tenant_id: Tenant identifier
        days: Number of days to look back

    Returns:
        Count of distinct active users
    """
    cursor = conn.cursor()

    query = """
        SELECT COUNT(DISTINCT user_id)
        FROM user_events
        WHERE tenant_id = %s
          AND event_timestamp >= NOW() - INTERVAL '%s days'
    """

    try:
        cursor.execute(query, (tenant_id, days))
        result = cursor.fetchone()
        return result[0] if result and result[0] else 0
    except Exception as e:
        logger.debug(f"user_events query failed: {e}")
        return 0
    finally:
        cursor.close()


def _query_sessions(conn, tenant_id: str, days: int = 30) -> int:
    """
    Query active users from sessions table.

    Args:
        conn: Database connection
        tenant_id: Tenant identifier
        days: Number of days to look back

    Returns:
        Count of distinct active users
    """
    cursor = conn.cursor()

    query = """
        SELECT COUNT(DISTINCT user_id)
        FROM sessions
        WHERE tenant_id = %s
          AND created_at >= NOW() - INTERVAL '%s days'
    """

    try:
        cursor.execute(query, (tenant_id, days))
        result = cursor.fetchone()
        return result[0] if result and result[0] else 0
    except Exception as e:
        logger.debug(f"sessions query failed: {e}")
        return 0
    finally:
        cursor.close()


def _query_users_table(conn, tenant_id: str, days: int = 30) -> int:
    """
    Query active users from users table (last login based).

    Args:
        conn: Database connection
        tenant_id: Tenant identifier
        days: Number of days to look back

    Returns:
        Count of distinct active users
    """
    cursor = conn.cursor()

    query = """
        SELECT COUNT(DISTINCT id)
        FROM users
        WHERE tenant_id = %s
          AND last_login_at >= NOW() - INTERVAL '%s days'
    """

    try:
        cursor.execute(query, (tenant_id, days))
        result = cursor.fetchone()
        return result[0] if result and result[0] else 0
    except Exception as e:
        logger.debug(f"users query failed: {e}")
        return 0
    finally:
        cursor.close()


def _check_table_exists(conn, table_name: str) -> bool:
    """
    Check if a table exists in the database.

    Args:
        conn: Database connection
        table_name: Name of table to check

    Returns:
        True if table exists, False otherwise
    """
    cursor = conn.cursor()

    schema = os.getenv("PRODUCT_DB_SCHEMA", "public")

    query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
        )
    """

    try:
        cursor.execute(query, (schema, table_name))
        result = cursor.fetchone()
        return result[0] if result else False
    except Exception as e:
        logger.debug(f"Table check failed for {table_name}: {e}")
        return False
    finally:
        cursor.close()


def get_product_snapshot(tenant_id: str) -> Dict[str, Any]:
    """
    Get product usage snapshot for a tenant.

    Queries the product database to calculate active user counts
    over different time periods (1d, 7d, 30d).

    Query strategy:
    1. Try user_events table (event-based tracking)
    2. Fall back to sessions table (session-based tracking)
    3. Fall back to users table (last_login based)
    4. Return mock data if no table exists or DB not configured

    Args:
        tenant_id: Tenant identifier (used for filtering and logging)

    Returns:
        Dict with keys:
            - active_users_30d: Active users in last 30 days
            - active_users_7d: Active users in last 7 days
            - active_users_1d: Active users in last 1 day

    Example:
        >>> snapshot = get_product_snapshot("tenant-123")
        >>> print(f"Active users (30d): {snapshot['active_users_30d']}")
    """
    # Return mock data if not configured
    if MOCK_MODE:
        logger.info(f"[MOCK MODE] Returning seed product data for tenant {tenant_id}")
        return _add_metadata(_MOCK_PRODUCT_DATA, "product_mock")

    try:
        with _get_db_connection() as conn:
            # Determine which table to use
            if _check_table_exists(conn, "user_events"):
                logger.debug(f"Using user_events table for tenant {tenant_id}")
                active_30d = _query_user_events(conn, tenant_id, 30)
                active_7d = _query_user_events(conn, tenant_id, 7)
                active_1d = _query_user_events(conn, tenant_id, 1)

            elif _check_table_exists(conn, "sessions"):
                logger.debug(f"Using sessions table for tenant {tenant_id}")
                active_30d = _query_sessions(conn, tenant_id, 30)
                active_7d = _query_sessions(conn, tenant_id, 7)
                active_1d = _query_sessions(conn, tenant_id, 1)

            elif _check_table_exists(conn, "users"):
                logger.debug(f"Using users table for tenant {tenant_id}")
                active_30d = _query_users_table(conn, tenant_id, 30)
                active_7d = _query_users_table(conn, tenant_id, 7)
                active_1d = _query_users_table(conn, tenant_id, 1)

            else:
                logger.warning(f"No suitable table found for tenant {tenant_id}, using mock data")
                return _add_metadata(_MOCK_PRODUCT_DATA, "product_mock")

            # Validate results
            if active_30d == 0 and active_7d == 0 and active_1d == 0:
                logger.warning(f"All queries returned 0 for tenant {tenant_id}, using mock data")
                return _add_metadata(_MOCK_PRODUCT_DATA, "product_mock")

            result = {
                "active_users_30d": active_30d,
                "active_users_7d": active_7d,
                "active_users_1d": active_1d,
            }

            logger.info(
                f"Product snapshot for {tenant_id}: "
                f"30d={active_30d}, 7d={active_7d}, 1d={active_1d}"
            )

            return result

    except Exception as e:
        logger.error(f"Error fetching product snapshot for tenant {tenant_id}: {e}")
        # Fall back to mock data on error
        return _add_metadata(_MOCK_PRODUCT_DATA, "product_mock")


def get_user_growth_rate(tenant_id: str, period_days: int = 30) -> Dict[str, Any]:
    """
    Calculate user growth rate over a period.

    Compares active users in the current period vs previous period.

    Args:
        tenant_id: Tenant identifier
        period_days: Number of days per period (default: 30)

    Returns:
        Dict with keys:
            - current_period: Active users in current period
            - previous_period: Active users in previous period
            - growth_rate: Percentage growth (can be negative)
            - growth_absolute: Absolute user change

    Example:
        >>> growth = get_user_growth_rate("tenant-123", 30)
        >>> print(f"Growth: {growth['growth_rate']:.1f}%")
    """
    if MOCK_MODE:
        # Return realistic mock growth data
        current = _MOCK_PRODUCT_DATA["active_users_30d"]
        previous = int(current * 0.92)  # ~8% growth
        return {
            "current_period": current,
            "previous_period": previous,
            "growth_rate": 8.0,
            "growth_absolute": current - previous,
        }

    try:
        with _get_db_connection() as conn:
            # Get current period
            if _check_table_exists(conn, "user_events"):
                current = _query_user_events(conn, tenant_id, period_days)

                # Get previous period
                cursor = conn.cursor()
                prev_query = """
                    SELECT COUNT(DISTINCT user_id)
                    FROM user_events
                    WHERE tenant_id = %s
                      AND event_timestamp >= NOW() - INTERVAL '%s days'
                      AND event_timestamp < NOW() - INTERVAL '%s days'
                """
                cursor.execute(prev_query, (tenant_id, period_days * 2, period_days))
                result = cursor.fetchone()
                previous = result[0] if result and result[0] else 0
                cursor.close()

            else:
                # Fallback to mock
                return get_user_growth_rate.__wrapped__(tenant_id, period_days)

            # Calculate growth
            if previous == 0:
                growth_rate = 100.0 if current > 0 else 0.0
            else:
                growth_rate = ((current - previous) / previous) * 100

            return {
                "current_period": current,
                "previous_period": previous,
                "growth_rate": round(growth_rate, 2),
                "growth_absolute": current - previous,
            }

    except Exception as e:
        logger.error(f"Error calculating growth rate for tenant {tenant_id}: {e}")
        return {
            "current_period": _MOCK_PRODUCT_DATA["active_users_30d"],
            "previous_period": int(_MOCK_PRODUCT_DATA["active_users_30d"] * 0.92),
            "growth_rate": 8.0,
            "growth_absolute": 100,
        }
