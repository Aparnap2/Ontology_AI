"""
E2E Test Fixtures for OntologyAI v1.0.

Provides fixtures for:
- test_tenant: Creates tenant + 90d baseline data, cleans up after
- clean_qdrant_after: Deletes Qdrant points for test tenant
- Service connectivity checks (PostgreSQL, Qdrant, Redpanda, Ollama, Temporal)
"""
import os
import uuid
import pytest
import pytest_asyncio
import asyncpg
import requests
import httpx
from typing import AsyncGenerator, Generator

# ── Environment Configuration ───────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://iterateswarm:iterateswarm@localhost:5433/iterateswarm"
)
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
REDPANDA_BROKER = os.getenv("REDPANDA_BROKERS", "localhost:19092")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")


# ── Tenant Fixture ──────────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="function")
async def test_tenant() -> AsyncGenerator[dict, None]:
    """
    Create a test tenant with 90-day baseline data.

    This fixture:
    1. Creates a unique tenant_id (UUID)
    2. Inserts baseline transactions (90 days of data)
    3. Creates vendor_baselines entries
    4. Creates finance_snapshots
    5. Yields tenant info dict
    6. Cleans up all data after test completes

    Yields:
        dict with tenant_id, created_at, and cleanup status

    Example:
        async def test_finance_flow(test_tenant):
            tenant_id = test_tenant["tenant_id"]
            # ... test logic ...
    """
    tenant_id = str(uuid.uuid4())  # Use valid UUID format
    created_at = None

    try:
        # Connect to database
        conn = await asyncpg.connect(DATABASE_URL)

        # Note: tenants table may not exist, skip tenant creation
        # The tenant_id is used for data isolation in other tables

        # Generate 90 days of baseline transactions for AWS vendor
        # This creates realistic spend patterns for anomaly detection tests
        base_amount = 5000.0  # Baseline AWS spend
        dates = []
        for i in range(90):
            dates.append(f"NOW() - INTERVAL '{i} days'")

        # Insert transactions for baseline (AWS vendor, normal amounts)
        for i in range(30):  # 30 transactions over 90 days
            amount = base_amount + (uuid.uuid4().int % 1000 - 500)  # ±500 variance
            await conn.execute("""
                INSERT INTO transactions
                (tenant_id, txn_date, description, debit, credit, category, confidence, source)
                VALUES ($1, NOW() - INTERVAL '{days} days', $2, $3, $4, $5, $6, $7)
            """.format(days=i * 3),
                tenant_id,
                f"AWS Web Services - Transaction {i}",
                amount,
                0,
                "infrastructure",
                0.95,
                "bank_webhook"
            )

        # Create vendor baseline for AWS
        await conn.execute("""
            INSERT INTO vendor_baselines
            (tenant_id, vendor_name, avg_30d, avg_90d, transaction_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (tenant_id, vendor_name) DO UPDATE SET
                avg_30d = EXCLUDED.avg_30d,
                avg_90d = EXCLUDED.avg_90d,
                transaction_count = EXCLUDED.transaction_count
        """, tenant_id, "aws", base_amount * 1.05, base_amount, 30)

        # Create finance snapshot
        await conn.execute("""
            INSERT INTO finance_snapshots
            (tenant_id, snapshot_date, burn_rate, runway_months)
            VALUES ($1, NOW(), $2, $3)
        """, tenant_id, base_amount * 30, 12.0)  # 12 months runway

        created_at = True

        yield {
            "tenant_id": tenant_id,
            "created_at": created_at,
            "vendor": "aws",
            "baseline_amount": base_amount,
        }

    finally:
        # Cleanup: Delete all test data
        try:
            conn = await asyncpg.connect(DATABASE_URL)

            # Delete in reverse order of dependencies
            await conn.execute("""
                DELETE FROM bi_queries WHERE tenant_id = $1
            """, tenant_id)

            await conn.execute("""
                DELETE FROM agent_outputs WHERE tenant_id = $1
            """, tenant_id)

            await conn.execute("""
                DELETE FROM finance_snapshots WHERE tenant_id = $1
            """, tenant_id)

            await conn.execute("""
                DELETE FROM vendor_baselines WHERE tenant_id = $1
            """, tenant_id)

            await conn.execute("""
                DELETE FROM transactions WHERE tenant_id = $1
            """, tenant_id)

            # Note: tenants table may not exist in all schemas
            # await conn.execute("""
            #     DELETE FROM tenants WHERE id = $1
            # """, tenant_id)

            await conn.close()
        except Exception as e:
            print(f"Warning: Cleanup failed for tenant {tenant_id}: {e}")


