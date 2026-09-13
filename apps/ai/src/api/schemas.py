"""Pydantic request/response models for V7 REST API.

All models use ``extra="forbid"`` and ``strict=True`` to reject
unknown fields and prevent type coercion. This is a hard constraint
from the OntologyAI architecture.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Shared types
# =============================================================================


class ErrorDetail(BaseModel):
    """Standard error response body."""

    model_config = ConfigDict(extra="forbid", strict=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, str] = Field(default_factory=dict)


class PaginationMeta(BaseModel):
    """Pagination envelope metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)

    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    has_next: bool


# =============================================================================
# Event ingestion — POST /api/v1/events
# =============================================================================


class IncidentEventPayload(BaseModel):
    """Incoming incident event for ingestion.

    Attributes:
        tenant_id: Multi-tenant identifier.
        event_type: Normalized event type.
        source: Origin system (e.g. "pagerduty", "slack", "jira").
        source_id: Unique ID from the source system.
        title: Short incident title.
        description: Full description of the incident.
        severity: Incident severity.
        occurred_at: When the event occurred (ISO 8601).
        reporter: Who reported it.
        tags: Freeform tags.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    tenant_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    occurred_at: datetime
    reporter: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class EvidenceResponse(BaseModel):
    """Evidence object returned after ingestion."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    tenant_id: str
    source: str
    provenance: str
    captured_at: str
    raw_text: str
    normalized_text: str


class SituationResponse(BaseModel):
    """Situation object returned after ingestion."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    tenant_id: str
    type: str
    affected_entities: list[str]
    detected_condition: str
    severity: str
    owner_id: str | None
    evidence_ids: list[str]
    checkpoint_id: str
    business_impact: str
    status: str


class EventIngestionResponse(BaseModel):
    """Response for POST /api/v1/events."""

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence: EvidenceResponse
    situation: SituationResponse
    trace_id: str


# =============================================================================
# Situation CRUD — GET /api/v1/situations
# =============================================================================


class SituationListQuery(BaseModel):
    """Query parameters for listing situations."""

    model_config = ConfigDict(extra="forbid", strict=True)

    tenant_id: str = Field(min_length=1)
    type: str | None = None
    status: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class SituationListResponse(BaseModel):
    """Response for GET /api/v1/situations."""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[SituationResponse]
    pagination: PaginationMeta


class SituationDetailResponse(BaseModel):
    """Response for GET /api/v1/situations/{id}."""

    model_config = ConfigDict(extra="forbid", strict=True)

    situation: SituationResponse
    evidence: list[EvidenceResponse]


# =============================================================================
# Mission management — GET /api/v1/missions
# =============================================================================


class MissionResponse(BaseModel):
    """Mission object."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    title: str
    status: str
    priority: str
    owner_id: str | None
    employee_role: str | None
    situation_id: str | None
    target_type: str | None
    target_id: str | None


class MissionAuditEntry(BaseModel):
    """Single audit trail entry on a mission."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    mission_id: str
    event_type: str
    version: int
    timestamp: datetime | None = None
    actor: str | None = None
    details: dict[str, str] = Field(default_factory=dict)


class MissionListResponse(BaseModel):
    """Response for GET /api/v1/missions."""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[MissionResponse]
    pagination: PaginationMeta


class MissionDetailResponse(BaseModel):
    """Response for GET /api/v1/missions/{id}."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mission: MissionResponse
    audit_trail: list[MissionAuditEntry]


# =============================================================================
# Incident tracking — GET /api/v1/incidents
# =============================================================================


class IncidentResponse(BaseModel):
    """Incident (Issue) object."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: str
    severity: str
    status: str
    summary: str
    opened_at: str | None
    resolved_at: str | None
    owner: str | None
    affected_entities: list[str]
    escalation: bool


class TimelineEntry(BaseModel):
    """Single entry in an incident timeline."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    incident_id: str
    event_type: str
    timestamp: datetime
    actor: str | None = None
    description: str


class IncidentListResponse(BaseModel):
    """Response for GET /api/v1/incidents."""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[IncidentResponse]
    pagination: PaginationMeta


class IncidentDetailResponse(BaseModel):
    """Response for GET /api/v1/incidents/{id}."""

    model_config = ConfigDict(extra="forbid", strict=True)

    incident: IncidentResponse
    timeline: list[TimelineEntry]


# =============================================================================
# Vendor management — GET /api/v1/vendors
# =============================================================================


class VendorContact(BaseModel):
    """Contact point for a vendor."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    role: str
    email: str | None = None
    phone: str | None = None


class VendorResponse(BaseModel):
    """Vendor (Party) object."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: str
    name: str
    status: str
    owner: str | None
    contact_points: list[str]
    notes: str | None


class VendorDetailResponse(BaseModel):
    """Response for GET /api/v1/vendors/{id}."""

    model_config = ConfigDict(extra="forbid", strict=True)

    vendor: VendorResponse
    contacts: list[VendorContact]
    active_incidents: list[IncidentResponse]


class VendorListResponse(BaseModel):
    """Response for GET /api/v1/vendors."""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[VendorResponse]
    pagination: PaginationMeta


# =============================================================================
# Approval queue — GET /api/v1/approvals, POST approve/reject
# =============================================================================


class ApprovalResponse(BaseModel):
    """Pending approval item."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    action_id: str
    tenant_id: str
    mission_id: str
    action_type: str
    target: str
    risk_tier: str
    status: Literal["pending", "approved", "rejected"]
    requested_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None


class ApprovalListResponse(BaseModel):
    """Response for GET /api/v1/approvals."""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[ApprovalResponse]
    pagination: PaginationMeta


class ApprovalActionRequest(BaseModel):
    """Request body for approve/reject actions."""

    model_config = ConfigDict(extra="forbid", strict=True)

    resolved_by: str = Field(min_length=1)
    reason: str = Field(default="", max_length=500)


class ApprovalActionResponse(BaseModel):
    """Response for POST /api/v1/approvals/{id}/approve or /reject."""

    model_config = ConfigDict(extra="forbid", strict=True)

    approval: ApprovalResponse
    message: str


# =============================================================================
# Route not found
# =============================================================================


class NotFoundResponse(BaseModel):
    """Response for unknown routes / missing resources."""

    model_config = ConfigDict(extra="forbid", strict=True)

    error: ErrorDetail
