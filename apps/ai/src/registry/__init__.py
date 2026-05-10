"""
Capability Registry - Service discovery for agents.

Per the systems design: agents query registry instead of hardcoded imports.
Models both internal services AND agent capabilities with policy metadata.

Layer: Control plane (Postgres-backed)
"""
from .registry import CapabilityRegistry, Capability, PolicyMetadata
from .health import HealthPoller

__all__ = ["CapabilityRegistry", "Capability", "PolicyMetadata", "HealthPoller"]