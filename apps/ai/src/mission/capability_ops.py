"""Capability Op Registry — the frozen deterministic ops over connectors.

Employees never call connectors directly. They reach external systems ONLY
through :class:`CapabilityOpRegistry` ops, which wrap the existing capability
layer (``src/mission/capability.py`` → ``src/connectors``).

The registry holds the frozen union of the employee capability allowlists:
the original 10 ops over 4 connectors plus the V7 Phase 4 vendor-operations
vocabulary (15 ops over the vendor domain, built in
``src/mission/capability_ops_vendor.py`` with the same builders and
registered here). The write ops are routed through ``@governed_write``
(ontology governance) so every mutation is HITL-gated and auditable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from src.connectors.base import ConnectorConfig
from src.mission.capability import CapabilityRegistry
from src.mission.capability_ops_vendor import VendorInMemoryMixin
from src.ontology.governance import governed_write

logger = logging.getLogger(__name__)


class CapabilityOpError(Exception):
    """Base error for the capability op layer."""


class UnknownCapabilityOpError(CapabilityOpError):
    """Raised when an op name is not registered."""


class CapabilityNotAllowedError(CapabilityOpError):
    """Raised when a role's capability allowlist does not admit an op."""


def _config_for(tenant_id: str) -> ConnectorConfig:
    """Build the connector config for a tenant.

    ``mock_mode`` stays True under the ``test`` binding (exactly the
    historical behavior); demo/prod resolve real HTTP and must not claim
    mock semantics. The binding choice is invisible to mission/agent code:
    no caller branches on it outside this module.
    """
    from src.mission.capability_binding import get_capability_binding

    return ConnectorConfig(tenant_id=tenant_id, mock_mode=(get_capability_binding() == "test"))


def _resolve_demo_capability(capability: str, config: ConnectorConfig) -> Any:
    """Resolve a demo-binding capability (real HTTP to local Mockoon).

    Only bridged capabilities resolve; anything else fails closed with
    :class:`NotConfigured` instead of silently downgrading to in-memory.
    """
    import os

    from src.connectors.jira_client import JiraClient
    from src.mission.capability_binding import NotConfigured

    if capability == "project":
        base_url = os.environ.get("JIRA_MOCK_URL", "http://localhost:3003")
        return JiraClient(base_url=base_url, tenant_id=config.tenant_id, demo=True)
    raise NotConfigured(
        f"demo binding for capability {capability!r} is not bridged yet "
        "(bridged: project)"
    )


def _resolve_prod_capability(capability: str, config: ConnectorConfig) -> Any:
    """Resolve a prod-binding capability (real endpoint where configured).

    Fails closed with :class:`NotConfigured` until credentials exist —
    never a silent in-memory fallback.
    """
    import os

    from src.connectors.jira_client import JiraClient
    from src.mission.capability_binding import NotConfigured

    def _cred(name: str) -> str:
        return os.environ.get(name, "") or config.credentials.get(name.lower(), "")

    if capability == "project":
        base_url = _cred("JIRA_BASE_URL")
        username = _cred("JIRA_USERNAME")
        api_token = _cred("JIRA_API_TOKEN")
        missing = [
            label
            for label, value in (
                ("JIRA_BASE_URL", base_url),
                ("JIRA_USERNAME", username),
                ("JIRA_API_TOKEN", api_token),
            )
            if not value
        ]
        if missing:
            raise NotConfigured(
                f"prod binding for capability {capability!r} has no credentials "
                f"configured (tenant {config.tenant_id!r}): missing {missing}"
            )
        return JiraClient(
            base_url=base_url, tenant_id=config.tenant_id,
            username=username, api_token=api_token,
        )
    raise NotConfigured(
        f"prod binding for capability {capability!r} is not bridged yet "
        "(bridged: project)"
    )


def _resolve_capability(capability: str, config: ConnectorConfig) -> Any:
    """Resolve a capability instance from the existing capability layer.

    The implementation is selected by the runtime binding (see
    ``src/mission/capability_binding.py``); mission/agent code must not
    branch on the choice. Under ``test`` (the default) this keeps the
    historical behavior: the registered connector when one exists, else
    the deterministic in-memory fallback. Tests monkeypatch this seam to
    assert the exact connector method each op wraps.
    """
    from src.mission.capability_binding import get_capability_binding

    binding = get_capability_binding()
    if binding == "test":
        try:
            return CapabilityRegistry.get_capability(capability, config)
        except KeyError:
            return _InMemoryCapability(capability, config)
    if binding == "demo":
        return _resolve_demo_capability(capability, config)
    return _resolve_prod_capability(capability, config)


