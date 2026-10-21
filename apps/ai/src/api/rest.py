"""V7 REST API handlers — pure async logic, no server startup.

Each handler is an ``async def`` that accepts typed Pydantic request
models and returns typed Pydantic response models.  Business logic
delegates to the existing control plane / mission / ontology modules.

These handlers are framework-agnostic: mount them on FastAPI, Starlette,
or any ASGI router.  The ``_store`` module-level dict acts as an
in-process placeholder; production replaces it with Postgres/Redis.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.api.schemas import (
    ApprovalActionRequest,
    ApprovalActionResponse,
    ApprovalListResponse,
    ApprovalResponse,
    EvidenceResponse,
    ErrorDetail,
    EventIngestionResponse,
    IncidentDetailResponse,
    IncidentEventPayload,
    IncidentListResponse,
    IncidentResponse,
    MissionAuditEntry,
    MissionDetailResponse,
    MissionListResponse,
    MissionResponse,
    NotFoundResponse,
    PaginationMeta,
    SituationDetailResponse,
    SituationListResponse,
    SituationResponse,
    TimelineEntry,
    VendorContact,
    VendorDetailResponse,
    VendorListResponse,
    VendorResponse,
)
from src.ontology.object_types import Evidence, Situation


# ---------------------------------------------------------------------------
# In-memory store — placeholder for production DB layer
# ---------------------------------------------------------------------------

_store: dict[str, list[dict[str, Any]]] = {
    "situations": [],
    "evidence": [],
    "missions": [],
    "incidents": [],
    "vendors": [],
    "approvals": [],
    "timelines": [],
    "audit_trails": [],
}


def _reset_store() -> None:
    """Clear all in-memory data (for tests)."""
    for key in _store:
        _store[key] = []


def _uuid() -> str:
    """Generate a deterministic prefixed UUID for tests."""
    return f"{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    """Current UTC time as ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def _now() -> datetime:
    """Current UTC datetime."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# POST /api/v1/events — ingest incident event → Evidence + Situation
# ---------------------------------------------------------------------------


async def ingest_event(payload: IncidentEventPayload) -> EventIngestionResponse:
    """Accept an incident event, create Evidence + Situation.

    Business logic:
    1. Create an Evidence record from the raw event.
    2. Open a Situation linked to that evidence.
    3. Return both objects.
    """
    evidence_id = f"ev-{_uuid()}"
    situation_id = f"sit-{_uuid()}"
    checkpoint_id = f"cp-{_uuid()}"
    trace_id = f"trace-{_uuid()}"

    evidence = Evidence(
        id=evidence_id,
        tenant_id=payload.tenant_id,
        source=payload.source,
        provenance=f"{payload.source}:{payload.reporter}",
        captured_at=payload.occurred_at.isoformat(),
        raw_text=payload.description,
        normalized_text=f"[{payload.source} report]: {payload.title}",
    )

    situation = Situation(
        id=situation_id,
        tenant_id=payload.tenant_id,
        type="VENDOR_INCIDENT"
        if "vendor" in payload.event_type.lower()
        else "DELIVERY_BLOCKER",
        affected_entities=[],
        detected_condition=payload.title,
        severity=payload.severity,
        owner_id=None,
        evidence_ids=[evidence_id],
        checkpoint_id=checkpoint_id,
        business_impact=payload.description,
    )

    _store["evidence"].append(evidence.model_dump())
    _store["situations"].append(situation.model_dump())

    return EventIngestionResponse(
        evidence=EvidenceResponse(
            id=evidence.id,
            tenant_id=evidence.tenant_id,
            source=evidence.source,
            provenance=evidence.provenance,
            captured_at=evidence.captured_at,
            raw_text=evidence.raw_text,
            normalized_text=evidence.normalized_text,
        ),
        situation=SituationResponse(
            id=situation.id,
            tenant_id=situation.tenant_id,
            type=situation.type,
            affected_entities=situation.affected_entities,
            detected_condition=situation.detected_condition,
            severity=situation.severity,
            owner_id=situation.owner_id,
            evidence_ids=situation.evidence_ids,
            checkpoint_id=situation.checkpoint_id,
            business_impact=situation.business_impact,
            status=situation.status,
        ),
        trace_id=trace_id,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/situations — list situations (filtered)
# ---------------------------------------------------------------------------


async def list_situations(
    tenant_id: str,
    type: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> SituationListResponse:
    """Return situations filtered by tenant, optional type/status."""
    items = [
        s
        for s in _store["situations"]
        if s["tenant_id"] == tenant_id
        and (type is None or s["type"] == type)
        and (status is None or s["status"] == status)
    ]
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return SituationListResponse(
        items=[SituationResponse(**s) for s in page_items],
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            has_next=start + page_size < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/v1/situations/{id} — get one situation with evidence
# ---------------------------------------------------------------------------


async def get_situation(
    situation_id: str,
) -> SituationDetailResponse | NotFoundResponse:
    """Return a single situation with its linked evidence."""
    for s in _store["situations"]:
        if s["id"] == situation_id:
            ev_ids = s.get("evidence_ids", [])
            evidence_items = [
                EvidenceResponse(**e) for e in _store["evidence"] if e["id"] in ev_ids
            ]
            return SituationDetailResponse(
                situation=SituationResponse(**s),
                evidence=evidence_items,
            )
    return NotFoundResponse(
        error=ErrorDetail(
            code="NOT_FOUND", message=f"Situation {situation_id} not found"
        )
    )


# ---------------------------------------------------------------------------
# GET /api/v1/missions — list missions
# ---------------------------------------------------------------------------


async def list_missions(
    tenant_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> MissionListResponse:
    """Return missions, optionally filtered."""
    items = _store["missions"]
    if tenant_id is not None:
        # Missions don't have tenant_id directly; filter via situation
        sit_ids = {s["id"] for s in _store["situations"] if s["tenant_id"] == tenant_id}
        items = [m for m in items if m.get("situation_id") in sit_ids]
    if status is not None:
        items = [m for m in items if m["status"] == status]

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return MissionListResponse(
        items=[MissionResponse(**m) for m in page_items],
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            has_next=start + page_size < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/v1/missions/{id} — get one mission with audit trail
# ---------------------------------------------------------------------------


async def get_mission(mission_id: str) -> MissionDetailResponse | NotFoundResponse:
    """Return a single mission with its audit trail."""
    for m in _store["missions"]:
        if m["id"] == mission_id:
            audit = [
                MissionAuditEntry(**a)
                for a in _store["audit_trails"]
                if a.get("mission_id") == mission_id
            ]
            return MissionDetailResponse(
                mission=MissionResponse(**m),
                audit_trail=audit,
            )
    return NotFoundResponse(
        error=ErrorDetail(code="NOT_FOUND", message=f"Mission {mission_id} not found")
    )


# ---------------------------------------------------------------------------
# GET /api/v1/incidents — list incidents
# ---------------------------------------------------------------------------


async def list_incidents(
    tenant_id: str | None = None,
    severity: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> IncidentListResponse:
    """Return incidents, optionally filtered."""
    items = _store["incidents"]
    if severity is not None:
        items = [i for i in items if i["severity"] == severity]

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return IncidentListResponse(
        items=[IncidentResponse(**i) for i in page_items],
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            has_next=start + page_size < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/v1/incidents/{id} — get incident with timeline
# ---------------------------------------------------------------------------


async def get_incident(incident_id: str) -> IncidentDetailResponse | NotFoundResponse:
    """Return a single incident with its timeline."""
    for inc in _store["incidents"]:
        if inc["id"] == incident_id:
            timeline = [
                TimelineEntry(**t)
                for t in _store["timelines"]
                if t.get("incident_id") == incident_id
            ]
            return IncidentDetailResponse(
                incident=IncidentResponse(**inc),
                timeline=timeline,
            )
    return NotFoundResponse(
        error=ErrorDetail(code="NOT_FOUND", message=f"Incident {incident_id} not found")
    )


# ---------------------------------------------------------------------------
# GET /api/v1/vendors — list vendors
# ---------------------------------------------------------------------------


async def list_vendors(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> VendorListResponse:
    """Return vendors, optionally filtered by status."""
    items = _store["vendors"]
    if status is not None:
        items = [v for v in items if v["status"] == status]

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return VendorListResponse(
        items=[VendorResponse(**v) for v in page_items],
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            has_next=start + page_size < total,
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/v1/vendors/{id} — get vendor with contacts + active incidents
# ---------------------------------------------------------------------------


async def get_vendor(vendor_id: str) -> VendorDetailResponse | NotFoundResponse:
    """Return a single vendor with contacts and active incidents."""
    for v in _store["vendors"]:
        if v["id"] == vendor_id:
            contacts = [
                VendorContact(**c)
                for c in _store.get("vendor_contacts", [])
                if c.get("vendor_id") == vendor_id
            ]
            active_incidents = [
                IncidentResponse(**i)
                for i in _store["incidents"]
                if vendor_id in i.get("affected_entities", [])
                and i["status"] in ("open", "investigating")
            ]
            return VendorDetailResponse(
                vendor=VendorResponse(**v),
                contacts=contacts,
                active_incidents=active_incidents,
            )
    return NotFoundResponse(
        error=ErrorDetail(code="NOT_FOUND", message=f"Vendor {vendor_id} not found")
    )


# ---------------------------------------------------------------------------
# GET /api/v1/approvals — list pending approvals
# ---------------------------------------------------------------------------


async def list_approvals(
    tenant_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ApprovalListResponse:
    """Return approvals, optionally filtered."""
    items = _store["approvals"]
    if tenant_id is not None:
        items = [a for a in items if a["tenant_id"] == tenant_id]
    if status is not None:
        items = [a for a in items if a["status"] == status]

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return ApprovalListResponse(
        items=[ApprovalResponse(**a) for a in page_items],
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            has_next=start + page_size < total,
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/approvals/{id}/approve
# ---------------------------------------------------------------------------


async def approve_action(
    approval_id: str,
    request: ApprovalActionRequest,
) -> ApprovalActionResponse | NotFoundResponse:
    """Mark a pending approval as approved."""
    for a in _store["approvals"]:
        if a["id"] == approval_id:
            if a["status"] != "pending":
                return NotFoundResponse(
                    error=ErrorDetail(
                        code="ALREADY_RESOLVED",
                        message=f"Approval {approval_id} is already {a['status']}",
                    )
                )
            a["status"] = "approved"
            a["resolved_at"] = _now()
            a["resolved_by"] = request.resolved_by
            return ApprovalActionResponse(
                approval=ApprovalResponse(**a),
                message=f"Approval {approval_id} approved by {request.resolved_by}",
            )
    return NotFoundResponse(
        error=ErrorDetail(code="NOT_FOUND", message=f"Approval {approval_id} not found")
    )


# ---------------------------------------------------------------------------
# POST /api/v1/approvals/{id}/reject
# ---------------------------------------------------------------------------


async def reject_action(
    approval_id: str,
    request: ApprovalActionRequest,
) -> ApprovalActionResponse | NotFoundResponse:
    """Mark a pending approval as rejected."""
    for a in _store["approvals"]:
        if a["id"] == approval_id:
            if a["status"] != "pending":
                return NotFoundResponse(
                    error=ErrorDetail(
                        code="ALREADY_RESOLVED",
                        message=f"Approval {approval_id} is already {a['status']}",
                    )
                )
            a["status"] = "rejected"
            a["resolved_at"] = _now()
            a["resolved_by"] = request.resolved_by
            return ApprovalActionResponse(
                approval=ApprovalResponse(**a),
                message=f"Approval {approval_id} rejected by {request.resolved_by}",
            )
    return NotFoundResponse(
        error=ErrorDetail(code="NOT_FOUND", message=f"Approval {approval_id} not found")
    )


# ---------------------------------------------------------------------------
# Route table — maps path → handler for framework mounting
# ---------------------------------------------------------------------------

ROUTE_TABLE: dict[str, Any] = {
    "POST /api/v1/events": ingest_event,
    "GET /api/v1/situations": list_situations,
    "GET /api/v1/situations/{id}": get_situation,
    "GET /api/v1/missions": list_missions,
    "GET /api/v1/missions/{id}": get_mission,
    "GET /api/v1/incidents": list_incidents,
    "GET /api/v1/incidents/{id}": get_incident,
    "GET /api/v1/vendors": list_vendors,
    "GET /api/v1/vendors/{id}": get_vendor,
    "GET /api/v1/approvals": list_approvals,
    "POST /api/v1/approvals/{id}/approve": approve_action,
    "POST /api/v1/approvals/{id}/reject": reject_action,
}
