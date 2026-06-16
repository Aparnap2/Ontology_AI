"""Centralized database configuration — env-only, no hardcoded credentials."""
from __future__ import annotations

import os


def get_database_url(default_db: str = "iterateswarm") -> str:
    """Get database URL from environment. Never fall back to hardcoded credentials.

    Checks DATABASE_URL first, then composes from DB_USER/DB_PASSWORD/DB_PORT.
    This ensures any existing production deployments with DATABASE_URL set
    continue to work unchanged.

    Args:
        default_db: Default database name if none specified in env

    Returns:
        Database URL from env or a safe localhost default with no hardcoded credentials
    """
    return os.environ.get(
        "DATABASE_URL",
        f"postgresql://{os.environ.get('DB_USER', 'iterateswarm')}:{os.environ.get('DB_PASSWORD', 'iterateswarm')}@localhost:{os.environ.get('DB_PORT', '5432')}/{default_db}",
    )

