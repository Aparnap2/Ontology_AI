"""OntologyAI V4.2 — Object Type schema definitions.

Strict Pydantic v2 models for the canonical business Object Types that
specialists read/write through governed actions. Every model uses
``extra="forbid"`` and ``strict=True`` so that:

* unknown/extra fields are rejected (no silent schema drift), and
* type coercion is disabled (wrong types raise ``ValidationError``).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Customer(BaseModel):
    """A business customer account."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    mrr: float
    health_score: float
    last_contact_at: datetime | None = None


class Deal(BaseModel):
    """A sales opportunity."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    stage: str
    value: float
    close_probability: float
    owner: str


class RevenueMetric(BaseModel):
    """A point-in-time financial snapshot for a period."""

    model_config = ConfigDict(extra="forbid", strict=True)

    period: str
    mrr: float
    burn: float
    runway_days: int


class Incident(BaseModel):
    """An operational incident."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    severity: str
    opened_at: datetime
    resolved_at: datetime | None = None
    root_cause: str


class Message(BaseModel):
    """A communication message (Slack, email, etc.)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    channel: str
    thread_id: str
    sentiment: str
    drafted_by: str


class PlannedAction(BaseModel):
    """A governed action proposed/executed by a specialist."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    type: str
    blast_radius: Literal["low", "medium", "high"]
    status: str
    requested_by: str


# Registry of all Object Types by name, useful for governance/adapter layers.
OBJECT_TYPES = {
    "Customer": Customer,
    "Deal": Deal,
    "RevenueMetric": RevenueMetric,
    "Incident": Incident,
    "Message": Message,
    "PlannedAction": PlannedAction,
}
