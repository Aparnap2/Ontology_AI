"""OntologyAI V5.1 — n8n REST runtime client (PRD §17.3, §20.4, ADR-007).

This is the real bridge to the managed, INVISIBLE n8n runtime. The Go core /
Python AI worker call this client over the internal Docker network only
(``N8N_API_URL`` defaults to ``http://n8n:5678/api/v1``); n8n is never exposed
to clients (ADR-007).

Flow:
    1. ``compile_n8n(draft)`` (runtime/n8n_compiler.py) produces a deterministic
       n8n payload (nodes + connections).
    2. This client POSTs that payload to ``POST /rest/workflows/`` to create the
       workflow, optionally activates it, and/or ``POST /rest/workflows/:id/run``
       to execute it.

The client is httpx-based and transport-injectable so it is fully
unit-testable without a running n8n (see tests/test_n8n_client.py).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.runtime.n8n_compiler import compile_n8n

log = logging.getLogger(__name__)

# n8n public REST API base path (self-hosted). The API key is sent as the
# ``X-N8N-API-KEY`` header (see n8n auth docs).
_DEFAULT_API_URL = "http://n8n:5678/api/v1"


class N8nClientError(RuntimeError):
    """Raised when the n8n API returns a non-2xx response."""


def _api_url() -> str:
    return os.environ.get("N8N_API_URL", _DEFAULT_API_URL).rstrip("/")


def _api_key() -> Optional[str]:
    return os.environ.get("N8N_API_KEY") or None


def _headers() -> dict[str, str]:
    headers = {"accept": "application/json", "content-type": "application/json"}
    key = _api_key()
    if key:
        headers["X-N8N-API-KEY"] = key
    return headers


def create_workflow(
    payload: dict[str, Any],
    *,
    client: Optional[httpx.Client] = None,
    api_url: Optional[str] = None,
) -> dict[str, Any]:
    """Create a workflow in n8n via ``POST /rest/workflows/``.

    Args:
        payload: n8n-shaped workflow doc (name, nodes, connections, ...).
        client: Optional pre-configured ``httpx.Client`` (for tests).
        api_url: Optional override of the API base URL.

    Returns:
        The n8n API response dict (contains ``id`` of the new workflow).

    Raises:
        N8nClientError: On non-2xx response.
    """
    base = (api_url or _api_url()).rstrip("/")
    own = client is None
    cli = client or httpx.Client(timeout=30.0, verify=False)
    try:
        resp = cli.post(f"{base}/rest/workflows/", json=payload, headers=_headers())
        if resp.status_code >= 400:
            raise N8nClientError(
                f"n8n create_workflow failed {resp.status_code}: {resp.text}"
            )
        return resp.json()
    finally:
        if own:
            cli.close()


def activate_workflow(
    workflow_id: str,
    *,
    client: Optional[httpx.Client] = None,
    api_url: Optional[str] = None,
) -> dict[str, Any]:
    """Activate (enable) an existing n8n workflow."""
    base = (api_url or _api_url()).rstrip("/")
    own = client is None
    cli = client or httpx.Client(timeout=30.0, verify=False)
    try:
        resp = cli.patch(
            f"{base}/rest/workflows/{workflow_id}/activate",
            json={},
            headers=_headers(),
        )
        if resp.status_code >= 400:
            raise N8nClientError(
                f"n8n activate failed {resp.status_code}: {resp.text}"
            )
        return resp.json()
    finally:
        if own:
            cli.close()


def execute_workflow(
    workflow_id: str,
    *,
    payload: Optional[dict[str, Any]] = None,
    client: Optional[httpx.Client] = None,
    api_url: Optional[str] = None,
) -> dict[str, Any]:
    """Execute a workflow via ``POST /rest/workflows/:id/run``.

    Returns the execution response (contains ``executionId``).
    """
    base = (api_url or _api_url()).rstrip("/")
    own = client is None
    cli = client or httpx.Client(timeout=60.0, verify=False)
    try:
        resp = cli.post(
            f"{base}/rest/workflows/{workflow_id}/run",
            json=payload or {},
            headers=_headers(),
        )
        if resp.status_code >= 400:
            raise N8nClientError(
                f"n8n execute_workflow failed {resp.status_code}: {resp.text}"
            )
        return resp.json()
    finally:
        if own:
            cli.close()


def healthcheck(
    *,
    client: Optional[httpx.Client] = None,
    api_url: Optional[str] = None,
) -> bool:
    """Return True if the n8n instance is reachable (``/healthz``)."""
    base = (api_url or _api_url()).rstrip("/")
    own = client is None
    cli = client or httpx.Client(timeout=10.0, verify=False)
    try:
        # The API root responds 200 with version info when healthy.
        resp = cli.get(f"{base}/rest/workflows", headers=_headers())
        return resp.status_code < 500
    except httpx.HTTPError:
        return False
    finally:
        if own:
            cli.close()


def compile_and_deploy(
    draft: ExecutableWorkflowDraft,
    *,
    activate: bool = False,
    execute: bool = False,
    client: Optional[httpx.Client] = None,
    api_url: Optional[str] = None,
) -> dict[str, Any]:
    """End-to-end: compile the draft, create it in n8n, optionally activate/run.

    Returns a result dict with keys: ``workflow_id``, ``payload``,
    ``activated``, ``execution``. Uses the sanctioned ``compile_n8n`` so the
    deterministic export_payload guard still holds.
    """
    payload = compile_n8n(draft)
    created = create_workflow(payload, client=client, api_url=api_url)
    workflow_id = created.get("id") or created.get("name")
    result: dict[str, Any] = {
        "workflow_id": workflow_id,
        "payload": payload,
        "activated": None,
        "execution": None,
    }
    if activate and workflow_id:
        result["activated"] = activate_workflow(
            workflow_id, client=client, api_url=api_url
        )
    if execute and workflow_id:
        result["execution"] = execute_workflow(
            workflow_id, client=client, api_url=api_url
        )
    return result
