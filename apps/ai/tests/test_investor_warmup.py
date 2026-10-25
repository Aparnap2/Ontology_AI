"""Hermetic tests for investor relations warmup alerts.

The suite provisions the canonical `investor_relationships` migration and
seeds its own tenant, so it never depends on a manually pre-seeded database.

DSN resolution is explicit: `TEST_DATABASE_URL` is required (no implicit
default) and is assigned to `src.db.DATABASE_URL` before the connection pool
is created. This matters because the `deepeval` pytest plugin autoloads
`apps/ai/.env` at collection time, which can otherwise overwrite the intended
test DSN with the application DSN. `DEEPEVAL_DISABLE_DOTENV=1` is an accepted
alternative, but assigning/asserting the pool DSN keeps the test correct even
when the plugin has already loaded dotenv.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

_CANONICAL_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "core"
    / "internal"
    / "db"
    / "migrations"
    / "014_investor_relationships.sql"
)

_TEST_TENANT = "00000000-0000-0000-0000-000000000103"
_EMPTY_TENANT = "99999999-9999-9999-9999-999999999999"


@pytest.fixture()
def investor_db():
    """Provision the canonical schema, seed the test tenant, and clean up."""
    if not TEST_DATABASE_URL:
        pytest.fail(
            "TEST_DATABASE_URL is required for investor warmup tests. "
            "Point it at a disposable PostgreSQL database."
        )

    if not _CANONICAL_MIGRATION.is_file():
        pytest.fail(f"Canonical migration not found at {_CANONICAL_MIGRATION}")

    try:
        conn = psycopg2.connect(TEST_DATABASE_URL)
    except Exception as exc:
        pytest.fail(
            f"Could not connect to TEST_DATABASE_URL ({TEST_DATABASE_URL!r}): "
            f"{exc!r}. These tests require a reachable PostgreSQL database."
        )

    db_module = None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(_CANONICAL_MIGRATION.read_text())
                cur.execute(
                    "DELETE FROM investor_interactions WHERE tenant_id IN (%s, %s)",
                    (_TEST_TENANT, _EMPTY_TENANT),
                )
                cur.execute(
                    "DELETE FROM investor_relationships WHERE tenant_id IN (%s, %s)",
                    (_TEST_TENANT, _EMPTY_TENANT),
                )
                cur.execute(
                    """
                    INSERT INTO investor_relationships
                        (tenant_id, investor_name, firm, last_contact_at,
                         warm_up_days, raise_priority, notes)
                    VALUES
                        (%s, 'Rahul Mehta', 'Sequoia', NOW() - INTERVAL '35 days',
                         30, 1, 'Overdue warmup'),
                        (%s, 'Priya Kapoor', 'Accel', NOW() - INTERVAL '5 days',
                         30, 2, 'Recently contacted')
                    """,
                    (_TEST_TENANT, _TEST_TENANT),
                )

        import src.db as db_module

        os.environ["DATABASE_URL"] = TEST_DATABASE_URL
        db_module.DATABASE_URL = TEST_DATABASE_URL
        db_module.DB.close_pool()
        assert db_module.DATABASE_URL == TEST_DATABASE_URL, (
            "Resolved pool DSN is not the intended TEST_DATABASE_URL"
        )

        yield _TEST_TENANT
    finally:
        if db_module is not None:
            db_module.DB.close_pool()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM investor_interactions WHERE tenant_id IN (%s, %s)",
                    (_TEST_TENANT, _EMPTY_TENANT),
                )
                cur.execute(
                    "DELETE FROM investor_relationships WHERE tenant_id IN (%s, %s)",
                    (_TEST_TENANT, _EMPTY_TENANT),
                )
        conn.close()


@pytest.mark.asyncio
async def test_get_investor_warmup_alerts(investor_db: str):
    """Rahul is overdue and appears; Priya is not overdue and is excluded."""
    from src.orchestration.run_investor_update import get_investor_warmup_alerts

    rows = await get_investor_warmup_alerts(investor_db)

    names = [r["investor_name"] for r in rows]
    assert "Rahul Mehta" in names, f"Overdue investor not returned: {names}"
    assert "Priya Kapoor" not in names, (
        f"Non-overdue investor wrongly returned: {names}"
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_get_investor_status_summary(investor_db: str):
    """Status summary totals tracked investors and ranks the top priority."""
    from src.orchestration.run_investor_update import get_investor_status_summary

    summary = await get_investor_status_summary(investor_db)

    assert summary["total_tracked"] >= 2, "Should track at least 2 investors"
    assert summary["overdue_count"] >= 1, "Rahul must be in overdue count"
    assert summary["top_priority"] == "Rahul Mehta", (
        f"Top priority should be Rahul: {summary['top_priority']}"
    )


@pytest.mark.asyncio
async def test_no_investors_does_not_crash(investor_db: str):
    """A tenant with zero investor relationships returns empty without error."""
    from src.orchestration.run_investor_update import (
        get_investor_status_summary,
        get_investor_warmup_alerts,
    )

    alerts = await get_investor_warmup_alerts(_EMPTY_TENANT)
    summary = await get_investor_status_summary(_EMPTY_TENANT)

    assert alerts == [], f"Expected empty alerts, got: {alerts}"
    assert summary["total_tracked"] == 0
    assert summary["overdue_count"] == 0
    assert summary["top_priority"] is None
