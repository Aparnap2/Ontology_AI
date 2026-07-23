"""OntologyAI V5.1 — Windmill runtime compiler (PRD §17, §12.7).

Deterministically transforms an :class:`ExecutableWorkflowDraft` into a
Windmill-compatible payload supporting two target types:

* **Script** (single-step) — a standalone Python function uploaded as a script.
* **Flow** (multi-step / approval) — a multi-module workflow with optional
  human-in-the-loop suspension.

Windmill API docs: https://docs.windmill.dev/

Determinism
-----------
* Script/flow paths are derived from the draft id, not random UUIDs.
* Module ids are ordered ``"step_{index}"`` indices.
* No ``uuid`` / ``random`` module is imported or used anywhere in this file.
"""

from __future__ import annotations

import json
from typing import Any

from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.runtime.base import RuntimeCompiler

# ── Helpers ──────────────────────────────────────────────────────────────────


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
        runtime="windmill",
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


def _inputs_to_schema(inputs: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert draft inputs to a JSON Schema object.

    Maps each input's ``type`` string to a JSON Schema type and builds a
    ``{"type": "object", "properties": {...}}`` schema.
    """
    _TYPE_MAP: dict[str, str] = {
        "string": "string",
        "integer": "integer",
        "float": "number",
        "boolean": "boolean",
        "dict": "object",
        "list": "array",
        "any": "string",
    }
    properties: dict[str, dict[str, str]] = {}
    for inp in inputs:
        name = inp.get("name", "")
        if not name:
            continue
        raw_type = inp.get("type", "string")
        js_type = _TYPE_MAP.get(str(raw_type).lower(), "string")
        properties[name] = {"type": js_type}

    return {
        "type": "object",
        "properties": properties,
    }


def _generate_script_body(draft: ExecutableWorkflowDraft) -> str:
    """Generate a Python ``def main(...)`` body executing all steps.

    For a single-step draft this produces a compact function that runs the
    step and returns the result.
    """
    lines: list[str] = [
        '"""Auto-generated Windmill script — OntologyAI V5.1."""',
        "from __future__ import annotations",
        "",
    ]

    # Build parameter list from draft inputs.
    param_names: list[str] = []
    for inp in draft.inputs:
        param_names.append(str(inp.get("name", "")))
    params = ", ".join(param for param in param_names if param)

    lines.append(f"def main({params}):")
    lines.append('    """Execute the workflow steps."""')

    for i, step in enumerate(draft.steps, start=1):
        step_id = step.get("id", f"step_{i}")
        desc = step.get("description", step_id)
        lines.append(f"    # Step {i}: {desc}")
        lines.append(f"    print(f'Executing step {{step_id}}')")

    # Return a summary result dict.
    if draft.success_criteria:
        lines.append(
            f"    return {{'status': 'completed', "
            f"'steps_executed': {len(draft.steps)}, "
            f"'success_criteria': {json.dumps(list(draft.success_criteria))}}}"
        )
    else:
        lines.append(
            f"    return {{'status': 'completed', "
            f"'steps_executed': {len(draft.steps)}}}"
        )

    return "\n".join(lines)


def _generate_flow_module(
    step: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    """Build a single flow module dict for a Windmill flow value.

    Each step becomes a ``rawscript`` module with its own ``def main():``.
    """
    step_id = step.get("id", f"step_{index}")
    desc = step.get("description", step_id)
    action = step.get("action", step.get("type", "unknown"))

    content = (
        f'"""Step {index}: {desc}."""\n'
        "from __future__ import annotations\n"
        "\n"
        "\n"
        "def main():\n"
        f'    """{desc}."""\n'
        f'    result = f"Executed: {action}"\n'
        f"    print(result)\n"
        f'    return {{"step_id": "{step_id}", "status": "completed"}}\n'
    )

    module: dict[str, Any] = {
        "id": step_id,
        "value": {
            "type": "rawscript",
            "language": "python3",
            "content": content,
        },
    }

    return module


def _build_flow_value(draft: ExecutableWorkflowDraft) -> dict[str, Any]:
    """Build the ``flow_value`` dict for a multi-step Windmill flow.

    Includes optiona: supend module when the draft has approval items.
    """
    modules: list[dict[str, Any]] = []

    # Generate a module per step.
    for i, step in enumerate(draft.steps, start=1):
        module = _generate_flow_module(step, i)

        # Add input transforms mapping flow inputs to module params.
        if draft.inputs:
            transforms: dict[str, dict[str, str]] = {}
            for inp in draft.inputs:
                name = str(inp.get("name", ""))
                if name:
                    transforms[name] = {
                        "type": "raw",
                        "expr": f"flow_input.{name}",
                    }
            if transforms:
                module["value"]["input_transforms"] = transforms

        modules.append(module)

    # Insert a suspend module for approval items.
    if draft.approvals:
        for ap in draft.approvals:
            ap_id = ap.get("id", f"approval_{len(modules) + 1}")
            modules.append({
                "id": ap_id,
                "suspend": {
                    "required_events": 1,
                    "timeout": 86400,
                    "user_auth_required": True,
                },
            })

    return {
        "modules": modules,
        "same_worker": True,
    }


# ── Public compile function ──────────────────────────────────────────────────


def compile_windmill(draft: ExecutableWorkflowDraft) -> dict[str, Any]:
    """Compile ``draft`` into a Windmill-compatible payload.

    Determines target type automatically:
    * Single-step drafts → ``"script"`` target (standalone Python function).
    * Multi-step drafts → ``"flow"`` target (multi-module workflow).
    * Drafts with approvals → always ``"flow"`` target with a suspend module.

    Args:
        draft: The executable workflow draft to compile. Must have
            ``runtime == "windmill"``.

    Returns:
        A Windmill-shaped payload dict with keys: ``target_type``, ``path``,
        ``summary``, and either ``content``+``language``+``schema`` (for scripts)
        or ``flow_value`` (for flows).

    Raises:
        ValueError: If ``draft.runtime`` is not ``"windmill"``.
    """
    if draft.runtime != "windmill":
        raise ValueError(
            f"compile_windmill requires runtime='windmill', got {draft.runtime!r}"
        )

    draft_id = draft.id
    path = f"f/iterateswarm/{draft_id}"
    summary = draft.name
    language = draft.trigger.get("language", "python3") if draft.trigger else "python3"

    # Determine target type based on steps and approvals.
    has_multi_step = len(draft.steps) > 1
    has_approvals = len(draft.approvals) > 0

    if has_multi_step or has_approvals:
        # ── Flow target ───────────────────────────────────────────────────
        return {
            "target_type": "flow",
            "path": path,
            "summary": summary,
            "flow_value": _build_flow_value(draft),
        }
    else:
        # ── Script target ─────────────────────────────────────────────────
        content = _generate_script_body(draft)
        schema = _inputs_to_schema(draft.inputs)

        return {
            "target_type": "script",
            "path": path,
            "summary": summary,
            "content": content,
            "language": language,
            "kind": "script",
            "tag": "default",
            "schema": schema,
        }


# ── Class-based compiler (RuntimeCompiler ABC) ──────────────────────────────


class WindmillCompiler(RuntimeCompiler):
    """Compiler targeting the Windmill workflow runtime.

    Converts a workflow draft dict into a Windmill-compatible payload stored
    as ``windmill.json`` in the output ``files`` dict.
    """

    def compile(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Compile a draft dict into a Windmill-shaped payload.

        Returns:
            Dict with ``runtime="windmill"`` and ``files`` containing
            ``windmill.json`` (serialised Windmill payload).
        """
        draft_obj = _dict_to_draft(draft)
        payload = compile_windmill(draft_obj)
        return {
            "runtime": "windmill",
            "files": {
                "windmill.json": json.dumps(payload, indent=2),
            },
        }
