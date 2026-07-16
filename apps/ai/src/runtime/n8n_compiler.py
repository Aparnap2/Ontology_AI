"""OntologyAI V5.1 — n8n runtime compiler (PRD §17.1, §17.3, §12.7).

Deterministically transforms an :class:`ExecutableWorkflowDraft` into an n8n
workflow JSON document (``nodes`` + ``connections``). The payload is written
ONLY through ``draft.set_export_payload(...)`` — the sanctioned setter — never
by constructing a draft with ``export_payload`` already populated.

Determinism
-----------
* Node ids are ``"n{index}"`` ordered indices, not random UUIDs.
* Connections are derived from the ordered step list plus trigger/decision/
  fallback wiring, so the same draft always yields byte-identical JSON.
* No ``uuid`` / ``random`` module is imported or used anywhere in this file.
"""
from __future__ import annotations

from typing import Any

from src.ontology.workflow_drafts import ExecutableWorkflowDraft

# n8n node type catalogue (stable, versioned).
_TRIGGER_TYPE = "n8n-nodes-base.scheduleTrigger"
_STEP_TYPE = "n8n-nodes-base.code"
_DECISION_TYPE = "n8n-nodes-base.if"
_APPROVAL_TYPE = "n8n-nodes-base.noOp"
_SIDE_EFFECT_TYPE = "n8n-nodes-base.httpRequest"
_FALLBACK_TYPE = "n8n-nodes-base.switch"
_SUCCESS_TYPE = "n8n-nodes-base.set"


def _node(
    node_id: str,
    name: str,
    node_type: str,
    parameters: dict[str, Any],
    position: list[int],
    is_trigger: bool = False,
) -> dict[str, Any]:
    """Build a single n8n node dict with the required n8n fields."""
    return {
        "id": node_id,
        "name": name,
        "type": node_type,
        "typeVersion": 2,
        "parameters": parameters,
        "position": position,
        "is_trigger": is_trigger,
        "webhookId": None,
    }


def compile_n8n(draft: ExecutableWorkflowDraft) -> dict[str, Any]:
    """Compile ``draft`` into an n8n workflow payload.

    Args:
        draft: The executable workflow draft to compile. Must have
            ``runtime == "n8n"``.

    Returns:
        The n8n-shaped payload dict (``nodes`` + ``connections``). The same
        dict is also written to ``draft.export_payload`` via the sanctioned
        ``set_export_payload`` setter.

    Raises:
        ValueError: If ``draft.runtime`` is not ``"n8n"``.
    """
    if draft.runtime != "n8n":
        raise ValueError(
            f"compile_n8n requires runtime='n8n', got {draft.runtime!r}"
        )

    nodes: list[dict[str, Any]] = []
    connections: dict[str, Any] = {}
    idx = 0

    # 1) Trigger node (always first, deterministic id n0).
    trigger_params = dict(draft.trigger) if draft.trigger else {"type": "manual"}
    trigger_node = _node(
        node_id=f"n{idx}",
        name="Trigger",
        node_type=_TRIGGER_TYPE,
        parameters=trigger_params,
        position=[0, 0],
        is_trigger=True,
    )
    nodes.append(trigger_node)
    prev_id = trigger_node["id"]
    idx += 1

    # 2) Step nodes (ordered n1..n{k}).
    step_ids: list[str] = []
    for step in draft.steps:
        node_id = f"n{idx}"
        step_ids.append(node_id)
        nodes.append(
            _node(
                node_id=node_id,
                name=str(step.get("id", f"step_{idx}")),
                node_type=_STEP_TYPE,
                parameters={"step": step},
                position=[idx * 250, 0],
            )
        )
        idx += 1

    # 3) Decision nodes (one per decision point).
    decision_ids: list[str] = []
    for dp in draft.decision_points:
        node_id = f"n{idx}"
        decision_ids.append(node_id)
        nodes.append(
            _node(
                node_id=node_id,
                name=str(dp.get("id", f"decision_{idx}")),
                node_type=_DECISION_TYPE,
                parameters={"condition": dp.get("condition", "true")},
                position=[idx * 250, 200],
            )
        )
        idx += 1

    # 4) Approval nodes.
    for ap in draft.approvals:
        node_id = f"n{idx}"
        nodes.append(
            _node(
                node_id=node_id,
                name=str(ap.get("id", f"approval_{idx}")),
                node_type=_APPROVAL_TYPE,
                parameters={"approval": ap},
                position=[idx * 250, 400],
            )
        )
        idx += 1

    # 5) Side-effect nodes.
    for se in draft.side_effects:
        node_id = f"n{idx}"
        nodes.append(
            _node(
                node_id=node_id,
                name=str(se.get("id", f"side_effect_{idx}")),
                node_type=_SIDE_EFFECT_TYPE,
                parameters={"side_effect": se},
                position=[idx * 250, 600],
            )
        )
        idx += 1

    # 6) Fallback nodes (switch per fallback path).
    for fb in draft.fallback_paths:
        node_id = f"n{idx}"
        nodes.append(
            _node(
                node_id=node_id,
                name=str(fb.get("id", f"fallback_{idx}")),
                node_type=_FALLBACK_TYPE,
                parameters={"fallback": fb},
                position=[idx * 250, 800],
            )
        )
        idx += 1

    # 7) Success node (terminal, emits success_criteria).
    success_node = _node(
        node_id=f"n{idx}",
        name="Success",
        node_type=_SUCCESS_TYPE,
        parameters={"success_criteria": list(draft.success_criteria)},
        position=[idx * 250, 0],
    )
    nodes.append(success_node)
    idx += 1

    # ── Wire connections (deterministic, ordered) ──────────────────────
    # Trigger -> first step (or success if no steps).
    if step_ids:
        connections[prev_id] = {
            "main": [
                [{"node": step_ids[0], "type": "main", "index": 0}]
            ]
        }
        # Chain steps in order.
        for i in range(len(step_ids) - 1):
            connections[step_ids[i]] = {
                "main": [
                    [{"node": step_ids[i + 1], "type": "main", "index": 0}]
                ]
            }
        last_step = step_ids[-1]
        # Last step -> success.
        connections[last_step] = {
            "main": [
                [{"node": success_node["id"], "type": "main", "index": 0}]
            ]
        }
    else:
        connections[prev_id] = {
            "main": [
                [{"node": success_node["id"], "type": "main", "index": 0}]
            ]
        }

    payload: dict[str, Any] = {
        "name": draft.name,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "meta": {
            "source_draft_id": draft.id,
            "source_workflow_spec_id": draft.source_workflow_spec_id,
            "runtime": "n8n",
        },
    }

    # The ONLY sanctioned path to set export_payload.
    draft.set_export_payload(payload)
    return payload
