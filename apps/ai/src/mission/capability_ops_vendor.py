"""Vendor-operations capability vocabulary (V7 Phase 4, capability layer).

Extends the frozen 10-op registry (``src/mission/capability_ops.py``) with 15
vendor-operations ops over the V7 vendor domain (``src/entities/models.py``):

* READ (10): ``vendor.lookup``, ``vendor.get_contacts``, ``service.get``,
  ``service.get_dependencies``, ``incident.get``, ``incident.search``,
  ``sla.get``, ``sla.get_deadlines``, ``evidence.search``, ``evidence.get``.
* WRITE (5, every one through ``@governed_write`` with a fail-closed
  object/property pair): ``vendor_ticket.create``, ``vendor_ticket.update``,
  ``notification.send_internal``, ``notification.send_vendor``,
  ``incident.verify_recovery``.

Phase scope is registry + in-memory + contracts ONLY: backing
implementations live on :class:`VendorInMemoryMixin` (deterministic,
tenant-scoped, empty-by-default — the same fallback discipline as
``_InMemoryCapability``). Demo/prod bindings resolve in a later phase; no
real HTTP is wired here, and this module imports nothing from the
connector layer (import boundary: only the registry module and the
control-plane executor may touch connector packages).

Governance pairs (verified fail-closed: without a ``PlannedAction`` each
raises ``GovernanceError`` instead of committing):
* ticket ops            → (``Issue``, ``status``) — vendor tickets are
  issue-lifecycle writes, gated like issue closes.
* notification ops      → (``Message``, ``direction``) — outbound
  communication is high-blast.
* ``verify_recovery``   → (``Outcome``, ``result``) — recording a recovery
  verdict is a consequential outcome write.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.ontology.governance import governed_write

logger = logging.getLogger(__name__)

# The 15 vendor-operations op names (the 10 original ops are untouched).
VENDOR_READ_OPS = (
    "vendor.lookup",
    "vendor.get_contacts",
    "service.get",
    "service.get_dependencies",
    "incident.get",
    "incident.search",
    "sla.get",
    "sla.get_deadlines",
    "evidence.search",
    "evidence.get",
)

VENDOR_WRITE_OPS = (
    "vendor_ticket.create",
    "vendor_ticket.update",
    "notification.send_internal",
    "notification.send_vendor",
    "incident.verify_recovery",
)

VENDOR_OPS = VENDOR_READ_OPS + VENDOR_WRITE_OPS


# ── Error taxonomy (mirrors the jira_client pattern: retryable flag) ──────


class VendorOpError(Exception):
    """Base error for the vendor capability surface (fail-closed)."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class VendorRetryableError(VendorOpError):
    """Transient failure (timeout/transport/rate-limit class): safe to retry."""

    def __init__(self, message: str):
        super().__init__(message, retryable=True)


