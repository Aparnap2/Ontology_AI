"""OntologyAI V5.2 — Canonical Object Type schema definitions.

Strict Pydantic v2 models for the canonical business Object Types that
specialists read/write through governed actions. Every model uses
``extra="forbid"`` and ``strict=True`` so that:

* unknown/extra fields are rejected (no silent schema drift), and
* type coercion is disabled (wrong types raise ``ValidationError``).

The six PRD §12 types (Party, Engagement, MoneyEvent, Issue, Message,
PlannedAction) plus the Shipment slice, the V6 domain types, and the
Onboarding lifecycle aggregate (ADR-010: Onboarding, Task, Evidence).
Graph models hold REFERENCE IDs only — never embedded mutable objects.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator


# ── Internal counter for deterministic ID generation ───────────────────
_SEQUENCE: int = 0


def _next_seq() -> int:
    """Return the next integer in a monotonic sequence for artifact IDs."""
    global _SEQUENCE
    _SEQUENCE += 1
    return _SEQUENCE


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
    """A blocker, dispute, delay, defect, or incident (PRD §12.4).

    Deviation fields (severity/detected_at/root_cause/affected_entities/
    resolution/escalation) describe a departure from plan. Planned work
    is a ``Task``, never ``Issue(kind="task")`` — "task" is not a valid
    kind.
    """

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
    detected_at: Optional[str] = None
    root_cause: Optional[str] = None
    affected_entities: list[str] = []
    resolution: Optional[str] = None
    escalation: bool = False
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


class Shipment(BaseModel):
    """A fulfillment shipment against an order (Revenue Protection vertical slice)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    order_id: str
    status: Literal["planned", "in_transit", "delivered", "partial", "returned"]
    shipped_value: float
    shipped_at: Optional[str] = None
    carrier: Optional[str] = None
    items: list[dict] = []
    notes: Optional[str] = None
    source_refs: list[str] = []


# ── V6 domain Object Types (Virtual COO operating model) ──────────────────


class Stakeholder(BaseModel):
    """A person with a business role (process owner, approver, reviewer)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    email: str
    role: str
    status: Literal["active", "inactive", "at_risk", "blocked"]
    source_refs: list[str] = []


class Pillar(BaseModel):
    """One of the four MVP business pillars (Marketing, Sales, Ops, Finance)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: Literal["marketing", "sales", "operations", "finance"]
    status: Literal["active", "inactive"] = "active"
    source_refs: list[str] = []


class Process(BaseModel):
    """A repeatable business process with an owner and KPIs."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    pillar: Optional[str] = None
    owner_id: Optional[str] = None
    status: Literal["mapped", "analyzed", "improved", "retired"] = "mapped"
    process_type: str = "core"
    source_refs: list[str] = []


class ProcessStep(BaseModel):
    """A single step within a business process."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    process_id: str
    name: str
    order_index: int = 0
    owner_id: Optional[str] = None
    status: Literal["draft", "active", "deprecated"] = "draft"
    source_refs: list[str] = []


class SOP(BaseModel):
    """A Standard Operating Procedure attached to a process."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    process_id: Optional[str] = None
    owner_id: Optional[str] = None
    status: Literal["draft", "active", "archived"] = "draft"
    current_version_id: Optional[str] = None
    source_refs: list[str] = []


class SOPVersion(BaseModel):
    """A versioned snapshot of an SOP."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    sop_id: str
    version: str
    content_hash: str
    status: Literal["draft", "current", "superseded"] = "draft"
    source_refs: list[str] = []


class Employee(BaseModel):
    """An AI employee role definition (config, not runtime state)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    role: str
    status: Literal["active", "inactive", "paused"] = "active"
    source_refs: list[str] = []


class EmployeeRun(BaseModel):
    """Runtime state of an AI employee (state, not config)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    employee_id: str
    status: Literal["idle", "active", "paused", "offline"] = "idle"
    current_mission_id: Optional[str] = None
    source_refs: list[str] = []


class Mission(BaseModel):
    """A persistent business objective assigned to an AI employee.

    Runtime stays generic: a mission is a bounded AI work unit operating
    *within* one onboarding (ADR-010). ``onboarding_id`` links it to its
    parent aggregate; M1-M6 refs live on ``Onboarding.missions``, never
    here. Aggregate-only fields (customer, missions) must never migrate
    onto this model.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    title: str
    status: Literal["pending", "active", "stalled", "completed", "failed", "archived"] = "pending"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    owner_id: Optional[str] = None
    employee_role: Optional[str] = None
    # DEPRECATED: prefer the Situation link (``situation_id``) for new code.
    # ``onboarding_id`` stays so existing M1-M6 aggregates keep resolving.
    onboarding_id: Optional[str] = None
    situation_id: Optional[str] = None
    # Generic mission target (Phase 1 dual-write): explicit ``target_*`` wins;
    # ``onboarding_id``-only derives ("onboarding", onboarding_id). New code
    # passes explicit targets; ``onboarding_id`` is a deprecated alias.
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    source_refs: list[str] = []

    @model_validator(mode="after")
    def _resolve_target(self) -> "Mission":
        if self.target_type is None and self.target_id is None:
            if self.onboarding_id is not None:
                self.target_type = "onboarding"
                self.target_id = self.onboarding_id
        elif (
            self.target_type == "onboarding"
            and self.target_id is not None
            and self.onboarding_id is not None
            and self.target_id != self.onboarding_id
        ):
            raise ValueError(
                "contradictory mission target: explicit target_* "
                f"({self.target_type!r}, {self.target_id!r}) disagrees with "
                f"onboarding_id={self.onboarding_id!r}"
            )
        return self


class MissionEvent(BaseModel):
    """An immutable, append-only event on a mission timeline."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    mission_id: str
    event_type: str
    version: int = 1
    source_refs: list[str] = []


