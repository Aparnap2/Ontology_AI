"""OntologyAI V5.1 — Windmill REST runtime client (PRD §17.3, §20.4).

This is the bridge to the managed Windmill runtime. The Go core / Python AI
worker call this client over the internal Docker network only
(``WINDMILL_API_BASE`` defaults to ``http://windmill:8000/api``); Windmill is
never exposed to clients (ADR-007).

Flow:
    1. ``compile_windmill(draft)`` (runtime/windmill_compiler.py) produces a
       deterministic Windmill payload (target_type, path, summary, …).
    2. This client POSTs that payload to the appropriate Windmill API endpoint
       to create the script or flow.

Authentication is via Bearer token passed in the ``Authorization`` header.

The client is httpx-based and transport-injectable so it is fully
unit-testable without a running Windmill instance.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Windmill public API base path (self-hosted). Token is sent as a Bearer
# ``Authorization`` header (see Windmill auth docs).
_DEFAULT_API_BASE = "http://windmill:8000/api"


class WindmillClientError(RuntimeError):
    """Raised when the Windmill API returns a non-2xx response."""


def _api_base() -> str:
    return os.environ.get("WINDMILL_API_BASE", _DEFAULT_API_BASE).rstrip("/")


def _headers(token: str) -> dict[str, str]:
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
    }


def create_script(
    workspace: str,
    token: str,
    payload: dict[str, Any],
    *,
    client: httpx.Client | None = None,
    api_base: str | None = None,
) -> dict[str, Any]:
    """Create a script in Windmill via ``POST /api/w/{workspace}/scripts/create``.

    Args:
        workspace: Windmill workspace name.
        token: Bearer token for authentication.
        payload: The script payload dict (path, summary, content, language, …).
        client: Optional pre-configured ``httpx.Client`` (for tests).
        api_base: Optional override of the API base URL.

    Returns:
        The Windmill API response dict.

    Raises:
        WindmillClientError: On non-2xx response.
    """
    base = (api_base or _api_base()).rstrip("/")
    own = client is None
    cli = client or httpx.Client(timeout=30.0, verify=False)
    try:
        resp = cli.post(
            f"{base}/w/{workspace}/scripts/create",
            json=payload,
            headers=_headers(token),
        )
        if resp.status_code >= 400:
            raise WindmillClientError(
                f"Windmill create_script failed {resp.status_code}: {resp.text}"
            )
        return resp.json()
    finally:
        if own:
            cli.close()


def create_flow(
    workspace: str,
    token: str,
    payload: dict[str, Any],
    *,
    client: httpx.Client | None = None,
    api_base: str | None = None,
) -> dict[str, Any]:
    """Create / run a flow in Windmill via ``POST /api/w/{workspace}/jobs/run/flow_dependencies_async``.

    Args:
        workspace: Windmill workspace name.
        token: Bearer token for authentication.
        payload: The flow payload dict (path, summary, flow_value, …).
        client: Optional pre-configured ``httpx.Client`` (for tests).
        api_base: Optional override of the API base URL.

    Returns:
        The Windmill API response dict.

    Raises:
        WindmillClientError: On non-2xx response.
    """
    base = (api_base or _api_base()).rstrip("/")
    own = client is None
    cli = client or httpx.Client(timeout=60.0, verify=False)
    try:
        resp = cli.post(
            f"{base}/w/{workspace}/jobs/run/flow_dependencies_async",
            json=payload,
            headers=_headers(token),
        )
        if resp.status_code >= 400:
            raise WindmillClientError(
                f"Windmill create_flow failed {resp.status_code}: {resp.text}"
            )
        return resp.json()
    finally:
        if own:
            cli.close()


def run_script(
    workspace: str,
    token: str,
    path: str,
    args: dict[str, Any],
    *,
    client: httpx.Client | None = None,
    api_base: str | None = None,
) -> dict[str, Any]:
    """Run a script by path via ``POST /api/w/{workspace}/jobs/run/p/{path}``.

    Args:
        workspace: Windmill workspace name.
        token: Bearer token for authentication.
        path: The script path (e.g. ``"f/iterateswarm/draft-123"``).
        args: Dict of arguments to pass to the script.
        client: Optional pre-configured ``httpx.Client`` (for tests).
        api_base: Optional override of the API base URL.

    Returns:
        The Windmill API response dict (contains ``job_id``, etc.).

    Raises:
        WindmillClientError: On non-2xx response.
    """
    base = (api_base or _api_base()).rstrip("/")
    own = client is None
    cli = client or httpx.Client(timeout=30.0, verify=False)
    try:
        resp = cli.post(
            f"{base}/w/{workspace}/jobs/run/p/{path.lstrip('/')}",
            json=args,
            headers=_headers(token),
        )
        if resp.status_code >= 400:
            raise WindmillClientError(
                f"Windmill run_script failed {resp.status_code}: {resp.text}"
            )
        return resp.json()
    finally:
        if own:
            cli.close()


def set_variable(
    workspace: str,
    token: str,
    name: str,
    value: str,
    *,
    client: httpx.Client | None = None,
    api_base: str | None = None,
) -> dict[str, Any]:
    """Set a Windmill variable via ``POST /api/w/{workspace}/variables/create``.

    Args:
        workspace: Windmill workspace name.
        token: Bearer token for authentication.
        name: Variable name.
        value: Variable value.
        client: Optional pre-configured ``httpx.Client`` (for tests).
        api_base: Optional override of the API base URL.

    Returns:
        The Windmill API response dict.

    Raises:
        WindmillClientError: On non-2xx response.
    """
    base = (api_base or _api_base()).rstrip("/")
    own = client is None
    cli = client or httpx.Client(timeout=30.0, verify=False)
    try:
        resp = cli.post(
            f"{base}/w/{workspace}/variables/create",
            json={
                "name": name,
                "value": value,
                "is_secret": True,
            },
            headers=_headers(token),
        )
        if resp.status_code >= 400:
            raise WindmillClientError(
                f"Windmill set_variable failed {resp.status_code}: {resp.text}"
            )
        return resp.json()
    finally:
        if own:
            cli.close()
