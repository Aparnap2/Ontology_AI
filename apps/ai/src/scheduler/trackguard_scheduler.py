"""
APScheduler-based job scheduler for TrackGuard.

Replaces Temporal for simple schedule-driven jobs.
"""
from __future__ import annotations

import logging
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://trackguard:trackguard@localhost:5432/trackguard")

jobstores = {
    "default": SQLAlchemyJobStore(url=DATABASE_URL),
}

job_defaults = {
    "coalesce": True,
    "max_instances": 1,
    "misfire_grace_time": 300,
}

scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    job_defaults=job_defaults,
    timezone="UTC",
)


def register_tenant_schedules(tenant_id: str) -> None:
    """
    Register all scheduled jobs for a tenant.

    Jobs:
    - startup_guardian: Every 6 hours (health check + Slack alert)
    - finance_guardian: Every 6 hours
    - bi_pulse: Daily at 8am
    - ops_watch: Every 4 hours
    - investor_update: Monday at 7am
    - weekly_synthesis: Monday at 7:05am
    """
    log.info(f"Registering schedules for tenant: {tenant_id}")

    scheduler.add_job(
        run_startup_guardian_job,
        trigger=IntervalTrigger(hours=6),
        args=[tenant_id],
        id=f"startup_guardian_{tenant_id}",
        replace_existing=True,
    )

    scheduler.add_job(
        run_finance_guardian,
        trigger=IntervalTrigger(hours=6),
        args=[tenant_id],
        id=f"finance_guardian_{tenant_id}",
        replace_existing=True,
    )

    scheduler.add_job(
        run_bi_pulse,
        trigger=CronTrigger(hour=8, minute=0),
        args=[tenant_id],
        id=f"bi_pulse_{tenant_id}",
        replace_existing=True,
    )

    scheduler.add_job(
        run_ops_watch,
        trigger=IntervalTrigger(hours=4),
        args=[tenant_id],
        id=f"ops_watch_{tenant_id}",
        replace_existing=True,
    )

    scheduler.add_job(
        run_investor_update,
        trigger=CronTrigger(day_of_week="mon", hour=7, minute=0),
        args=[tenant_id],
        id=f"investor_update_{tenant_id}",
        replace_existing=True,
    )

    scheduler.add_job(
        run_weekly_synthesis,
        trigger=CronTrigger(day_of_week="mon", hour=7, minute=5),
        args=[tenant_id],
        id=f"weekly_synthesis_{tenant_id}",
        replace_existing=True,
    )

    log.info(f"Registered 6 jobs for tenant: {tenant_id}")


def unregister_tenant_schedules(tenant_id: str) -> None:
    """Remove all scheduled jobs for a tenant."""
    job_ids = [
        f"startup_guardian_{tenant_id}",
        f"finance_guardian_{tenant_id}",
        f"bi_pulse_{tenant_id}",
        f"ops_watch_{tenant_id}",
        f"investor_update_{tenant_id}",
        f"weekly_synthesis_{tenant_id}",
    ]

    for job_id in job_ids:
        scheduler.remove_job(job_id)

    log.info(f"Unregistered schedules for tenant: {tenant_id}")


def get_jobs_for_tenant(tenant_id: str) -> list[dict]:
    """Get all scheduled jobs for a tenant."""
    jobs = scheduler.get_jobs()
    tenant_jobs = [j for j in jobs if j.id.endswith(f"_{tenant_id}")]
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        }
        for job in tenant_jobs
    ]


def start_scheduler() -> None:
    """Start the scheduler."""
    if not scheduler.running:
        scheduler.start()
        log.info("APScheduler started")


def shutdown_scheduler() -> None:
    """Shutdown the scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        log.info("APScheduler shutdown")


def is_running() -> bool:
    """Check if scheduler is running."""
    return scheduler.running


# Import orchestration functions at module level
def run_startup_guardian_job(tenant_id: str) -> dict:
    """Run startup guardian job."""
    from src.orchestration.run_startup_guardian import run_startup_guardian as _run
    import asyncio
    return asyncio.run(_run(tenant_id))


def run_finance_guardian(tenant_id: str) -> dict:
    """Run finance guardian job."""
    from src.orchestration.run_finance_guardian import run_finance_guardian as _run
    import asyncio
    return asyncio.run(_run(tenant_id))


def run_bi_pulse(tenant_id: str) -> dict:
    """Run BI pulse job."""
    from src.orchestration.run_bi_pulse import run_bi_pulse as _run
    import asyncio
    return asyncio.run(_run(tenant_id))


def run_ops_watch(tenant_id: str) -> dict:
    """Run ops watch job."""
    from src.orchestration.run_ops_watch import run_ops_watch as _run
    import asyncio
    return asyncio.run(_run(tenant_id))


def run_investor_update(tenant_id: str) -> dict:
    """Run investor update job."""
    from src.orchestration.run_investor_update import run_investor_update as _run
    import asyncio
    return asyncio.run(_run(tenant_id))


def run_weekly_synthesis(tenant_id: str) -> dict:
    """Run weekly synthesis job."""
    from src.orchestration.run_weekly_synthesis import run_weekly_synthesis as _run
    import asyncio
    return asyncio.run(_run(tenant_id))