class MissionSnapshot(BaseModel):
    """A point-in-time capture of a mission's composed state."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    mission_id: str
    version: int = 1
    snapshot_type: Literal["periodic", "on_change", "manual"] = "periodic"
    source_refs: list[str] = []


class Action(BaseModel):
    """A governed, idempotent unit of work executed by an AI employee."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    mission_id: str
    employee_role: str
    capability: str
    risk_tier: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    status: Literal["draft", "pending_approval", "approved", "rejected", "executing", "completed", "failed"] = "draft"
    idempotency_key: str
    source_refs: list[str] = []


class ActionResult(BaseModel):
    """The result of executing an Action, with verification metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    action_id: str
    result_summary: str = ""
    verified: bool = False
    source_refs: list[str] = []


class Outcome(BaseModel):
    """The result of a mission, tied to evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    mission_id: str
    result: Literal["success", "partial", "failure", "na"] = "na"
    evidence_refs: list[str] = []
    source_refs: list[str] = []


class Review(BaseModel):
    """A scheduled review of a process, SOP, or other target."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    target_type: str
    target_id: str
    reviewer: str
    cadence: Optional[str] = None
    source_refs: list[str] = []


class KPI(BaseModel):
    """A measurable key performance indicator for a business process."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    target_value: float
    unit: str
    owner_id: Optional[str] = None
    status: Literal["active", "archived", "draft"] = "active"
    source_refs: list[str] = []


# ── Onboarding lifecycle aggregate (ADR-010) ─────────────────────────────
# First-class business lifecycle: Customer ──enters──> Onboarding
# ──contains──> Missions M1-M6. All cross-entity holders are REFERENCE
# IDs (never embedded mutable Task/Mission objects) so lifecycle state
# survives across missions, retries, and approvals.


class Onboarding(BaseModel):
    """The onboarding lifecycle aggregate root (ADR-010).

    Owns customer, stakeholders, requirements, task refs, issue refs,
    M1-M6 mission refs, and lifecycle state. ``Mission`` is a bounded
    work unit within one onboarding — never model onboarding as
    ``Mission.kind``.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    customer: str
    stakeholders: list[str] = []
    requirements: list[str] = []
    tasks: list[str] = []
    issues: list[str] = []
    missions: list[str] = []
    lifecycle_state: str


class Task(BaseModel):
    """Planned work with owner, due date, and delivery linkage (ADR-010).

    Distinct from ``Issue`` (a deviation from plan). ``external_ref``
    carries the delivery-system key (e.g. a Jira issue key);
    ``linked_requirement`` points at the requirement this work fulfills.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    owner: str
    due_date: Optional[str] = None
    status: str
    priority: str
    linked_requirement: Optional[str] = None
    external_ref: Optional[str] = None
    source_refs: list[str] = []


class Evidence(BaseModel):
    """Connector content ingested as attributed data (ADR-012).

    External text (e.g. Slack "ignore previous instructions …") is
    preserved as evidence content attributed to its reporter via
    ``provenance`` — never as an instruction. ``captured_at`` is the
    freshness timestamp; ``tenant_id`` scopes ownership.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    tenant_id: str
    source: str
    provenance: str
    captured_at: str
    raw_text: str
    normalized_text: str


# ── Situation business-problem aggregate (E2) ─────────────────────────────
# Durable business problem between Evidence and Mission: Event/Evidence
# → Situation → Mission (agent work context) → Action → Outcome.
# A Situation outlives any single mission attempt; missions link in via
# ``Mission.situation_id``. All cross-entity holders are REFERENCE IDs
# (never embedded mutable objects).


class Situation(BaseModel):
    """A durable business problem detected from evidence (E2).

    The unit the business tracks (e.g. a blocked delivery); ``Mission``
    is the agent's bounded work context against it. ``owner_id`` comes
    from owner resolution and stays ``None`` until resolved.
    ``evidence_ids`` cite the supporting evidence; ``checkpoint_id``
    pins the context checkpoint the situation was opened from.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    tenant_id: str
    type: Literal[
        "DELIVERY_BLOCKER",
        "RESOURCE_RISK",
        "DEPENDENCY_DELAY",
        "QUALITY_DEFECT",
        "SCOPE_DRIFT",
        "VENDOR_INCIDENT",
        "SLA_RISK",
        "VENDOR_PERFORMANCE_ISSUE",
    ] = "DELIVERY_BLOCKER"
    affected_entities: list[str] = []
    detected_condition: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    owner_id: Optional[str] = None
    evidence_ids: list[str] = []
    checkpoint_id: str
    business_impact: str
    status: Literal["OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"] = "OPEN"


# Registry of all canonical Object Types by name, used by governance/adapter
# layers and tests. PRD §12 six + Shipment slice + V6 domain + ADR-010 three
# + E2 Situation.
OBJECT_TYPES = {
    "Party": Party,
    "Engagement": Engagement,
    "MoneyEvent": MoneyEvent,
    "Issue": Issue,
    "Message": Message,
    "PlannedAction": PlannedAction,
    "Shipment": Shipment,
    "Stakeholder": Stakeholder,
    "Pillar": Pillar,
    "Process": Process,
    "ProcessStep": ProcessStep,
    "SOP": SOP,
    "SOPVersion": SOPVersion,
    "Employee": Employee,
    "EmployeeRun": EmployeeRun,
    "Mission": Mission,
    "MissionEvent": MissionEvent,
    "MissionSnapshot": MissionSnapshot,
    "Action": Action,
    "ActionResult": ActionResult,
    "Outcome": Outcome,
    "Review": Review,
    "KPI": KPI,
    "Onboarding": Onboarding,
    "Task": Task,
    "Evidence": Evidence,
    "Situation": Situation,
}
