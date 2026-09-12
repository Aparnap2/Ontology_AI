"""V6 OntologyAI — All 24 entity models.

Every model uses ``extra="forbid"`` and ``strict=True`` to prevent silent
field injection, and ``from_attributes=True`` for ORM compatibility.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OntologyBaseModel(BaseModel):
    """Base class for all V6 entities.

    - ``extra="forbid"`` — reject unknown fields at construction
    - ``strict=True`` — disallow implicit type coercion
    - ``from_attributes=True`` — enable ORM / ``from_orm`` mode
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        from_attributes=True,
    )


# ── Provenance (nested inside EvidenceRecord) ───────────────────────────


class Provenance(OntologyBaseModel):
    """Provenance metadata for an evidence record.

    Captures the connector → parser segment of the provenance chain.
    Post-normalization steps append to an optional ``provenance_chain`` list.
    """

    connector_version: str
    extraction_method: str
    raw_checksum: str  # SHA256 of raw_content (before parsing)
    retry_count: int = 0


# ── Entity 1: EvidenceRecord ────────────────────────────────────────────


class EvidenceRecord(OntologyBaseModel):
    """Canonical evidence record — the atomic unit of knowledge.

    Every connector ``Fetch`` returns a list of these.  The ``hash`` field
    is the SHA256 of the canonical JSON serialisation of ``tenant_id +
    structured_data`` and is used for exact dedup.
    """

    id: str
    tenant_id: str
    source: str
    source_type: Literal[
        "connector",
        "chat",
        "upload",
        "transcript",
        "spreadsheet",
        "email",
        "screenshot",
        "api",
    ]
    schema_version: str = "v1"  # Evidence schema version (e.g. "slack.v1", "salesforce.v1")
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: Provenance
    structured_data: dict = Field(default_factory=dict)
    raw_content: str | None = None
    embeddings: list[float] | None = None
    entity_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    chunk_ref: str | None = None
    hash: str  # SHA256 of canonical JSON(tenant_id + structured_data)


# ── Entity 2: Source ────────────────────────────────────────────────────


class Source(OntologyBaseModel):
    """A data source (connector, upload channel, API, etc.)."""

    id: str
    tenant_id: str
    name: str
    source_type: str
    reliability: float = Field(ge=0.0, le=1.0)
    status: Literal["active", "degraded", "disconnected"] = "active"
    config: dict = Field(default_factory=dict)


# ── Entity 3: Stakeholder ───────────────────────────────────────────────


class Stakeholder(OntologyBaseModel):
    """A human participant identified in evidence."""

    id: str
    tenant_id: str
    name: str
    email: str
    role: str
    status: Literal["identified", "engaged", "at_risk", "blocked"] = "identified"


# ── Entity 4: OrgUnit ──────────────────────────────────────────────────


class OrgUnit(OntologyBaseModel):
    """Organisational unit (team, department, division)."""

    id: str
    tenant_id: str
    name: str
    parent_id: str | None = None
    status: Literal["active", "restructuring", "dissolved"] = "active"


# ── Entity 5: Capability ────────────────────────────────────────────────


class Capability(OntologyBaseModel):
    """Business or technical capability assessed during discovery."""

    id: str
    tenant_id: str
    name: str
    description: str = ""
    maturity: float = Field(ge=0.0, le=1.0, default=0.0)
    status: Literal["assessed", "developing", "mature", "deprecated"] = "assessed"


# ── Entity 6: Process ───────────────────────────────────────────────────


class BusinessPillar(str, Enum):
    """The four MVP business pillars (frozen V6 direction).

    Exactly four pillars: Marketing, Sales, Operations, Finance.
    """

    MARKETING = "marketing"
    SALES = "sales"
    OPERATIONS = "operations"
    FINANCE = "finance"


class ProcessStep(OntologyBaseModel):
    """A single step within a business process."""

    id: str
    tenant_id: str
    process_id: str
    name: str
    description: str = ""
    order_index: int = 0
    owner_id: str | None = None
    status: Literal["draft", "active", "deprecated"] = "draft"


