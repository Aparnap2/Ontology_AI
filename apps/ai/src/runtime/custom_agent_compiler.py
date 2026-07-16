"""OntologyAI V5.1 — custom_agent runtime compiler (PRD §17.2, §17.3, §12.7).

Deterministically transforms an :class:`ExecutableWorkflowDraft` into a
config-driven ``custom_agent`` runtime config (instructions / tool list /
state machine). The payload is written ONLY through
``draft.set_export_payload(...)`` — the sanctioned setter.

Determinism
-----------
* State ids are ``"st{index}"`` ordered indices, not random UUIDs.
* The state machine is derived from the ordered step list plus decision /
  approval / fallback / success wiring, so the same draft always yields
  byte-identical JSON.
* No ``uuid`` / ``random`` module is imported or used anywhere in this file.
"""
from __future__ import annotations

from typing import Any

from src.ontology.workflow_drafts import ExecutableWorkflowDraft


def _instruction_for(step: dict[str, Any], index: int) -> str:
    """Deterministically render a natural-language instruction for a step."""
    action = step.get("action", f"step_{index}")
    params = step.get("params", {})
    return f"Step {index}: perform '{action}' with params {params!r}."


def compile_custom_agent(draft: ExecutableWorkflowDraft) -> dict[str, Any]:
    """Compile ``draft`` into a custom_agent runtime config payload.

    Args:
        draft: The executable workflow draft to compile. Must have
            ``runtime == "custom_agent"``.

    Returns:
        The custom_agent-shaped payload dict. The same dict is also written to
        ``draft.export_payload`` via the sanctioned ``set_export_payload`` setter.

    Raises:
        ValueError: If ``draft.runtime`` is not ``"custom_agent"``.
    """
    if draft.runtime != "custom_agent":
        raise ValueError(
            f"compile_custom_agent requires runtime='custom_agent', "
            f"got {draft.runtime!r}"
        )

    # ── Instructions: deterministic, ordered from steps ────────────────
    instructions: list[str] = []
    instructions.append(f"Goal: {draft.name}.")
    if draft.trigger:
        instructions.append(f"Trigger when: {draft.trigger!r}.")
    for i, step in enumerate(draft.steps, start=1):
        instructions.append(_instruction_for(step, i))
    for dp in draft.decision_points:
        instructions.append(
            f"Decision {dp.get('id', '?')}: if {dp.get('condition', 'true')} "
            f"then branch, else continue."
        )
    for ap in draft.approvals:
        instructions.append(
            f"Require approval from {ap.get('role', 'owner')} "
            f"(approval {ap.get('id', '?')})."
        )
    for se in draft.side_effects:
        instructions.append(f"Side effect: {se.get('effect', se.get('id', '?'))}.")
    for fb in draft.fallback_paths:
        instructions.append(
            f"On {fb.get('on', 'failure')} go to {fb.get('goto', 'start')}."
        )
    if draft.success_criteria:
        instructions.append(
            "Success when: " + "; ".join(draft.success_criteria) + "."
        )

    # ── Tool list: derived from step actions (deterministic) ───────────
    tools: list[dict[str, Any]] = []
    for step in draft.steps:
        action = step.get("action", "unknown")
        tools.append(
            {
                "name": str(action),
                "params": step.get("params", {}),
                "source_step": str(step.get("id", "")),
            }
        )

    # ── State machine: ordered, stable ids (st{index}) ─────────────────
    state_machine: list[dict[str, Any]] = []
    state_machine.append(
        {
            "index": 0,
            "id": "st0",
            "kind": "start",
            "on_enter": "await_trigger",
            "next": "st1" if draft.steps else "st_success",
        }
    )
    for i, step in enumerate(draft.steps, start=1):
        state_machine.append(
            {
                "index": i,
                "id": f"st{i}",
                "kind": "action",
                "action": step.get("action", f"step_{i}"),
                "next": f"st{i + 1}" if i < len(draft.steps) else "st_decision",
            }
        )
    # Decision fan-out state.
    decision_state_idx = len(draft.steps) + 1
    state_machine.append(
        {
            "index": decision_state_idx,
            "id": f"st{decision_state_idx}",
            "kind": "decision",
            "decision_points": [dp.get("id") for dp in draft.decision_points],
            "next": "st_approval" if draft.approvals else "st_success",
        }
    )
    # Approval gate state.
    approval_state_idx = decision_state_idx + 1
    state_machine.append(
        {
            "index": approval_state_idx,
            "id": f"st{approval_state_idx}",
            "kind": "approval",
            "approvals": [ap.get("id") for ap in draft.approvals],
            "next": "st_success",
        }
    )
    # Terminal success state.
    success_state_idx = approval_state_idx + 1
    state_machine.append(
        {
            "index": success_state_idx,
            "id": f"st{success_state_idx}",
            "kind": "success",
            "success_criteria": list(draft.success_criteria),
            "next": None,
        }
    )

    payload: dict[str, Any] = {
        "runtime": "custom_agent",
        "name": draft.name,
        "trigger": draft.trigger,
        "inputs": list(draft.inputs),
        "instructions": instructions,
        "tools": tools,
        "state_machine": state_machine,
        "fallback_paths": list(draft.fallback_paths),
        "meta": {
            "source_draft_id": draft.id,
            "source_workflow_spec_id": draft.source_workflow_spec_id,
        },
    }

    # The ONLY sanctioned path to set export_payload.
    draft.set_export_payload(payload)
    return payload