class VendorTerminalError(VendorOpError):
    """Terminal failure (validation/not-found/auth class): never retried."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False)


# ── Strict params (extra=forbid + strict types: malformed fails closed) ────


class _StrictParams(BaseModel):
    """Base for op params: reject unknown fields, reject coerced types."""

    model_config = ConfigDict(extra="forbid", strict=True)


class VendorLookupParams(_StrictParams):
    vendor_id: str = Field(min_length=1)


class VendorContactsParams(_StrictParams):
    vendor_id: str = Field(min_length=1)


class ServiceParams(_StrictParams):
    service_id: str = Field(min_length=1)


class IncidentGetParams(_StrictParams):
    incident_id: str = Field(min_length=1)


class IncidentSearchParams(_StrictParams):
    query: str = ""
    limit: int = Field(default=50, ge=1, le=200)


class SlaGetParams(_StrictParams):
    sla_id: str = Field(min_length=1)


class SlaDeadlinesParams(_StrictParams):
    sla_id: str = Field(min_length=1)
    incident_id: str = ""


class EvidenceSearchParams(_StrictParams):
    query: str = ""
    limit: int = Field(default=50, ge=1, le=200)


class EvidenceGetParams(_StrictParams):
    evidence_id: str = Field(min_length=1)


class TicketCreateParams(_StrictParams):
    vendor_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    title: str = ""
    status: str = "open"
    idempotency_key: str = ""


class TicketUpdateParams(_StrictParams):
    ticket_id: str = Field(min_length=1)
    fields: dict[str, Any] = Field(default_factory=dict)


class NotifyInternalParams(_StrictParams):
    channel: str = Field(min_length=1)
    text: str = Field(min_length=1)
    recipient: str = ""


class NotifyVendorParams(_StrictParams):
    vendor_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    channel: str = ""


class VerifyRecoveryParams(_StrictParams):
    incident_id: str = Field(min_length=1)
    expected: dict[str, Any] = Field(default_factory=dict)


def _validated(
    model_cls: type[_StrictParams], op_name: str, params: Any
) -> _StrictParams:
    """Validate *params* strictly; malformed input fails closed (terminal)."""
    if not isinstance(params, dict):
        raise VendorTerminalError(
            f"{op_name}: params must be a mapping, got {type(params).__name__}"
        )
    try:
        return model_cls(**params)
    except ValidationError as exc:
        raise VendorTerminalError(
            f"{op_name}: invalid params ({exc.error_count()} error(s))"
        ) from exc


def _stable_id(*parts: str) -> str:
    """Deterministic short id from tenant-scoped parts (idempotency-safe)."""
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return digest


# ── In-memory backing surface (mixed into _InMemoryCapability) ─────────────


class VendorInMemoryMixin:
    """Deterministic vendor-domain fallback (no network, no config).

    Empty-by-default: reads return ``{}``/``[]`` until a write populates the
    tenant-scoped ticket/notification stores. Stateful writes are
    idempotent: the same params derive the same record id, so re-execution
    returns the same record without duplicates. Requires the ``tenant_id``
    attribute from the host capability class.
    """

    tenant_id: str

    def _ticket_store(self) -> dict[str, dict[str, Any]]:
        return self.__dict__.setdefault("_vendor_tickets", {})

    def _notification_log(self) -> list[dict[str, Any]]:
        return self.__dict__.setdefault("_vendor_notifications", [])

    # — vendor —
    def get_vendor(self, vendor_id: str) -> dict[str, Any]:
        if not vendor_id:
            raise VendorTerminalError("vendor.lookup: vendor_id must be non-empty")
        return {}

    def get_vendor_contacts(self, vendor_id: str) -> list[dict[str, Any]]:
        if not vendor_id:
            raise VendorTerminalError(
                "vendor.get_contacts: vendor_id must be non-empty"
            )
        return []

    # — service —
    def get_service(self, service_id: str) -> dict[str, Any]:
        if not service_id:
            raise VendorTerminalError("service.get: service_id must be non-empty")
        return {}

    def get_service_dependencies(self, service_id: str) -> list[dict[str, Any]]:
        if not service_id:
            raise VendorTerminalError(
                "service.get_dependencies: service_id must be non-empty"
            )
        return []

    # — incident —
    def get_incident(self, incident_id: str) -> dict[str, Any]:
        if not incident_id:
            raise VendorTerminalError("incident.get: incident_id must be non-empty")
        return {}

    def search_incidents(self, **filters: Any) -> list[dict[str, Any]]:
        return []

    # — sla —
    def get_sla(self, sla_id: str) -> dict[str, Any]:
        if not sla_id:
            raise VendorTerminalError("sla.get: sla_id must be non-empty")
        return {}

    def get_sla_deadlines(
        self, sla_id: str, incident_id: str = ""
    ) -> dict[str, Any]:
        if not sla_id:
            raise VendorTerminalError("sla.get_deadlines: sla_id must be non-empty")
        return {"sla_id": sla_id, "incident_id": incident_id, "deadlines": []}

    # — evidence —
    def search_evidence(self, **filters: Any) -> list[dict[str, Any]]:
        return []

    def get_evidence(self, evidence_id: str) -> dict[str, Any]:
        if not evidence_id:
            raise VendorTerminalError("evidence.get: evidence_id must be non-empty")
        return {}

    # — vendor tickets (idempotent upsert by deterministic id) —
    def create_vendor_ticket(self, data: dict[str, Any]) -> dict[str, Any]:
        vendor_id = str(data.get("vendor_id", ""))
        incident_id = str(data.get("incident_id", ""))
        if not vendor_id or not incident_id:
            raise VendorTerminalError(
                "vendor_ticket.create: vendor_id and incident_id are required"
            )
        key = str(data.get("idempotency_key", "") or "")
        seed = f"{self.tenant_id}|{vendor_id}|{incident_id}|{key}"
        ticket_id = f"vt-{_stable_id(seed)}"
        store = self._ticket_store()
        if ticket_id not in store:
            store[ticket_id] = {
                "id": ticket_id,
                "tenant_id": self.tenant_id,
                "vendor_id": vendor_id,
                "incident_id": incident_id,
                "title": str(data.get("title", "")),
                "status": str(data.get("status", "open")),
            }
        return dict(store[ticket_id])

    def update_vendor_ticket(
        self, ticket_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        if not ticket_id:
            raise VendorTerminalError(
                "vendor_ticket.update: ticket_id must be non-empty"
            )
        store = self._ticket_store()
        record = store.get(ticket_id, {"id": ticket_id, "tenant_id": self.tenant_id})
        record = {**record, **dict(fields)}
        store[ticket_id] = record
        return dict(record)

    # — notifications (deduplicated by deterministic message id) —
    def send_internal_notification(
        self, channel: str, text: str, recipient: str = ""
    ) -> dict[str, Any]:
        if not channel or not text:
            raise VendorTerminalError(
                "notification.send_internal: channel and text are required"
            )
        message_id = f"msg-{_stable_id(self.tenant_id, channel, text, recipient)}"
        log = self._notification_log()
        if not any(entry["id"] == message_id for entry in log):
            log.append(
                {
                    "id": message_id,
                    "tenant_id": self.tenant_id,
                    "channel": channel,
                    "recipient": recipient,
                }
            )
        return {"ok": True, "id": message_id, "channel": channel}

    def send_vendor_notification(
        self, vendor_id: str, text: str, channel: str = ""
    ) -> dict[str, Any]:
        if not vendor_id or not text:
            raise VendorTerminalError(
                "notification.send_vendor: vendor_id and text are required"
            )
        message_id = f"msg-{_stable_id(self.tenant_id, vendor_id, text, channel)}"
        log = self._notification_log()
        if not any(entry["id"] == message_id for entry in log):
            log.append(
                {
                    "id": message_id,
                    "tenant_id": self.tenant_id,
                    "vendor_id": vendor_id,
                    "channel": channel,
                }
            )
        return {"ok": True, "id": message_id, "vendor_id": vendor_id}

    # — recovery verification (read-back predicate check, never bare 200) —
    def verify_incident_recovery(
        self, incident_id: str, expected: dict[str, Any]
    ) -> dict[str, Any]:
        if not incident_id:
            raise VendorTerminalError(
                "incident.verify_recovery: incident_id must be non-empty"
            )
        record = self.get_incident(incident_id)
        mismatches = [
            key for key, value in expected.items() if record.get(key) != value
        ]
        verified = bool(expected) and not mismatches
        return {
            "incident_id": incident_id,
            "verified": verified,
            "mismatches": mismatches,
            "record": record,
        }


# ── Governed write closures (all fail closed without a PlannedAction) ──────


@governed_write(object_type="Issue", property_name="status", requested_by="EmployeeRuntime")
def _execute_vendor_ticket_create(
    params: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    from src.mission.capability_ops import _config_for, _resolve_capability

    req = _validated(TicketCreateParams, "vendor_ticket.create", params)
    cap = _resolve_capability("vendor", _config_for(tenant_id))
    data = cap.create_vendor_ticket(
        {
            "vendor_id": req.vendor_id,
            "incident_id": req.incident_id,
            "title": req.title,
            "status": req.status,
            "idempotency_key": req.idempotency_key,
        }
    )
    return {"op": "vendor_ticket.create", "ok": True, "data": data}


@governed_write(object_type="Issue", property_name="status", requested_by="EmployeeRuntime")
def _execute_vendor_ticket_update(
    params: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    from src.mission.capability_ops import _config_for, _resolve_capability

    req = _validated(TicketUpdateParams, "vendor_ticket.update", params)
    cap = _resolve_capability("vendor", _config_for(tenant_id))
    data = cap.update_vendor_ticket(req.ticket_id, dict(req.fields))
    return {"op": "vendor_ticket.update", "ok": True, "data": data}


@governed_write(
    object_type="Message", property_name="direction", requested_by="EmployeeRuntime"
)
def _execute_notify_internal(
    params: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    from src.mission.capability_ops import _config_for, _resolve_capability

    req = _validated(NotifyInternalParams, "notification.send_internal", params)
    cap = _resolve_capability("notification", _config_for(tenant_id))
    data = cap.send_internal_notification(req.channel, req.text, req.recipient)
    return {"op": "notification.send_internal", "ok": True, "data": data}


@governed_write(
    object_type="Message", property_name="direction", requested_by="EmployeeRuntime"
)
def _execute_notify_vendor(
    params: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    from src.mission.capability_ops import _config_for, _resolve_capability

    req = _validated(NotifyVendorParams, "notification.send_vendor", params)
    cap = _resolve_capability("notification", _config_for(tenant_id))
    data = cap.send_vendor_notification(req.vendor_id, req.text, req.channel)
    return {"op": "notification.send_vendor", "ok": True, "data": data}


@governed_write(
    object_type="Outcome", property_name="result", requested_by="EmployeeRuntime"
)
def _execute_verify_recovery(
    params: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    from src.mission.capability_ops import _config_for, _resolve_capability

    req = _validated(VerifyRecoveryParams, "incident.verify_recovery", params)
    cap = _resolve_capability("incident", _config_for(tenant_id))
    data = cap.verify_incident_recovery(req.incident_id, dict(req.expected))
    return {
        "op": "incident.verify_recovery",
        "ok": True,
        "verified": bool(data.get("verified", False)),
        "data": data,
    }


def build_vendor_ops() -> list[Any]:
    """Build the 15 vendor-operations ops with the shared frozen builders."""
    from src.mission.capability_ops import _read_op, _search_op, _write_op

    return [
        _read_op(
            "vendor.lookup", "vendor", "get_vendor", "vendor",
            lambda cap, p: cap.get_vendor(
                _validated(VendorLookupParams, "vendor.lookup", p).vendor_id
            ),
        ),
        _read_op(
            "vendor.get_contacts", "vendor", "get_vendor_contacts", "vendor",
            lambda cap, p: cap.get_vendor_contacts(
                _validated(VendorContactsParams, "vendor.get_contacts", p).vendor_id
            ),
        ),
        _read_op(
            "service.get", "service", "get_service", "service",
            lambda cap, p: cap.get_service(
                _validated(ServiceParams, "service.get", p).service_id
            ),
        ),
        _read_op(
            "service.get_dependencies",
            "service",
            "get_service_dependencies",
            "service",
            lambda cap, p: cap.get_service_dependencies(
                _validated(ServiceParams, "service.get_dependencies", p).service_id
            ),
        ),
        _read_op(
            "incident.get", "incident", "get_incident", "incident",
            lambda cap, p: cap.get_incident(
                _validated(IncidentGetParams, "incident.get", p).incident_id
            ),
        ),
        _search_op(
            "incident.search", "incident", "search_incidents", "incident",
            lambda cap, p: cap.search_incidents(
                **_validated(IncidentSearchParams, "incident.search", p).model_dump()
            ),
        ),
        _read_op(
            "sla.get", "sla", "get_sla", "sla",
            lambda cap, p: cap.get_sla(
                _validated(SlaGetParams, "sla.get", p).sla_id
            ),
        ),
        _read_op(
            "sla.get_deadlines", "sla", "get_sla_deadlines", "sla",
            lambda cap, p: cap.get_sla_deadlines(
                **_validated(SlaDeadlinesParams, "sla.get_deadlines", p).model_dump()
            ),
        ),
        _search_op(
            "evidence.search", "evidence", "search_evidence", "evidence",
            lambda cap, p: cap.search_evidence(
                **_validated(EvidenceSearchParams, "evidence.search", p).model_dump()
            ),
        ),
        _read_op(
            "evidence.get", "evidence", "get_evidence", "evidence",
            lambda cap, p: cap.get_evidence(
                _validated(EvidenceGetParams, "evidence.get", p).evidence_id
            ),
        ),
        _write_op(
            "vendor_ticket.create",
            "vendor",
            "create_vendor_ticket",
            "vendor",
            _execute_vendor_ticket_create,
        ),
        _write_op(
            "vendor_ticket.update",
            "vendor",
            "update_vendor_ticket",
            "vendor",
            _execute_vendor_ticket_update,
        ),
        _write_op(
            "notification.send_internal",
            "notification",
            "send_internal_notification",
            "notification",
            _execute_notify_internal,
        ),
        _write_op(
            "notification.send_vendor",
            "notification",
            "send_vendor_notification",
            "notification",
            _execute_notify_vendor,
        ),
        _write_op(
            "incident.verify_recovery",
            "incident",
            "verify_incident_recovery",
            "incident",
            _execute_verify_recovery,
        ),
    ]
