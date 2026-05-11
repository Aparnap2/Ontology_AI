"""Pulse agent graph - stub for V3.0."""
from dataclasses import dataclass


@dataclass
class PulseGraph:
    tenant_id: str


pulse_graph = PulseGraph(tenant_id="")