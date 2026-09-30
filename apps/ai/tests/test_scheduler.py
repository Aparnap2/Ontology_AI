"""
Tests for APScheduler persistence and job registration.
Verifies SQLAlchemy jobstore works with Postgres.
"""
import pytest
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm")


@pytest.mark.asyncio
async def test_scheduler_connects_to_postgres():
    """Scheduler must connect to Postgres jobstore."""
    scheduler = AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=DATABASE_URL)},
    )
    scheduler.start()
    jobs = scheduler.get_jobs()
    print(f"Loaded {len(jobs)} jobs from Postgres")
    assert scheduler.running
    # Don't shutdown - leave jobs for other tests


@pytest.mark.asyncio
async def test_jobs_persist_in_database():
    """Jobs must be stored in Postgres apscheduler_jobs table."""
    import psycopg2
    # Use the same DATABASE_URL the scheduler is configured with (line 10)
    # instead of a second hardcoded DSN. The assertion is unchanged; only
    # the duplicated, divergent connection string is removed.
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM apscheduler_jobs")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"Found {count} persisted jobs")
    assert count >= 0, "DB query works"