"""OntologyAI V5.1 — Canonical Object Type schema definitions.

Strict Pydantic v2 models for the six canonical business Object Types that
specialists read/write through governed actions. Every model uses
``extra="forbid"`` and ``strict=True`` so that:

* unknown/extra fields are rejected (no silent schema drift), and
* type coercion is disabled (wrong types raise ``ValidationError``).

The six canonical types (PRD §12) are:
    Party, Engagement, MoneyEvent, Issue, Message, PlannedAction
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class Party(BaseModel):
    """A person or organization relevant to the business (PRD §12.1)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: Literal[
        "customer", "supplier", "employee", "contractor", "partner", "approver"
    ]
    name: str
    status: Literal["active", "inactive", "at_risk", "blocked"]
    owner: Optional[str] = None
    contact_points: list[str] = []
    notes: Optional[str] = None
    source_refs: list[str] = []


class Engagement(BaseModel):
    """A unit of work, commercial motion, or deliverable (PRD §12.2)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: Literal["deal", "order", "job", "project", "service_case"]
    title: str
    status: Literal[
        "new", "quoted", "active", "blocked", "done", "billed", "closed"
    ]
    owner: Optional[str] = None
    value: Optional[float] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    source_refs: list[str] = []


class MoneyEvent(BaseModel):
    """A financial event or obligation (PRD §12.3)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: Literal[
        "receivable", "payable", "payment", "refund", "writeoff", "expense"
    ]
    amount: float
    currency: str
    status: Literal[
        "open", "due", "paid", "partial", "overdue", "cancelled"
    ]
    due_date: Optional[str] = None
    occurred_at: Optional[str] = None
    counterparty_id: Optional[str] = None
    notes: Optional[str] = None
    source_refs: list[str] = []


class Issue(BaseModel):
    """A blocker, dispute, delay, defect, or incident (PRD §12.4)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: Literal["delay", "dispute", "defect", "incident", "risk", "blocker"]
    severity: Literal["low", "medium", "high", "critical"]
    status: Literal[
        "open", "investigating", "waiting", "resolved", "closed"
    ]
    opened_at: Optional[str] = None
    resolved_at: Optional[str] = None
    owner: Optional[str] = None
    summary: str
    notes: Optional[str] = None
    source_refs: list[str] = []


class Message(BaseModel):
    """A communication artifact (PRD §12.5)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    channel: Literal[
        "email", "whatsapp", "call_note", "sms", "note", "meeting_summary"
    ]
    thread_id: Optional[str] = None
    timestamp: Optional[str] = None
    direction: Literal["inbound", "outbound", "internal"]
    summary: str
    sentiment: Literal["positive", "neutral", "negative", "mixed", "unknown"]
    needs_action: bool = False
    source_refs: list[str] = []


class PlannedAction(BaseModel):
    """A proposed or governed change (PRD §12.6)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    type: str
    title: str
    blast_radius: Literal["low", "medium", "high"]
    status: Literal[
        "draft",
        "pending_approval",
        "approved",
        "rejected",
        "executing",
        "completed",
        "failed",
    ]
    requested_by: str
    target_object_type: Literal[
        "Party", "Engagement", "MoneyEvent", "Issue", "Message", "Workflow"
    ]
    target_id: str
    rationale: str
    requires_approval: bool = False
    execution_payload: Optional[dict] = None
    source_refs: list[str] = []


# Registry of all canonical Object Types by name, used by governance/adapter
# layers and tests. Exactly the six PRD §12 types.
OBJECT_TYPES = {
    "Party": Party,
    "Engagement": Engagement,
    "MoneyEvent": MoneyEvent,
    "Issue": Issue,
    "Message": Message,
    "PlannedAction": PlannedAction,
}
