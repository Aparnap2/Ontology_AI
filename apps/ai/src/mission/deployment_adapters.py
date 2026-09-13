"""Deployment adapters — typed Protocol interfaces for infrastructure.

Every infrastructure dependency is accessed through a Protocol class.
This proves the application does not import raw boto3, aioredis,
or vendor SDKs at the domain boundary — it only calls typed methods
on adapter instances injected at the seam.

Production replaces these adapters with real implementations; tests
provide deterministic fakes. The domain code never observes the difference.
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Database Adapter
# ---------------------------------------------------------------------------


@runtime_checkable
class DatabaseAdapter(Protocol):
    """Typed interface for all database operations.

    Production binds this to asyncpg / SQLAlchemy; tests bind to a dict-backed
    fake. The domain never imports a driver directly.
    """

    async def execute(self, query: str, params: dict[str, Any]) -> Any:
        """Execute a parameterized query and return the result."""
        ...

    async def fetch_one(self, query: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Fetch a single row or None."""
        ...

    async def fetch_all(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Fetch all matching rows."""
        ...

    async def close(self) -> None:
        """Release the connection."""
        ...


# ---------------------------------------------------------------------------
# Event Bus Adapter
# ---------------------------------------------------------------------------


@runtime_checkable
class EventBusAdapter(Protocol):
    """Typed interface for event publishing.

    Production binds to Redis Streams (aioredis); tests bind to an in-memory
    list. The domain never imports redis/aioredis directly.
    """

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Publish a message to a topic."""
        ...

    async def subscribe(self, topic: str) -> Any:
        """Subscribe to a topic (returns an async iterator)."""
        ...

    async def close(self) -> None:
        """Release the connection."""
        ...


# ---------------------------------------------------------------------------
# LLM Adapter
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMAdapter(Protocol):
    """Typed interface for LLM inference.

    Production binds to the OpenAI-compatible SDK (Azure AI Foundry, Groq,
    Ollama); tests bind to a deterministic stub. The domain never imports
    openai/ollama/google-genai directly at the boundary.
    """

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        """Complete a chat and return the assistant message content."""
        ...

    async def close(self) -> None:
        """Release the connection."""
        ...


# ---------------------------------------------------------------------------
# Vendor HTTP Adapter
# ---------------------------------------------------------------------------


@runtime_checkable
class VendorHTTPAdapter(Protocol):
    """Typed interface for vendor HTTP calls (Jira, Notion, Slack, Salesforce).

    Production binds to httpx.AsyncClient; tests bind to respx mock or a
    deterministic fake. The domain never imports httpx directly at the
    boundary.
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request and return the parsed JSON response."""
        ...

    async def close(self) -> None:
        """Release the connection."""
        ...


# ---------------------------------------------------------------------------
# Vector Store Adapter
# ---------------------------------------------------------------------------


@runtime_checkable
class VectorStoreAdapter(Protocol):
    """Typed interface for vector similarity search.

    Production binds to Qdrant; tests bind to an in-memory cosine calculator.
    The domain never imports qdrant_client directly at the boundary.
    """

    async def upsert(self, collection: str, id: str, vector: list[float], payload: dict[str, Any]) -> None:
        """Insert or update a vector record."""
        ...

    async def search(self, collection: str, vector: list[float], limit: int = 5) -> list[dict[str, Any]]:
        """Return the top-k nearest neighbors."""
        ...

    async def close(self) -> None:
        """Release the connection."""
        ...


# ---------------------------------------------------------------------------
# RuntimeConfig — centralized infrastructure configuration
# ---------------------------------------------------------------------------

#: Maps each logical service (as declared in ``config/deployment.yaml``)
#: to the environment variable the runtime reads. No infrastructure
#: address is hardcoded anywhere else: callers read endpoints from
#: :class:`RuntimeConfig`, never from literals.
SERVICE_ENV_VARS: dict[str, str] = {
    "database": "DATABASE_URL",
    "temporal": "TEMPORAL_ADDRESS",
    "llm": "LLM_ENDPOINT",
    "event_bus": "EVENT_BROKER_URL",
    "vendor_api": "VENDOR_API_URL",
    "otel": "OTEL_ENDPOINT",
    "qdrant": "QDRANT_URL",
    "neo4j": "NEO4J_URI",
}

#: Local-development defaults, mirroring ``config/deployment.yaml``.
#: Production overrides every value via environment — the defaults exist
#: only so ``from_env()`` is total without configuration.
SERVICE_DEFAULTS: dict[str, str] = {
    "database": "postgresql://localhost:5432/ontologyai",
    "temporal": "localhost:7233",
    "llm": "http://localhost:11434/v1",
    "event_bus": "redis://localhost:6379",
    "vendor_api": "http://localhost:3003",
    "otel": "http://localhost:4318",
    "qdrant": "http://localhost:6333",
    "neo4j": "bolt://localhost:7687",
}


class RuntimeConfig(BaseModel):
    """Centralized infrastructure configuration for the OntologyAI runtime.

    Every infrastructure dependency (database, workflow engine, LLM
    gateway, event bus, vendor API, tracing, vector store, graph store)
    is a field on this model. Values are read from environment variables
    (see :data:`SERVICE_ENV_VARS`) with local defaults (see
    :data:`SERVICE_DEFAULTS`). No module outside this one resolves an
    infrastructure address: there is no environment-name branching
    anywhere — the same code path runs in every environment and only the
    injected values change.

    Strict (``extra="forbid"``): unknown fields are rejected so a typo'd
    endpoint name fails loudly instead of silently falling back.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    database_url: str = Field(min_length=1)
    temporal_address: str = Field(min_length=1)
    llm_endpoint: str = Field(min_length=1)
    event_broker_url: str = Field(min_length=1)
    vendor_api_url: str = Field(min_length=1)
    otel_endpoint: str = Field(min_length=1)
    qdrant_url: str = Field(min_length=1)
    neo4j_uri: str = Field(min_length=1)

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        """Build a config from the process environment with local defaults."""
        values: dict[str, str] = {}
        field_for_service: dict[str, str] = {
            "database": "database_url",
            "temporal": "temporal_address",
            "llm": "llm_endpoint",
            "event_bus": "event_broker_url",
            "vendor_api": "vendor_api_url",
            "otel": "otel_endpoint",
            "qdrant": "qdrant_url",
            "neo4j": "neo4j_uri",
        }
        for service, field in field_for_service.items():
            env_var: str = SERVICE_ENV_VARS[service]
            default: str = SERVICE_DEFAULTS[service]
            raw: str | None = os.environ.get(env_var)
            values[field] = raw if raw else default
        return cls.model_validate(values)

    def endpoint_for(self, service: str) -> str:
        """Return the configured endpoint for a logical *service* name."""
        field_for_service: dict[str, str] = {
            "database": self.database_url,
            "temporal": self.temporal_address,
            "llm": self.llm_endpoint,
            "event_bus": self.event_broker_url,
            "vendor_api": self.vendor_api_url,
            "otel": self.otel_endpoint,
            "qdrant": self.qdrant_url,
            "neo4j": self.neo4j_uri,
        }
        try:
            return field_for_service[service]
        except KeyError:
            raise KeyError(f"unknown infrastructure service: {service!r}") from None