class _InMemoryCapability(VendorInMemoryMixin):
    """Deterministic in-memory fallback capability (no network, no config).

    Mirrors the method surface of the capability layer so every op stays
    executable when no real connector is registered. The vendor-domain
    surface (vendor/service/incident/sla/evidence/notification) mixes in
    from ``VendorInMemoryMixin`` with the same empty-by-default,
    tenant-scoped, deterministic discipline.
    """

    def __init__(self, capability: str, config: ConnectorConfig) -> None:
        self.capability = capability
        self.tenant_id = config.tenant_id

    def get_customers(self) -> list[dict[str, Any]]:
        return []

    def get_deals(self) -> list[dict[str, Any]]:
        return []

    def update_deal(self, deal_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        return {"id": deal_id, **fields}

    def get_messages(self, channel: str, **filters: Any) -> list[dict[str, Any]]:
        return []

    def send_message(self, channel: str, text: str) -> dict[str, Any]:
        return {"ok": True, "channel": channel}

    def get_issues(self, **filters: Any) -> list[dict[str, Any]]:
        return []

    def create_issue(self, data: dict[str, Any]) -> str:
        return "X-1"

    def update_issue(self, issue_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        return {"id": issue_id, **fields}

    def get_pages(self, **filters: Any) -> list[dict[str, Any]]:
        return []

    def update_page(self, page_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"id": page_id, **data}


@dataclass(frozen=True)
class CapabilityOp:
    """A frozen, deterministic op over a single capability method."""

    name: str
    capability: str
    method: str
    kind: str
    connector_capability: str
    governed: bool
    execute: Callable[[dict[str, Any], str], dict[str, Any]]


# ── Governed write closures (decorated so every mutation is HITL-gated) ────


@governed_write(object_type="Opportunity", property_name="stage", requested_by="EmployeeRuntime")
def _execute_salesforce_update(params: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    cap = _resolve_capability("crm", _config_for(tenant_id))
    data = cap.update_deal(params.get("record_id", ""), params.get("fields", {}))
    return {"op": "salesforce.update", "ok": True, "data": data}


@governed_write(object_type="Message", property_name="text", requested_by="EmployeeRuntime")
def _execute_slack_send(params: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    cap = _resolve_capability("messaging", _config_for(tenant_id))
    data = cap.send_message(params.get("channel", ""), params.get("text", ""))
    return {"op": "slack.send", "ok": True, "data": data}


@governed_write(object_type="Issue", property_name="summary", requested_by="EmployeeRuntime")
def _execute_jira_create(params: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    cap = _resolve_capability("project", _config_for(tenant_id))
    # Adapter mapping (integration boundary): the resolved owner arrives as
    # ``owner``/``assignee`` in intent params; Jira speaks ``assignee``.
    data = cap.create_issue(
        {
            "project": params.get("project", ""),
            "summary": params.get("summary", ""),
            "description": params.get("description", ""),
            "issue_type": params.get("issue_type", "Task"),
            "assignee": params.get("assignee") or params.get("owner") or "",
        }
    )
    return {"op": "jira.create", "ok": True, "data": data}


@governed_write(object_type="Issue", property_name="summary", requested_by="EmployeeRuntime")
def _execute_jira_update(params: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    cap = _resolve_capability("project", _config_for(tenant_id))
    data = cap.update_issue(params.get("issue_id", ""), params.get("fields", {}))
    return {"op": "jira.update", "ok": True, "data": data}


@governed_write(object_type="SOP", property_name="content", requested_by="EmployeeRuntime")
def _execute_notion_update(params: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    cap = _resolve_capability("knowledge", _config_for(tenant_id))
    data = cap.update_page(params.get("page_id", ""), params.get("data", {}))
    return {"op": "notion.update", "ok": True, "data": data}


# ── Frozen op builders (module level so the vendor vocabulary module ─────
# reuses the identical builders; behavior is unchanged from the nested form)


def _read_op(
    name: str,
    capability: str,
    method: str,
    connector_capability: str,
    fn: Callable[[Any, dict[str, Any]], Any],
) -> CapabilityOp:
    def execute(params: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        cap = _resolve_capability(capability, _config_for(tenant_id))
        data = fn(cap, params)
        return {"op": name, "ok": True, "data": data}

    return CapabilityOp(
        name=name,
        capability=capability,
        method=method,
        kind="read",
        connector_capability=connector_capability,
        governed=False,
        execute=execute,
    )


def _search_op(
    name: str,
    capability: str,
    method: str,
    connector_capability: str,
    fn: Callable[[Any, dict[str, Any]], Any],
) -> CapabilityOp:
    def execute(params: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        cap = _resolve_capability(capability, _config_for(tenant_id))
        data = fn(cap, params)
        return {"op": name, "ok": True, "data": data}

    return CapabilityOp(
        name=name,
        capability=capability,
        method=method,
        kind="search",
        connector_capability=connector_capability,
        governed=False,
        execute=execute,
    )


def _write_op(
    name: str,
    capability: str,
    method: str,
    connector_capability: str,
    fn: Callable[[dict[str, Any], str], dict[str, Any]],
) -> CapabilityOp:
    return CapabilityOp(
        name=name,
        capability=capability,
        method=method,
        kind="write",
        connector_capability=connector_capability,
        governed=True,
        execute=fn,
    )


def _build_ops() -> list[CapabilityOp]:
    """Build the frozen op set: the original 10 plus the vendor vocabulary."""
    ops = [
        # CRM (Salesforce)
        _read_op(
            "salesforce.read",
            "crm",
            "get_deals",
            "salesforce",
            lambda cap, params: (
                cap.get_customers() if params.get("object_type") == "customer" else cap.get_deals()
            ),
        ),
        _write_op(
            "salesforce.update",
            "crm",
            "update_deal",
            "salesforce",
            _execute_salesforce_update,
        ),
        # Communication (Slack)
        _search_op(
            "slack.search",
            "messaging",
            "get_messages",
            "slack",
            lambda cap, params: cap.get_messages(
                params.get("channel", ""),
                query=params.get("query"),
                limit=params.get("limit"),
            ),
        ),
        _write_op("slack.send", "messaging", "send_message", "slack", _execute_slack_send),
        # Project (Jira)
        _search_op(
            "jira.search",
            "project",
            "get_issues",
            "jira",
            lambda cap, params: cap.get_issues(
                query=params.get("query"), limit=params.get("limit")
            ),
        ),
        _read_op(
            "jira.read",
            "project",
            "get_issues",
            "jira",
            lambda cap, params: cap.get_issues(jql=params.get("jql"), limit=params.get("limit")),
        ),
        _write_op("jira.create", "project", "create_issue", "jira", _execute_jira_create),
        _write_op("jira.update", "project", "update_issue", "jira", _execute_jira_update),
        # Knowledge (Notion)
        _read_op(
            "notion.read",
            "knowledge",
            "get_pages",
            "notion",
            lambda cap, params: cap.get_pages(
                query=params.get("query"),
                page_id=params.get("page_id"),
                limit=params.get("limit"),
            ),
        ),
        _write_op("notion.update", "knowledge", "update_page", "notion", _execute_notion_update),
    ]
    # V7 Phase 4 vendor-operations vocabulary (same builders, same registry;
    # lazy import keeps the vendor module free of import cycles).
    from src.mission.capability_ops_vendor import build_vendor_ops

    return ops + build_vendor_ops()


class CapabilityOpRegistry:
    """Registry of the frozen capability ops (original 10 + vendor vocabulary)."""

    _ops: dict[str, CapabilityOp] = {}

    @classmethod
    def _ensure_loaded(cls) -> None:
        if not cls._ops:
            for op in _build_ops():
                cls._ops[op.name] = op

    @classmethod
    def get(cls, name: str) -> CapabilityOp:
        """Return the op for *name*, raising :class:`UnknownCapabilityOpError`."""
        cls._ensure_loaded()
        try:
            return cls._ops[name]
        except KeyError:
            raise UnknownCapabilityOpError(f"unknown capability op: {name}") from None

    @classmethod
    def list_ops(cls) -> list[str]:
        """Return the sorted names of all registered ops."""
        cls._ensure_loaded()
        return sorted(cls._ops)

    @classmethod
    def write_ops(cls) -> list[str]:
        """Return the sorted names of the governed write ops."""
        cls._ensure_loaded()
        return sorted(name for name, op in cls._ops.items() if op.governed)

    @classmethod
    def assert_allowed(cls, name: str, role_caps: list[str] | None) -> None:
        """Enforce the role capability allowlist (no-op when role_caps is None)."""
        if role_caps is None:
            return
        if name not in role_caps:
            raise CapabilityNotAllowedError(
                f"op {name} not in role capability allowlist {role_caps}"
            )

    @classmethod
    def execute(
        cls,
        name: str,
        params: dict[str, Any],
        tenant_id: str,
        *,
        role_caps: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute *name* with *params*, enforcing the role allowlist first."""
        op = cls.get(name)
        cls.assert_allowed(name, role_caps)
        return op.execute(params, tenant_id)