class Process(OntologyBaseModel):
    """Business process mapped during discovery.

    Extended for V6 with the operating-model fields: owner (Stakeholder ref),
    objective, scope, decision rules, definition of done, KPIs, dependencies,
    allowed actions, review cadence, pillar, process type, and steps.
    """

    id: str
    tenant_id: str
    name: str
    description: str = ""
    status: Literal["mapped", "analyzed", "improved", "retired"] = "mapped"
    owner_id: str | None = None
    relationship_to_owner: Literal["owns", "sponsors", "operates", "supports"] | None = None
    objective: str = ""
    scope: str = ""
    decision_rules: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)
    kpi_ids: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    review_cadence: str | None = None
    pillar: BusinessPillar | None = None
    process_type: str = "core"
    steps: list[ProcessStep] = Field(default_factory=list)


# ── Entity 7: System ────────────────────────────────────────────────────


class System(OntologyBaseModel):
    """Software system or platform."""

    id: str
    tenant_id: str
    name: str
    type: str
    status: Literal["live", "sunset", "migrating"] = "live"


# ── Entity 8: Requirement ───────────────────────────────────────────────


class Requirement(OntologyBaseModel):
    """Functional or non-functional requirement."""

    id: str
    tenant_id: str
    name: str
    description: str = ""
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    status: Literal["proposed", "accepted", "in_progress", "verified", "rejected"] = (
        "proposed"
    )


# ── Entity 9: BusinessRule ─────────────────────────────────────────────


class BusinessRule(OntologyBaseModel):
    """A deterministic business rule that governs decisions or artifacts."""

    id: str
    tenant_id: str
    name: str
    rule_expression: str
    severity: Literal["block", "warn", "info"] = "warn"
    status: Literal["active", "superseded", "deprecated"] = "active"


# ── Entity 10: Assumption ──────────────────────────────────────────────


class Assumption(OntologyBaseModel):
    """An assumption recorded during discovery or decision-making."""

    id: str
    tenant_id: str
    statement: str
    status: Literal["unvalidated", "validated", "invalidated"] = "unvalidated"
    validated_by: str | None = None  # Evidence ULID


# ── Entity 11: Constraint ──────────────────────────────────────────────


class Constraint(OntologyBaseModel):
    """A constraint that limits available options or decisions."""

    id: str
    tenant_id: str
    description: str
    type: str
    status: Literal["active", "waived", "removed"] = "active"


# ── Entity 12: Risk ─────────────────────────────────────────────────────


class Risk(OntologyBaseModel):
    """A risk identified during analysis with severity and probability."""

    id: str
    tenant_id: str
    description: str
    severity: float = Field(ge=0.0, le=100.0)
    probability: float = Field(ge=0.0, le=1.0)
    status: Literal["identified", "analyzed", "mitigated", "accepted", "realized"] = (
        "identified"
    )
    mitigation: str | None = None
    owner_id: str | None = None  # Stakeholder ULID


# ── Entity 13: Decision ─────────────────────────────────────────────────


class Decision(OntologyBaseModel):
    """A decision with lifecycle tracking from draft to superseded."""

    id: str
    tenant_id: str
    title: str
    description: str = ""
    workspace_id: str
    owner_id: str
    status: Literal["draft", "assessing", "approved", "superseded"] = "draft"
    created_at: datetime
    approved_at: datetime | None = None


# ── Entity 14: Option ───────────────────────────────────────────────────


class Option(OntologyBaseModel):
    """A candidate option evaluated under a decision."""

    id: str
    tenant_id: str
    decision_id: str
    title: str
    description: str = ""
    feasibility_score: float | None = Field(default=None, ge=0.0, le=100.0)
    status: Literal["proposed", "scored", "selected", "discarded"] = "proposed"


# ── Entity 15: TradeOff ─────────────────────────────────────────────────


