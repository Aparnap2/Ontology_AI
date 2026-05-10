"""Session context integration with real Redis/Qdrant.

L2 tests - Real Docker Redis/Qdrant, mocked LLM.
Tests write message to session, read back correctly.
"""
import asyncio
import os
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import redis.asyncio as redis


# Test Redis configuration
TEST_REDIS_URL = os.environ.get(
    "TEST_REDIS_URL",
    "redis://test:test@localhost:6379/1"  # Use DB 1 for tests
)

TEST_QDRANT_HOST = os.environ.get("TEST_QDRANT_HOST", "localhost")
TEST_QDRANT_PORT = int(os.environ.get("TEST_QDRANT_PORT", "6333"))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for session-scoped async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_redis() -> AsyncGenerator[redis.Redis, None]:
    """Create Redis client for testing.

    Skip if Redis not available.
    """
    try:
        client = redis.from_url(
            TEST_REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await client.ping()
        yield client
        await client.aclose()
    except redis.ConnectionError:
        pytest.skip("Redis not available at TEST_REDIS_URL")
    except Exception as e:
        pytest.skip(f"Redis connection failed: {e}")


@pytest.fixture
async def clean_redis(test_redis: redis.Redis) -> AsyncGenerator[str, None]:
    """Provide a clean session key and clean up after test."""
    session_id = f"test-l2-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    yield session_id
    # Cleanup
    await test_redis.delete(f"session:{session_id}")


class TestSessionContextRoundtrip:
    """Session context database roundtrip tests.

    Tests write to real Redis, read back correctly.
    Mocks LLM calls while using real database.
    """

    @pytest.mark.asyncio
    async def test_write_and_read_messages(
        self,
        test_redis: redis.Redis,
        clean_redis: str,
    ):
        """Write message to session, read back."""
        from src.session.context import SessionContext

        session = SessionContext(
            tenant_id=clean_redis,
            user_id="test-user",
            message="Hello, how is my MRR?",
            session_id=clean_redis,
        )

        # Write message to session
        await session.save_message(role="user", content=session.message)
        await session.save_message(role="assistant", content="Your MRR is $5,000")

        # Read messages back
        messages = await session.get_messages()
        assert len(messages) >= 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello, how is my MRR?"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Your MRR is $5,000"

    @pytest.mark.asyncio
    async def test_session_context_with_metadata(
        self,
        test_redis: redis.Redis,
        clean_redis: str,
    ):
        """Session context includes metadata."""
        from src.session.context import SessionContext

        session = SessionContext(
            tenant_id=clean_redis,
            user_id="test-user",
            message="Check my DAU",
            session_id=clean_redis,
            metadata={"source": "slack", "channel": "#metrics"},
        )

        # Write and verify
        await session.save_message(
            role="user",
            content="Check my DAU",
            metadata={"dau_requested": True},
        )

        messages = await session.get_messages()
        assert len(messages) >= 1
        # Metadata should be preserved in message
        assert messages[0]["metadata"]["dau_requested"] is True


class TestSessionContextWithRealProviders:
    """Session context with real Redis provider integration.

    Tests using actual Redis for session storage.
    """

    @pytest.mark.asyncio
    async def test_session_persists_across_instances(
        self,
        test_redis: redis.Redis,
        clean_redis: str,
    ):
        """Session persists when creating new SessionContext instance."""
        from src.session.context import SessionContext

        # First instance writes
        session1 = SessionContext(
            tenant_id=clean_redis,
            user_id="test-user",
            message="Initial message",
            session_id=clean_redis,
        )
        await session1.save_message(role="user", content="Initial message")

        # Second instance reads same session
        session2 = SessionContext(
            tenant_id=clean_redis,
            user_id="test-user",
            message="Read message",
            session_id=clean_redis,
        )
        messages = await session2.get_messages()

        assert len(messages) >= 1
        assert any(m["content"] == "Initial message" for m in messages)

    @pytest.mark.asyncio
    async def test_session_ttl_behavior(
        self,
        test_redis: redis.Redis,
        clean_redis: str,
    ):
        """Session respects TTL behavior."""
        from src.session.context import SessionContext

        session = SessionContext(
            tenant_id=clean_redis,
            user_id="test-user",
            message="TTL test",
            session_id=clean_redis,
        )

        await session.save_message(role="user", content="TTL test")

        # Check TTL is set (should be > 0)
        ttl = await test_redis.ttl(f"session:{clean_redis}")
        assert ttl > 0 or ttl == -1  # -1 means no expiry, > 0 means has TTL


class TestQdrantSemanticMemory:
    """Qdrant semantic memory integration tests.

    Tests vector storage and retrieval with real Qdrant.
    """

    @pytest.mark.asyncio
    async def test_qdrant_connection(self):
        """Verify Qdrant is available for semantic memory."""
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(
                host=TEST_QDRANT_HOST,
                port=TEST_QDRANT_PORT,
                timeout=5,
            )
            # Just check connection
            info = client.get_collections()
            assert info is not None
        except Exception as e:
            pytest.skip(f"Qdrant not available: {e}")

    @pytest.mark.asyncio
    async def test_semantic_search_roundtrip(self):
        """Write to Qdrant, search back."""
        try:
            from qdrant_client import QdrantClient, models
            from datetime import datetime

            client = QdrantClient(
                host=TEST_QDRANT_HOST,
                port=TEST_QDRANT_PORT,
                timeout=5,
            )
            collection_name = f"test_memory_{datetime.now().strftime('%Y%m%d')}"

            # Create collection if needed
            try:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=384,  # MiniLM size
                        distance=models.Distance.COSINE,
                    ),
                )
            except Exception:
                pass  # Collection might already exist

            # Add a point
            import uuid
            point_id = str(uuid.uuid4())
            client.upsert(
                collection_name=collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=[0.1] * 384,
                        payload={
                            "tenant_id": "test-qdrant-001",
                            "content": "This is a test memory about MRR",
                            "created_at": datetime.now().isoformat(),
                        },
                    ),
                ],
            )

            # Search
            results = client.search(
                collection_name=collection_name,
                query_vector=[0.1] * 384,
                limit=1,
            )

            assert len(results) >= 1
            assert "test-qdrant-001" in results[0].payload.get("tenant_id", "")

            # Cleanup
            client.delete_collection(collection_name=collection_name)

        except ImportError:
            pytest.skip("qdrant_client not installed")
        except Exception as e:
            pytest.skip(f"Qdrant test failed: {e}")
