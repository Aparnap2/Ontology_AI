"""Temporal activity: compile an ExecutableWorkflowDraft and deploy to n8n.

This is the real n8n compile path that the Go ``APIWorkflowDraftCompile`` stub
queues (workspace.go). It deterministically compiles the draft via
``runtime/n8n_compiler.py`` and deploys it to the managed, invisible n8n
runtime through ``runtime/n8n_client.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from temporalio import activity

from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.runtime import n8n_client
from src.runtime.n8n_compiler import compile_n8n

log = logging.getLogger(__name__)


def _safe_heartbeat(message: str) -> None:
    try:
        activity.heartbeat(message)
    except RuntimeError:
        log.debug("Heartbeat (no context): %s", message)


@activity.defn(name="compile_n8n_workflow")
def compile_n8n_workflow(
    draft_dict: dict[str, Any],
    activate: bool = False,
    execute: bool = False,
) -> dict[str, Any]:
    """Compile ``draft_dict`` and deploy it to the n8n runtime.

    Args:
        draft_dict: Serialized :class:`ExecutableWorkflowDraft`.
        activate: Activate the workflow in n8n after creation.
        execute: Execute the workflow in n8n after creation.

    Note:
        Activate/execute are positional-or-keyword (not keyword-only) to
        satisfy Temporal's ``@activity.defn`` constraint which rejects
        keyword-only parameters.

    Returns:
        Result dict from ``n8n_client.compile_and_deploy`` (workflow_id,
        payload, activated, execution).
    """
    _safe_heartbeat("validating draft")
    draft = ExecutableWorkflowDraft(**draft_dict)
    if draft.runtime != "n8n":
        raise ValueError(f"compile_n8n_workflow requires runtime='n8n', got {draft.runtime!r}")

    _safe_heartbeat("compiling")
    result = n8n_client.compile_and_deploy(
        draft, activate=activate, execute=execute
    )
    _safe_heartbeat(f"deployed workflow {result.get('workflow_id')}")
    return result


# Re-export the deterministic compiler so callers can pre-compile offline.
__all__ = ["compile_n8n_workflow", "compile_n8n"]