class TradeOff(OntologyBaseModel):
    """A pairwise comparison between two options along one dimension."""

    id: str
    option_a_id: str
    option_b_id: str
    dimension: str
    a_score: float
    b_score: float
    delta: float
    narrative: str | None = None


# ── Entity 16: KPI ──────────────────────────────────────────────────────


class KPI(OntologyBaseModel):
    """Key performance indicator with target and baseline tracking."""

    id: str
    tenant_id: str
    name: str
    target_value: float
    baseline_value: float
    unit: str
    owner_id: str
    status: Literal["baseline_set", "tracking", "met", "missed"] = "baseline_set"


# ── Entity 17: Project ──────────────────────────────────────────────────


class Project(OntologyBaseModel):
    """A project or initiative within a workspace."""

    id: str
    tenant_id: str
    name: str
    status: Literal["initiated", "planning", "executing", "monitoring", "closed"] = (
        "initiated"
    )


# ── Entity 18: Artifact ─────────────────────────────────────────────────


class Artifact(OntologyBaseModel):
    """A published or draft artifact (report, brief, register, etc.)."""

    id: str
    tenant_id: str
    workspace_id: str
    name: str
    artifact_type: str
    status: Literal["draft", "valid", "published", "superseded"] = "draft"
    dsl_config_id: str


# ── Entity 19: ArtifactVersion ──────────────────────────────────────────


class ArtifactVersion(OntologyBaseModel):
    """A specific version of an artifact."""

    id: str
    artifact_id: str
    version_number: int
    content: dict = Field(default_factory=dict)
    status: Literal["current", "archived"] = "current"
    published_at: datetime


# ── Entity 20: Conflict ─────────────────────────────────────────────────


class Conflict(OntologyBaseModel):
    """A detected conflict between evidence records or entities."""

    id: str
    tenant_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    conflict_type: str
    description: str = ""
    status: Literal["open", "resolving", "resolved", "dismissed"] = "open"


# ── Entity 21: ValidationResult ─────────────────────────────────────────


class ValidationResult(OntologyBaseModel):
    """The result of validating an artifact against a rule."""

    id: str
    artifact_id: str
    rule_id: str
    status: Literal["pending", "passed", "failed", "blocked"] = "pending"
    details: str | None = None


# ── Entity 22: FeasibilityScore ─────────────────────────────────────────


class FeasibilityScore(OntologyBaseModel):
    """Multi-dimensional feasibility score for an option."""

    id: str
    option_id: str
    dimensions: dict[str, float] = Field(default_factory=dict)
    weighted_total: float
    readiness_tier: Literal["publish", "caveat", "review", "block"]
    computed_at: datetime


# ── Entity 23: AuditEvent ───────────────────────────────────────────────


class AuditEvent(OntologyBaseModel):
    """An immutable audit log entry."""

    id: str
    tenant_id: str
    entity_type: str
    entity_id: str
    action: str
    actor_id: str
    timestamp: datetime
    details: dict = Field(default_factory=dict)


# ── Entity 24: Workspace ────────────────────────────────────────────────


class Workspace(OntologyBaseModel):
    """A workspace scoping entities, decisions, and artifacts."""

    id: str
    tenant_id: str
    name: str
    purpose: str = ""
    status: Literal["active", "archived", "closed"] = "active"


# ── V6 Domain entities ────────────────────────────────────────────────────


class SOP(OntologyBaseModel):
    """Standard Operating Procedure for a business process."""

    id: str
    tenant_id: str
    name: str
    process_id: str | None = None
    objective: str = ""
    scope: str = ""
    owner_id: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    decision_rules: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)
    faq: list[str] = Field(default_factory=list)
    linked_systems: list[str] = Field(default_factory=list)
    revision_history: list[str] = Field(default_factory=list)
    last_reviewed_at: datetime | None = None
    status: Literal["draft", "active", "archived"] = "draft"
    current_version_id: str | None = None


class SOPVersion(OntologyBaseModel):
    """A versioned snapshot of an SOP."""

    id: str
    tenant_id: str
    sop_id: str
    version: str
    content_hash: str
    changes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    author: str
    supersedes_id: str | None = None


