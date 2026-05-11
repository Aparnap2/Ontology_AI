"""Anomaly agent graph - stub for V3.0."""
from dataclasses import dataclass


@dataclass
class AnomalyGraph:
    tenant_id: str


anomaly_graph = AnomalyGraph(tenant_id="")