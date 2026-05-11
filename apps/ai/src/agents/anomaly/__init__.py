"""Anomaly agent stub."""
from dataclasses import dataclass


@dataclass
class AnomalyState:
    tenant_id: str


def anomaly_graph():
    return None