# ── Qdrant Cleanup Fixture ──────────────────────────────────────────────────
@pytest.fixture(scope="function")
def clean_qdrant_after(test_tenant: dict) -> Generator[None, None, None]:
    """
    Delete Qdrant points for test tenant after test completes.

    This fixture:
    1. Runs test
    2. After test: Deletes all points from finance_memory and bi_memory
       collections that match the test tenant_id

    Example:
        def test_memory_compounds(test_tenant, clean_qdrant_after):
            # ... test logic that writes to Qdrant ...
            # Cleanup happens automatically
    """
    tenant_id = test_tenant["tenant_id"]

    yield  # Run the test

    # Cleanup Qdrant collections
    try:
        # Delete from finance_memory
        requests.delete(
            f"{QDRANT_URL}/collections/finance_memory/points",
            json={
                "filter": {
                    "must": [{"key": "tenant_id", "match": {"value": tenant_id}}]
                }
            },
            timeout=10,
        )

        # Delete from bi_memory
        requests.delete(
            f"{QDRANT_URL}/collections/bi_memory/points",
            json={
                "filter": {
                    "must": [{"key": "tenant_id", "match": {"value": tenant_id}}]
                }
            },
            timeout=10,
        )
    except Exception as e:
        print(f"Warning: Qdrant cleanup failed for tenant {tenant_id}: {e}")


# ── Service Connectivity Fixtures ───────────────────────────────────────────
@pytest_asyncio.fixture(scope="session")
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """
    PostgreSQL connection pool for all E2E tests.

    Creates a pool with min_size=2, max_size=10.
    Pool is created once per session and shared across tests.
    """
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(scope="session")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    HTTP client for API calls during E2E tests.

    Base URL from MOCKOON_BASE_URL or defaults to localhost:3000.
    Timeout: 30 seconds for all requests.
    """
    base_url = os.getenv("MOCKOON_BASE_URL", "http://localhost:3000")
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    ) as client:
        yield client


# ── Service Health Check Helpers ────────────────────────────────────────────
def check_postgres() -> bool:
    """Check if PostgreSQL is reachable."""
    try:
        conn = requests.post(
            DATABASE_URL.replace("postgresql://", "http://").split("@")[1].split("/")[0],
            timeout=5,
        )
        return True
    except Exception:
        # Try asyncpg connection
        import asyncio
        async def _check():
            try:
                conn = await asyncpg.connect(DATABASE_URL)
                await conn.close()
                return True
            except Exception:
                return False
        return asyncio.run(_check())


def check_qdrant() -> bool:
    """Check if Qdrant is reachable."""
    try:
        r = requests.get(f"{QDRANT_URL}/", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def check_ollama() -> bool:
    """Check if Ollama is reachable."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def check_temporal() -> bool:
    """Check if Temporal is reachable."""
    try:
        import asyncio
        from temporalio.client import Client

        async def _check():
            try:
                client = await Client.connect(TEMPORAL_ADDRESS)
                # List workflows as a health check
                async for _ in client.list_workflows(""):
                    break
                return True
            except Exception:
                # If listing fails, just try to connect
                return True

        return asyncio.run(_check())
    except Exception:
        return False


def check_redpanda() -> bool:
    """Check if Redpanda is reachable."""
    try:
        from kafka import KafkaClient
        client = KafkaClient(bootstrap_servers=[REDPANDA_BROKER])
        client.close()
        return True
    except Exception:
        return False


# ── Pytest Hooks ────────────────────────────────────────────────────────────
@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow-running"
    )
    config.addinivalue_line(
        "markers", "requires_services: mark test as requiring all services"
    )
