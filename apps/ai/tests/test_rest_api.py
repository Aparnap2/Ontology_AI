"""Tests for V7 REST API handlers — vendor operations desk.

Covers:
- POST /events creates Evidence + Situation
- GET /situations returns filtered list
- POST /approvals/{id}/approve marks approval as approved
- POST /approvals/{id}/reject marks approval as rejected
- Unknown routes return appropriate errors
- All models are strict (extra=forbid)
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from src.api.rest import (
    _reset_store,
    _store,
    approve_action,
    get_incident,
    get_mission,
    get_situation,
    get_vendor,
    ingest_event,
    list_incidents,
    list_missions,
    list_situations,
    list_vendors,
    reject_action,
)
from src.api.schemas import (
    ApprovalActionRequest,
    ErrorDetail,
    EventIngestionResponse,
    IncidentEventPayload,
    NotFoundResponse,
    PaginationMeta,
    SituationResponse,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    """Reset the in-memory store before every test."""
    _reset_store()
    yield
    _reset_store()


def _make_event(**overrides: object) -> IncidentEventPayload:
    """Build a valid IncidentEventPayload with sensible defaults."""
    defaults: dict[str, object] = {
        "tenant_id": "t-1",
        "event_type": "vendor_outage",
        "source": "pagerduty",
        "source_id": "pd-123",
        "title": "AWS us-east-1 outage",
        "description": "Complete regional outage affecting all services",
        "severity": "critical",
        "occurred_at": datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc),
        "reporter": "ops-bot",
    }
    defaults.update(overrides)
    return IncidentEventPayload(**defaults)  # type: ignore[arg-type]


def _seed_approval(
    approval_id: str = "ap-1",
    status: str = "pending",
    tenant_id: str = "t-1",
) -> None:
    """Insert a fake approval into the in-memory store."""
    _store["approvals"].append(
        {
            "id": approval_id,
            "action_id": "act-1",
            "tenant_id": tenant_id,
            "mission_id": "m-1",
            "action_type": "vendor.scale",
            "target": "vendor:v-1",
            "risk_tier": "HIGH",
            "status": status,
            "requested_at": datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc),
            "resolved_at": None,
            "resolved_by": None,
        }
    )


# ---------------------------------------------------------------------------
# POST /events — Evidence + Situation creation
# ---------------------------------------------------------------------------


class TestIngestEvent:
    @pytest.mark.asyncio
    async def test_creates_evidence_and_situation(self) -> None:
        payload = _make_event()
        resp = await ingest_event(payload)

        assert isinstance(resp, EventIngestionResponse)
        assert resp.evidence.tenant_id == "t-1"
        assert resp.evidence.source == "pagerduty"
        assert "ops-bot" in resp.evidence.provenance
        assert resp.situation.tenant_id == "t-1"
        assert resp.situation.severity == "critical"
        assert resp.situation.evidence_ids == [resp.evidence.id]
        assert resp.trace_id.startswith("trace-")

    @pytest.mark.asyncio
    async def test_vendor_event_uses_vendor_incident_type(self) -> None:
        payload = _make_event(event_type="vendor_outage")
        resp = await ingest_event(payload)
        assert resp.situation.type == "VENDOR_INCIDENT"

    @pytest.mark.asyncio
    async def test_non_vendor_event_uses_delivery_blocker(self) -> None:
        payload = _make_event(event_type="service_down")
        resp = await ingest_event(payload)
        assert resp.situation.type == "DELIVERY_BLOCKER"

    @pytest.mark.asyncio
    async def test_store_persists_both_objects(self) -> None:
        payload = _make_event()
        resp = await ingest_event(payload)

        assert len(_store["evidence"]) == 1
        assert len(_store["situations"]) == 1
        assert _store["evidence"][0]["id"] == resp.evidence.id
        assert _store["situations"][0]["id"] == resp.situation.id


# ---------------------------------------------------------------------------
# GET /situations — filtered list
# ---------------------------------------------------------------------------


class TestListSituations:
    @pytest.mark.asyncio
    async def test_empty_store_returns_empty_list(self) -> None:
        resp = await list_situations(tenant_id="t-1")
        assert resp.items == []
        assert resp.pagination.total == 0
        assert resp.pagination.has_next is False

    @pytest.mark.asyncio
    async def test_filters_by_tenant(self) -> None:
        payload_a = _make_event(tenant_id="t-1")
        payload_b = _make_event(tenant_id="t-2")
        await ingest_event(payload_a)
        await ingest_event(payload_b)

        resp = await list_situations(tenant_id="t-1")
        assert resp.pagination.total == 1
        assert resp.items[0].tenant_id == "t-1"

    @pytest.mark.asyncio
    async def test_filters_by_type(self) -> None:
        await ingest_event(_make_event(event_type="vendor_outage"))
        await ingest_event(_make_event(event_type="service_down"))

        resp = await list_situations(tenant_id="t-1", type="VENDOR_INCIDENT")
        assert resp.pagination.total == 1
        assert resp.items[0].type == "VENDOR_INCIDENT"

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        for _ in range(5):
            await ingest_event(_make_event())

        resp = await list_situations(tenant_id="t-1", page=1, page_size=2)
        assert len(resp.items) == 2
        assert resp.pagination.total == 5
        assert resp.pagination.has_next is True

        resp2 = await list_situations(tenant_id="t-1", page=3, page_size=2)
        assert len(resp2.items) == 1
        assert resp2.pagination.has_next is False


# ---------------------------------------------------------------------------
# GET /situations/{id} — detail with evidence
# ---------------------------------------------------------------------------


class TestGetSituation:
    @pytest.mark.asyncio
    async def test_returns_situation_with_evidence(self) -> None:
        resp = await ingest_event(_make_event())
        detail = await get_situation(resp.situation.id)

        assert isinstance(detail, EventIngestionResponse) or hasattr(
            detail, "situation"
        )
        # The actual return type is SituationDetailResponse
        from src.api.schemas import SituationDetailResponse

        assert isinstance(detail, SituationDetailResponse)
        assert len(detail.evidence) == 1
        assert detail.evidence[0].id == resp.evidence.id

    @pytest.mark.asyncio
    async def test_unknown_id_returns_not_found(self) -> None:
        resp = await get_situation("nonexistent")
        assert isinstance(resp, NotFoundResponse)
        assert resp.error.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /missions, GET /missions/{id}
# ---------------------------------------------------------------------------


class TestMissions:
    @pytest.mark.asyncio
    async def test_list_missions_empty(self) -> None:
        resp = await list_missions()
        assert resp.items == []
        assert resp.pagination.total == 0

    @pytest.mark.asyncio
    async def test_get_mission_not_found(self) -> None:
        resp = await get_mission("m-999")
        assert isinstance(resp, NotFoundResponse)
        assert resp.error.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /incidents, GET /incidents/{id}
# ---------------------------------------------------------------------------


class TestIncidents:
    @pytest.mark.asyncio
    async def test_list_incidents_empty(self) -> None:
        resp = await list_incidents()
        assert resp.items == []
        assert resp.pagination.total == 0

    @pytest.mark.asyncio
    async def test_get_incident_not_found(self) -> None:
        resp = await get_incident("inc-999")
        assert isinstance(resp, NotFoundResponse)
        assert resp.error.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /vendors, GET /vendors/{id}
# ---------------------------------------------------------------------------


class TestVendors:
    @pytest.mark.asyncio
    async def test_list_vendors_empty(self) -> None:
        resp = await list_vendors()
        assert resp.items == []

    @pytest.mark.asyncio
    async def test_get_vendor_not_found(self) -> None:
        resp = await get_vendor("v-999")
        assert isinstance(resp, NotFoundResponse)
        assert resp.error.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# POST /approvals/{id}/approve
# ---------------------------------------------------------------------------


class TestApproveAction:
    @pytest.mark.asyncio
    async def test_approve_pending_approval(self) -> None:
        _seed_approval("ap-1")
        req = ApprovalActionRequest(resolved_by="admin-1", reason="LGTM")
        resp = await approve_action("ap-1", req)

        assert isinstance(resp, EventIngestionResponse) or hasattr(resp, "approval")
        from src.api.schemas import ApprovalActionResponse

        assert isinstance(resp, ApprovalActionResponse)
        assert resp.approval.status == "approved"
        assert resp.approval.resolved_by == "admin-1"
        assert resp.approval.resolved_at is not None
        assert "approved" in resp.message

    @pytest.mark.asyncio
    async def test_approve_unknown_id_returns_not_found(self) -> None:
        req = ApprovalActionRequest(resolved_by="admin-1")
        resp = await approve_action("ap-999", req)
        assert isinstance(resp, NotFoundResponse)
        assert resp.error.code == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_approve_already_resolved_returns_error(self) -> None:
        _seed_approval("ap-2", status="approved")
        req = ApprovalActionRequest(resolved_by="admin-1")
        resp = await approve_action("ap-2", req)
        assert isinstance(resp, NotFoundResponse)
        assert resp.error.code == "ALREADY_RESOLVED"


# ---------------------------------------------------------------------------
# POST /approvals/{id}/reject
# ---------------------------------------------------------------------------


class TestRejectAction:
    @pytest.mark.asyncio
    async def test_reject_pending_approval(self) -> None:
        _seed_approval("ap-3")
        req = ApprovalActionRequest(resolved_by="admin-2", reason="Too risky")
        resp = await reject_action("ap-3", req)

        from src.api.schemas import ApprovalActionResponse

        assert isinstance(resp, ApprovalActionResponse)
        assert resp.approval.status == "rejected"
        assert resp.approval.resolved_by == "admin-2"
        assert resp.approval.resolved_at is not None
        assert "rejected" in resp.message

    @pytest.mark.asyncio
    async def test_reject_unknown_id_returns_not_found(self) -> None:
        req = ApprovalActionRequest(resolved_by="admin-2")
        resp = await reject_action("ap-999", req)
        assert isinstance(resp, NotFoundResponse)
        assert resp.error.code == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_reject_already_resolved_returns_error(self) -> None:
        _seed_approval("ap-4", status="rejected")
        req = ApprovalActionRequest(resolved_by="admin-2")
        resp = await reject_action("ap-4", req)
        assert isinstance(resp, NotFoundResponse)
        assert resp.error.code == "ALREADY_RESOLVED"


# ---------------------------------------------------------------------------
# Strict model validation (extra=forbid)
# ---------------------------------------------------------------------------


class TestStrictModels:
    def test_event_payload_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):  # ValidationError
            IncidentEventPayload(
                tenant_id="t-1",
                event_type="x",
                source="s",
                source_id="s-1",
                title="t",
                description="d",
                occurred_at=datetime.now(timezone.utc),
                reporter="r",
                surprise_field="boom",  # type: ignore[call-arg]
            )

    def test_approval_request_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            ApprovalActionRequest(
                resolved_by="admin",
                reason="ok",
                unexpected=True,  # type: ignore[call-arg]
            )

    def test_situation_response_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            SituationResponse(
                id="s-1",
                tenant_id="t-1",
                type="DELIVERY_BLOCKER",
                affected_entities=[],
                detected_condition="x",
                severity="medium",
                owner_id=None,
                evidence_ids=[],
                checkpoint_id="cp-1",
                business_impact="x",
                status="OPEN",
                fake_field="bad",  # type: ignore[call-arg]
            )

    def test_error_detail_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            ErrorDetail(
                code="X",
                message="Y",
                bogus=True,  # type: ignore[call-arg]
            )

    def test_pagination_meta_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            PaginationMeta(
                total=0,
                page=1,
                page_size=20,
                has_next=False,
                extra="nope",  # type: ignore[call-arg]
            )


# ---------------------------------------------------------------------------
# Route table sanity
# ---------------------------------------------------------------------------


class TestRouteTable:
    def test_all_expected_routes_present(self) -> None:
        from src.api.rest import ROUTE_TABLE

        expected = {
            "POST /api/v1/events",
            "GET /api/v1/situations",
            "GET /api/v1/situations/{id}",
            "GET /api/v1/missions",
            "GET /api/v1/missions/{id}",
            "GET /api/v1/incidents",
            "GET /api/v1/incidents/{id}",
            "GET /api/v1/vendors",
            "GET /api/v1/vendors/{id}",
            "GET /api/v1/approvals",
            "POST /api/v1/approvals/{id}/approve",
            "POST /api/v1/approvals/{id}/reject",
        }
        assert expected == set(ROUTE_TABLE.keys())

    def test_all_handlers_are_callable(self) -> None:
        from src.api.rest import ROUTE_TABLE

        for route, handler in ROUTE_TABLE.items():
            assert callable(handler), f"Handler for {route} is not callable"
