"""Temporal activity: compile and deploy a Windmill script/flow.

This activity compiles raw workflow content into a Windmill-compatible payload
via ``runtime/windmill_compiler.py`` and deploys it to the managed Windmill
runtime through ``runtime/windmill_client.py``.

Unlike the n8n activity (which operates on structured ``ExecutableWorkflowDraft``
objects), this activity accepts simple parameters (workflow_name, script_content,
env_vars) and constructs a minimal draft internally.
"""

from __future__ import annotations

import logging
from typing import Any

from temporalio import activity

from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.runtime.experimental import windmill_client
from src.runtime.experimental.windmill_compiler import compile_windmill

log = logging.getLogger(__name__)

# Default Windmill workspace (ADR-009).
_WORKSPACE = "iterateswarm"


def _safe_heartbeat(message: str) -> None:
    try:
        activity.heartbeat(message)
    except RuntimeError:
        log.debug("Heartbeat (no context): %s", message)


@activity.defn(name="compile_windmill_workflow")
def compile_windmill_workflow(
    workflow_name: str,
    script_content: str,
    env_vars: dict[str, str],
) -> dict[str, Any]:
    """Compile ``script_content`` and deploy it as a Windmill script.

    Args:
        workflow_name: Name/path for the Windmill script.
        script_content: Python source code to deploy.
        env_vars: Environment variable overrides.

    Returns:
        A result dict with ``success`` (bool), ``deployment_url`` (on success),
        or ``error`` (on failure).
    """
    _safe_heartbeat(f"compiling windmill workflow: {workflow_name}")

    try:
        # Build a minimal ExecutableWorkflowDraft from simple parameters.
        draft = ExecutableWorkflowDraft(
            id=workflow_name,
            runtime="windmill",
            name=workflow_name,
            source_workflow_spec_id=workflow_name,
            trigger={},
            inputs=[
                {"name": k, "type": "string"}
                for k in env_vars or {}
            ],
            steps=[
                {
                    "id": "step_1",
                    "description": f"Execute {workflow_name}",
                    "content": script_content,
                }
            ],
            decision_points=[],
            approvals=[],
            side_effects=[],
            fallback_paths=[],
            success_criteria=[],
        )

        _safe_heartbeat("compiling windmill payload")
        payload = compile_windmill(draft)

        _safe_heartbeat("deploying to windmill")
        token = "placeholder"  # In production, fetched from vault/env

        if payload["target_type"] == "flow":
            response = windmill_client.create_flow(
                workspace=_WORKSPACE,
                token=token,
                payload=payload,
            )
        else:
            response = windmill_client.create_script(
                workspace=_WORKSPACE,
                token=token,
                payload=payload,
            )

        deployment_url = f"{_WORKSPACE}/{payload.get('path', workflow_name)}"
        _safe_heartbeat(f"deployed: {deployment_url}")

        return {
            "success": True,
            "deployment_url": deployment_url,
            "workflow_id": response.get("id", ""),
            "workflow_name": workflow_name,
            "target_type": payload.get("target_type", "script"),
        }

    except Exception as exc:
        log.exception("Windmill compile failed for %s", workflow_name)
        return {
            "success": False,
            "error": str(exc),
            "workflow_name": workflow_name,
        }


# Re-export the deterministic compiler so callers can pre-compile offline.
__all__ = ["compile_windmill_workflow", "compile_windmill"]
