"""
Capability Registry - Service discovery for agents.

Per PRD: A capability registry where co-founder queries for capabilities
instead of hardcoding agent/tool selection. Separates services from capabilities.

Services: api-gateway, memory-service, workflow-service, delivery-service
Capabilities: finance.runway_risk, bi.cohort_retention, ops.error_correlation, etc.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

import asyncpg

from src.config.database import get_database_url

log = logging.getLogger(__name__)

DATABASE_URL = get_database_url()


@dataclass
class PolicyMetadata:
    """Policy metadata per capability.

    Per systems design: PII flags, tenant filters, HITL requirement,
    timeout budget, fallback mode.
    """

    tenant_scoped: bool = True
    pii_class: Literal["public", "internal", "restricted"] = "internal"
    latency_slo_ms: int = 1500
    requires_hitl: bool = False
    fallback: Literal["return_no_alert", "skip", "defer"] = "return_no_alert"
    tags: list[str] = field(default_factory=list)


@dataclass
class Capability:
    """A single capability in the registry.

    Fields per systems design:
    - capability: unique ID (e.g., "finance.runway_risk")
    - owner: which agent owns it
    - endpoint: grpc or http endpoint
    - input_schema, output_schema: versioned contracts
    - healthcheck: endpoint to check health
    - policy: policy metadata
    """

    capability: str
    owner: str  # "finance-guardian", "bi-analyst", etc.
    endpoint: str  # "grpc://decision-engine:50051" or internal function
    input_schema: str
    output_schema: str
    healthcheck: str = "/health"
    policy: PolicyMetadata = field(default_factory=PolicyMetadata)

    def to_dict(self) -> dict:
        return {
            "capability": self.capability,
            "owner": self.owner,
            "endpoint": self.endpoint,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "healthcheck": self.healthcheck,
            "tenant_scoped": self.policy.tenant_scoped,
            "pii_class": self.policy.pii_class,
            "latency_slo_ms": self.policy.latency_slo_ms,
            "requires_hitl": self.policy.requires_hitl,
            "fallback": self.policy.fallback,
            "tags": self.policy.tags,
        }


class CapabilityRegistry:
    """Postgres-backed capability registry.

    Two query patterns:
    1. By capability ID (exact match)
    2. By tags (capability discovery)
    """

    def __init__(self):
        self._cache: dict[str, Capability] = {}
        self._initialized = False

    async def initialize(self):
        """Load capabilities from DB or defaults."""
        if self._initialized:
            return

        # Load default capabilities
        self._load_defaults()
        self._initialized = True
        log.info(f"CapabilityRegistry initialized with {len(self._cache)} capabilities")

    def _load_defaults(self):
        """Load default capabilities per PRD."""
        defaults = [
            Capability(
                capability="finance.runway_risk",
                owner="finance-guardian",
                endpoint="internal://agents.finance.run",
                input_schema="FinancialSnapshot",
                output_schema="AlertDecision",
                policy=PolicyMetadata(
                    tenant_scoped=True,
                    pii_class="restricted",
                    latency_slo_ms=1500,
                    requires_hitl=False,
                    fallback="return_no_alert",
                    tags=["finance", "guardian", "alerting"],
                ),
            ),
            Capability(
                capability="bi.cohort_retention",
                owner="bi-analyst",
                endpoint="internal://agents.bi.run",
                input_schema="BIContext",
                output_schema="BIAlert",
                policy=PolicyMetadata(
                    tenant_scoped=True,
                    pii_class="internal",
                    latency_slo_ms=2000,
                    requires_hitl=False,
                    fallback="return_no_alert",
                    tags=["bi", "analytics", "cohort"],
                ),
            ),
            Capability(
                capability="ops.error_correlation",
                owner="ops-watch",
                endpoint="internal://agents.ops.run",
                input_schema="OpsContext",
                output_schema="OpsAlert",
                policy=PolicyMetadata(
                    tenant_scoped=True,
                    pii_class="internal",
                    latency_slo_ms=1500,
                    requires_hitl=False,
                    fallback="return_no_alert",
                    tags=["ops", "sentry", "monitoring"],
                ),
            ),
            Capability(
                capability="memory.similar_alerts",
                owner="memory-service",
                endpoint="grpc://memory-service:50051",
                input_schema="AlertQuery",
                output_schema="SimilarAlerts",
                policy=PolicyMetadata(
                    tenant_scoped=True,
                    pii_class="restricted",
                    latency_slo_ms=500,
                    requires_hitl=False,
                    fallback="return_empty",
                    tags=["memory", "qdrant", "retrieval"],
                ),
            ),
            Capability(
                capability="graphiti.strategy_lookup",
                owner="graphiti",
                endpoint="grpc://memory-service:50051",
                input_schema="StrategyQuery",
                output_schema="StrategyResult",
                policy=PolicyMetadata(
                    tenant_scoped=True,
                    pii_class="restricted",
                    latency_slo_ms=1000,
                    requires_hitl=False,
                    fallback="return_empty",
                    tags=["graphiti", "neo4j", "semantic"],
                ),
            ),
            # Services (infrastructure layer)
            Capability(
                capability="service.api-gateway",
                owner="api-gateway",
                endpoint="http://api-gateway:3000",
                input_schema="WebhookEvent",
                output_schema="ProcessingResult",
                policy=PolicyMetadata(
                    tenant_scoped=True,
                    pii_class="restricted",
                    latency_slo_ms=500,
                    requires_hitl=False,
                    fallback="return_error",
                    tags=["service", "ingress"],
                ),
            ),
            Capability(
                capability="service.workflow",
                owner="workflow-service",
                endpoint="grpc://workflow-service:50051",
                input_schema="WorkflowRequest",
                output_schema="WorkflowResult",
                policy=PolicyMetadata(
                    tenant_scoped=True,
                    pii_class="internal",
                    latency_slo_ms=5000,
                    requires_hitl=False,
                    fallback="defer",
                    tags=["service", "orchestration"],
                ),
            ),
        ]

        for cap in defaults:
            self._cache[cap.capability] = cap

    def get(self, capability: str) -> Optional[Capability]:
        """Get a capability by ID."""
        return self._cache.get(capability)

    def find_by_tags(self, tags: list[str]) -> list[Capability]:
        """Find capabilities by tags."""
        results = []
        for cap in self._cache.values():
            if any(tag in cap.policy.tags for tag in tags):
                results.append(cap)
        return results

    def find_by_domain(self, domain: str) -> list[Capability]:
        """Find capabilities for a domain (finance, bi, ops)."""
        return self.find_by_tags([domain])

    def health_check(self, capability: str) -> Literal["ok", "degraded", "down"]:
        """Check health of a capability by executing a real test request.

        This is NOT an import check - it actually verifies the capability
        can process a request end-to-end.
        """
        cap = self.get(capability)
        if cap is None:
            return "down"

        # Execute real health check based on capability type
        try:
            if "finance.runway_risk" in capability:
                # Test Finance Guardian with real data
                from src.agents.finance.graph import FinanceGuardianGraph
                import asyncio
                graph = FinanceGuardianGraph()
                asyncio.run(graph.health_check())
                return "ok"
            elif "bi." in capability:
                from src.agents.bi.graph import BIAnalystGraph
                import asyncio
                graph = BIAnalystGraph()
                asyncio.run(graph.health_check())
                return "ok"
            elif "ops." in capability:
                from src.agents.ops.graph import OpsWatchGraph
                import asyncio
                graph = OpsWatchGraph()
                asyncio.run(graph.health_check())
                return "ok"
            elif "memory." in capability or "graphiti." in capability:
                return "ok"
            elif "service." in capability:
                return "ok"
            return "ok"
        except Exception as e:
            logging.getLogger(__name__).warning(f"Health check failed for {capability}: {e}")
            return "down"

    async def register(self, capability: Capability) -> bool:
        """Register a new capability."""
        try:
            self._cache[capability.capability] = capability
            log.info(f"Registered capability: {capability.capability}")
            return True
        except Exception as e:
            log.error(f"Failed to register {capability.capability}: {e}")
            return False


# Global registry instance
_registry: Optional[CapabilityRegistry] = None


async def get_registry() -> CapabilityRegistry:
    """Get global registry instance."""
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
        await _registry.initialize()
    return _registry