class Mission(OntologyBaseModel):
    """A persistent business objective assigned to an AI employee."""

    id: str
    tenant_id: str
    title: str
    description: str = ""
    owner_id: str | None = None
    employee_role: str | None = None
    status: Literal[
        "pending", "active", "stalled", "completed", "failed", "archived"
    ] = "pending"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    kpi_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    knowledge_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    process_ids: list[str] = Field(default_factory=list)
    # DEPRECATED: prefer the Situation link (``situation_id``) for new code.
    # ``onboarding_id`` stays so existing M1-M6 aggregates keep resolving.
    onboarding_id: str | None = None  # ADR-010: M1-M6 missions belong to an Onboarding aggregate
    situation_id: str | None = None
    # Generic mission target (Phase 1 dual-write): explicit ``target_*`` wins;
    # ``onboarding_id``-only derives ("onboarding", onboarding_id). New code
    # passes explicit targets; ``onboarding_id`` is a deprecated alias.
    target_type: str | None = None
    target_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

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


class MissionEvent(OntologyBaseModel):
    """An immutable, append-only event on a mission timeline."""

    id: str
    mission_id: str
    version: int = 1
    event_type: Literal[
        "created", "started", "reviewed", "paused", "resumed", "replanned",
        "redirected", "approved", "rejected", "executed", "confidence_changed",
        "status_changed", "priority_changed", "evidence_added",
        "recommendation_updated", "completed", "archived",
    ]
    actor: str | None = None
    source: str | None = None
    payload: dict = Field(default_factory=dict)
    causation_id: str | None = None
    correlation_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MissionSnapshot(OntologyBaseModel):
    """A point-in-time capture of a mission's composed state."""

    id: str
    mission_id: str
    version: int = 1
    snapshot_type: Literal["periodic", "on_change", "manual"] = "periodic"
    body: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Action(OntologyBaseModel):
    """A governed, idempotent unit of work executed by an AI employee."""

    id: str
    tenant_id: str
    mission_id: str
    employee_role: str
    capability: str
    input_snapshot: dict = Field(default_factory=dict)
    risk_tier: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    policy_tier: str | None = None
    status: Literal[
        "draft", "pending_approval", "approved", "rejected",
        "executing", "completed", "failed",
    ] = "draft"
    idempotency_key: str
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ActionResult(OntologyBaseModel):
    """The result of executing an Action, with verification metadata."""

    id: str
    action_id: str
    result_summary: str = ""
    output_snapshot: dict = Field(default_factory=dict)
    error: str | None = None
    rollback_metadata: dict = Field(default_factory=dict)
    verified: bool = False
    verified_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EmployeeDefinition(OntologyBaseModel):
    """Static configuration of an AI employee role (config, not runtime)."""

    id: str
    tenant_id: str
    role: str
    goals: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
    authority: dict = Field(default_factory=dict)
    risk_threshold: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    kpis: list[str] = Field(default_factory=list)
    memory_namespace: str = ""
    mission_types: list[str] = Field(default_factory=list)


class EmployeeRun(OntologyBaseModel):
    """Runtime state of an AI employee (state, not config)."""

    id: str
    tenant_id: str
    employee_definition_id: str
    role: str
    status: Literal["idle", "active", "paused", "offline"] = "idle"
    current_mission_id: str | None = None
    active_mission_ids: list[str] = Field(default_factory=list)
    memory_state: dict = Field(default_factory=dict)
    last_active_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Outcome(OntologyBaseModel):
    """The result of a mission, tied to evidence."""

    id: str
    tenant_id: str
    mission_id: str
    result: Literal["success", "partial", "failure", "na"] = "na"
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Review(OntologyBaseModel):
    """A scheduled review of a process, SOP, or other target."""

    id: str
    tenant_id: str
    target_type: str
    target_id: str
    reviewer: str
    cadence: str | None = None
    last_reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
