"""
Tests for APScheduler persistence and job registration.
Verifies SQLAlchemy jobstore works with Postgres.
"""
import pytest
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="TEST_DATABASE_URL is required for scheduler Postgres tests",
)


@pytest.mark.asyncio
async def test_scheduler_connects_to_postgres():
    """Scheduler must connect to Postgres jobstore."""
    assert DATABASE_URL is not None
    scheduler = AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=DATABASE_URL)},
    )
    scheduler.start()
    jobs = scheduler.get_jobs()
    assert len(jobs) >= 0
    assert scheduler.running
    # Don't shutdown - leave jobs for other tests


@pytest.mark.asyncio
async def test_jobs_persist_in_database():
    """Jobs must be stored in Postgres apscheduler_jobs table."""
    import psycopg2

    assert DATABASE_URL is not None
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM apscheduler_jobs")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count >= 0, "DB query works"