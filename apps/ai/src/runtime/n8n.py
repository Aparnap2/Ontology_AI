"""OntologyAI V5.1 — N8NCompiler wrapper (adapter pattern).

Thin adapter that makes the existing deterministic ``compile_n8n()`` available
through the :class:`RuntimeCompiler` ABC interface.

The adapter:
1. Converts a generic draft dict to an ``ExecutableWorkflowDraft``.
2. Delegates to ``compile_n8n()`` (which sets ``export_payload`` via the
   sanctioned setter).
3. Returns the structured output dict (``runtime`` + ``files``).

Determinism is inherited from the underlying ``compile_n8n()`` — no
``uuid`` / ``random`` is introduced here.
"""

from __future__ import annotations

import json
from typing import Any

from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.runtime.base import RuntimeCompiler
from src.runtime.n8n_compiler import compile_n8n


def _dict_to_draft(draft: dict[str, Any]) -> ExecutableWorkflowDraft:
    """Convert a generic draft dict to an ``ExecutableWorkflowDraft``.

    Handles type coercions for fields that differ between the canonical IR
    dict and the strict Pydantic model (e.g. ``trigger`` may be a string,
    ``inputs`` may be a ``dict``, ``success_criteria`` may be a ``dict``).
    """
    # -- trigger: normalise str → dict ------------------------------------------
    trigger: dict[str, Any] = {}
    raw_trigger = draft.get("trigger")
    if isinstance(raw_trigger, dict):
        trigger = dict(raw_trigger)
    elif isinstance(raw_trigger, str):
        trigger = {"type": raw_trigger}

    # -- inputs: normalise dict → list[dict] ------------------------------------
    raw_inputs = draft.get("inputs", {})
    if isinstance(raw_inputs, dict):
        inputs: list[dict[str, Any]] = [
            {"name": k, "type": v} for k, v in raw_inputs.items()
        ]
    else:
        inputs = list(raw_inputs) if raw_inputs else []

    # -- success_criteria: normalise dict → list[str] ---------------------------
    raw_sc = draft.get("success_criteria", {})
    if isinstance(raw_sc, dict):
        success_criteria: list[str] = [str(v) for v in raw_sc.values()]
    elif isinstance(raw_sc, list):
        success_criteria = list(raw_sc)
    else:
        success_criteria = []

    # -- Build Pydantic model (extra="forbid" → strip unknown keys) -----------
    known_fields = {
        "id",
        "runtime",
        "name",
        "source_workflow_spec_id",
        "status",
        "trigger",
        "inputs",
        "steps",
        "decision_points",
        "approvals",
        "side_effects",
        "fallback_paths",
        "success_criteria",
        "export_payload",
        "source_refs",
    }
    safe: dict[str, Any] = {k: v for k, v in draft.items() if k in known_fields}

    return ExecutableWorkflowDraft(
        id=safe.get("id") or draft.get("mission_id", "unknown"),
        runtime="n8n",
        name=safe.get("name", f"Workflow {draft.get('mission_id', 'unknown')}"),
        source_workflow_spec_id=safe.get("source_workflow_spec_id")
        or draft.get("mission_id", "unknown"),
        trigger=trigger,
        inputs=inputs,
        steps=list(draft.get("steps", [])),
        decision_points=list(draft.get("decision_points", [])),
        approvals=list(draft.get("approvals", [])),
        side_effects=list(draft.get("side_effects", [])),
        fallback_paths=list(draft.get("fallback_paths", [])),
        success_criteria=success_criteria,
    )


class N8NCompiler(RuntimeCompiler):
    """Compiler targeting the n8n workflow runtime.

    Wraps the existing deterministic ``compile_n8n()`` function.
    """

    def compile(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Compile a draft dict into an n8n workflow payload.

        Returns:
            Dict with ``runtime="n8n"`` and ``files`` containing
            ``workflow.json`` (serialised n8n payload).
        """
        draft_obj = _dict_to_draft(draft)
        payload = compile_n8n(draft_obj)
        return {
            "runtime": "n8n",
            "files": {
                "workflow.json": json.dumps(payload, indent=2),
            },
        }
