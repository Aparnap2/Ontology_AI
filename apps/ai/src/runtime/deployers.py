"""OntologyAI V5.1 — Runtime deployers (PRD §17, §20.4).

Provides deployers that push compiled workflow artifacts to their target
runtimes:

* ``deploy_to_n8n`` — POSTs compiled n8n workflows to a running n8n instance
  via the existing :mod:`src.runtime.n8n_client` module.
* ``deploy_to_windmill`` — POSTs compiled Windmill scripts/flows to a running
  Windmill instance via the :mod:`src.runtime.windmill_client` module.
* ``deploy_custom_agent`` — Packages compiled custom-agent artifacts into a
  file bundle for export.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.runtime.n8n_client import N8nClientError, create_workflow
from src.runtime.windmill_client import (
    WindmillClientError,
    create_flow,
    create_script,
    set_variable,
)

log = logging.getLogger(__name__)


@dataclass
class DeployerResult:
    """Result of a deploy operation.

    Attributes:
        success: Whether the deploy succeeded.
        runtime: The target runtime name (``"n8n"``, ``"custom_agent"``, etc.).
        workflow_id: The created workflow id (n8n deploy) or ``None``.
        export_url: URL to access the exported artifact (if applicable).
        files: Dict of filename → content for artifact bundles (custom agent).
        error: Error message if deployment failed.
    """

    success: bool
    runtime: str
    workflow_id: str | None = None
    export_url: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    error: str | None = None


def deploy_to_n8n(
    draft: dict[str, Any],
    credentials: dict[str, Any],
) -> DeployerResult:
    """Deploy a compiled n8n workflow to a running n8n instance.

    Args:
        draft: The compiled n8n workflow payload dict (must have ``name``,
            ``nodes``, ``connections``).
        credentials: Dict containing:
            - ``url``: n8n API base URL (e.g. ``http://n8n:5678/api/v1``).
            - ``api_key``: n8n API key for ``X-N8N-API-KEY`` header.
            - ``client`` (optional): An ``httpx.Client`` instance for testing.

    Returns:
        A :class:`DeployerResult` with the outcome.

    Raises:
        ValueError: If required credentials (``url`` or ``api_key``) are
            missing.
    """
    if not credentials:
        raise ValueError(
            "n8n credentials are required: {'url': ..., 'api_key': ...}"
        )

    api_url = credentials.get("url")
    api_key = credentials.get("api_key")

    if not api_url:
        raise ValueError("n8n 'url' is required in credentials")
    if not api_key:
        raise ValueError("n8n 'api_key' is required in credentials")

    # Optional test injection: httpx.Client for mock transport.
    client: httpx.Client | None = credentials.get("client")

    try:
        response = create_workflow(
            draft,
            client=client,
            api_url=api_url,
        )
        workflow_id = response.get("id") or response.get("name", "")
        log.info(
            "Deployed n8n workflow",
            extra={"workflow_id": workflow_id, "api_url": api_url},
        )
        return DeployerResult(
            success=True,
            runtime="n8n",
            workflow_id=str(workflow_id) if workflow_id else None,
        )
    except (N8nClientError, httpx.HTTPError) as exc:
        error_msg = f"n8n deploy failed: {exc}"
        log.warning(error_msg)
        return DeployerResult(
            success=False,
            runtime="n8n",
            error=error_msg,
        )


def deploy_custom_agent(
    draft: dict[str, Any],
    credentials: dict[str, Any],
) -> DeployerResult:
    """Package a compiled custom-agent artifact for export.

    Produces a set of files (``config.json``, ``instructions.txt``) that can
    be exported or consumed by the custom agent runtime.

    Args:
        draft: The compiled custom agent payload dict (must have ``name``,
            ``steps``, etc.).
        credentials: Dict containing at minimum ``tenant_id`` for metadata.

    Returns:
        A :class:`DeployerResult` with the artifact bundle in ``files``.
    """
    name = draft.get("name", "custom_agent")
    steps = draft.get("steps", [])
    tenant_id = credentials.get("tenant_id", "unknown")

    # Build config.json with metadata.
    config = {
        "name": name,
        "runtime": "custom_agent",
        "version": "1.0.0",
        "tenant_id": tenant_id,
    }

    # Build instructions.txt from the step list.
    instructions_lines: list[str] = [f"Agent: {name}"]
    for i, step in enumerate(steps, start=1):
        action = step.get("action", f"step_{i}")
        instructions_lines.append(f"  Step {i}: {action}")

    files: dict[str, str] = {
        "config.json": json.dumps(config, indent=2),
        "instructions.txt": "\n".join(instructions_lines) + "\n",
    }

    log.info(
        "Packaged custom agent artifact",
        extra={"name": name, "file_count": len(files)},
    )

    return DeployerResult(
        success=True,
        runtime="custom_agent",
        files=files,
    )


def deploy_to_windmill(
    draft: dict[str, Any],
    credentials: dict[str, Any],
) -> DeployerResult:
    """Deploy a compiled Windmill artifact to a running Windmill instance.

    Args:
        draft: The compiled Windmill payload dict (from ``WindmillCompiler``).
            Must contain keys ``target_type``, ``path``, and ``summary``.
            For ``target_type="script"`` also requires ``content``, ``language``,
            ``schema``. For ``target_type="flow"`` also requires ``flow_value``.
            Optionally may contain ``secrets`` (dict of name → value) to set
            as Windmill variables.
        credentials: Dict containing:
            - ``workspace``: Windmill workspace name.
            - ``token``: Windmill Bearer token for authentication.
            - ``base_url`` (optional): Windmill API base URL override.
            - ``client`` (optional): An ``httpx.Client`` instance for testing.

    Returns:
        A :class:`DeployerResult` with the outcome.

    Raises:
        ValueError: If required credentials (``workspace`` or ``token``) are
            missing.
    """
    if not credentials:
        raise ValueError(
            "Windmill credentials are required: "
            "{'workspace': ..., 'token': ...}"
        )

    workspace = credentials.get("workspace")
    token = credentials.get("token")

    if not workspace:
        raise ValueError("Windmill 'workspace' is required in credentials")
    if not token:
        raise ValueError("Windmill 'token' is required in credentials")

    # Optional test injection: httpx.Client and API base URL override.
    client: httpx.Client | None = credentials.get("client")
    api_base: str | None = credentials.get("base_url")

    target_type = draft.get("target_type", "script")
    path = draft.get("path", "f/iterateswarm/unknown")

    try:
        if target_type == "flow":
            response = create_flow(
                workspace,
                token,
                draft,
                client=client,
                api_base=api_base,
            )
        else:
            response = create_script(
                workspace,
                token,
                draft,
                client=client,
                api_base=api_base,
            )

        workflow_id = response.get("id") or response.get("path", path)

        # Set secrets as Windmill variables if present.
        secrets: dict[str, str] = draft.get("secrets", {})
        if isinstance(secrets, dict):
            for var_name, var_value in secrets.items():
                try:
                    set_variable(
                        workspace,
                        token,
                        var_name,
                        str(var_value),
                        client=client,
                        api_base=api_base,
                    )
                except (WindmillClientError, httpx.HTTPError) as sec_exc:
                    log.warning(
                        "Failed to set Windmill variable",
                        extra={"name": var_name, "error": str(sec_exc)},
                    )

        log.info(
            "Deployed Windmill artifact",
            extra={
                "target_type": target_type,
                "path": path,
                "workspace": workspace,
            },
        )
        return DeployerResult(
            success=True,
            runtime="windmill",
            workflow_id=str(workflow_id) if workflow_id else None,
        )

    except (WindmillClientError, httpx.HTTPError) as exc:
        error_msg = f"Windmill deploy failed: {exc}"
        log.warning(error_msg)
        return DeployerResult(
            success=False,
            runtime="windmill",
            error=error_msg,
        )
