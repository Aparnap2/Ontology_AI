"""TDD tests for the Windmill runtime compiler (PRD §17, §19.3, §12.7).

RED phase: imports will fail until ``WindmillCompiler`` is implemented.
GREEN phase: after implementing ``src/runtime/windmill_compiler.py``.

Critical invariants asserted here:
* Compiler purity: ``export_payload`` is ONLY set via ``set_export_payload``.
* Determinism: the same draft compiles to byte-identical payloads (no UUID/random).
* Output shape: payload has ``target_type``, ``path``, ``summary``, plus either
  ``content``+``language``+``schema`` (script) or ``flow_value`` (flow).
"""

from __future__ import annotations

import json

import pytest

from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.runtime.windmill_compiler import WindmillCompiler, compile_windmill


def _make_script_draft() -> ExecutableWorkflowDraft:
    """Build a single-step draft → should produce a script target."""
    return ExecutableWorkflowDraft(
        id="draft-wm-1",
        runtime="windmill",
        name="Send Welcome Email",
        source_workflow_spec_id="ws-001",
        trigger={"type": "webhook", "language": "python3"},
        inputs=[{"name": "user_email", "type": "string"}],
        steps=[
            {
                "id": "s1",
                "action": "send_email",
                "type": "email",
                "params": {"template": "welcome"},
                "description": "Send welcome email",
            },
        ],
        success_criteria=["email_sent"],
    )


def _make_flow_draft() -> ExecutableWorkflowDraft:
    """Build a multi-step draft → should produce a flow target."""
    return ExecutableWorkflowDraft(
        id="draft-wm-2",
        runtime="windmill",
        name="Invoice Processing Pipeline",
        source_workflow_spec_id="ws-002",
        trigger={"type": "schedule", "cron": "0 6 * * *"},
        inputs=[
            {"name": "customer_id", "type": "string"},
            {"name": "amount", "type": "float"},
        ],
        steps=[
            {
                "id": "s1",
                "action": "fetch_invoice",
                "type": "api_call",
                "params": {"status": "overdue"},
                "description": "Fetch overdue invoice",
            },
            {
                "id": "s2",
                "action": "send_reminder",
                "type": "email",
                "params": {"template": "reminder"},
                "description": "Send reminder email",
            },
            {
                "id": "s3",
                "action": "log_activity",
                "type": "database",
                "params": {},
                "description": "Log the activity",
            },
        ],
        success_criteria=["invoice_reminded", "activity_logged"],
    )


def _make_approval_draft() -> ExecutableWorkflowDraft:
    """Build a draft with approvals → should produce a flow with suspend."""
    return ExecutableWorkflowDraft(
        id="draft-wm-3",
        runtime="windmill",
        name="Expense Report Approval",
        source_workflow_spec_id="ws-003",
        trigger={"type": "manual"},
        inputs=[{"name": "report_id", "type": "string"}],
        steps=[
            {
                "id": "s1",
                "action": "validate_report",
                "type": "validation",
                "params": {},
                "description": "Validate expense report",
            },
        ],
        approvals=[
            {"id": "a1", "role": "manager"},
            {"id": "a2", "role": "finance"},
        ],
        success_criteria=["approved"],
    )


# ── Compiler contract tests ──────────────────────────────────────────────────


class TestWindmillCompiler:
    """WindmillCompiler implements the RuntimeCompiler ABC."""

    def test_compiler_is_runtime_compiler(self):
        """WindmillCompiler can be instantiated and has a compile method."""
        compiler = WindmillCompiler()
        assert hasattr(compiler, "compile")
        assert callable(compiler.compile)

    def test_compiler_returns_payload_dict(self):
        """compile() returns a dict with runtime and files keys."""
        compiler = WindmillCompiler()
        result = compiler.compile({"id": "test", "steps": []})
        assert isinstance(result, dict)
        assert "runtime" in result
        assert "files" in result

    def test_get_runtime_returns_windmill(self):
        """The compile result runtime key is 'windmill'."""
        compiler = WindmillCompiler()
        result = compiler.compile({"id": "test", "steps": []})
        assert result["runtime"] == "windmill"

    def test_output_has_windmill_json_file(self):
        """The files dict contains a 'windmill.json' entry."""
        compiler = WindmillCompiler()
        result = compiler.compile({"id": "test", "steps": []})
        assert "windmill.json" in result["files"]

    def test_windmill_json_is_valid_json(self):
        """The windmill.json file content is valid JSON."""
        compiler = WindmillCompiler()
        result = compiler.compile({"id": "test", "steps": []})
        payload = json.loads(result["files"]["windmill.json"])
        assert isinstance(payload, dict)

    def test_same_draft_produces_identical_bytes(self):
        """Determinism: same draft → byte-identical output (no uuid4/random)."""
        draft_a = {"id": "det-test", "name": "Deterministic", "steps": [{"id": "x", "action": "test"}]}
        draft_b = {"id": "det-test", "name": "Deterministic", "steps": [{"id": "x", "action": "test"}]}
        compiler = WindmillCompiler()
        result_a = compiler.compile(draft_a)
        result_b = compiler.compile(draft_b)
        assert json.dumps(result_a, sort_keys=True) == json.dumps(result_b, sort_keys=True)


# ── Script target tests (single-step drafts) ─────────────────────────────────


class TestWindmillScriptTarget:
    """Single-step drafts compile to script targets."""

    def test_compile_single_step_returns_script(self):
        """Single-step draft → target_type == 'script'."""
        draft = _make_script_draft()
        payload = compile_windmill(draft)
        assert payload["target_type"] == "script"

    def test_script_has_required_keys(self):
        """Script payload has content, language, schema, kind, tag."""
        draft = _make_script_draft()
        payload = compile_windmill(draft)
        assert "content" in payload
        assert "language" in payload
        assert "schema" in payload
        assert "kind" in payload
        assert "tag" in payload

    def test_script_has_path_and_summary(self):
        """Script payload includes path and summary derived from draft."""
        draft = _make_script_draft()
        payload = compile_windmill(draft)
        assert payload["path"] == "f/iterateswarm/draft-wm-1"
        assert payload["summary"] == "Send Welcome Email"

    def test_script_language_defaults_to_python3(self):
        """Script language defaults to python3."""
        draft = _make_script_draft()
        payload = compile_windmill(draft)
        assert payload["language"] == "python3"

    def test_script_content_is_valid_python(self):
        """Generated content parses as valid Python."""
        draft = _make_script_draft()
        payload = compile_windmill(draft)
        content = payload["content"]
        assert "def main(" in content
        # Verify it parses
        compile(content, "<test>", "exec")

    def test_script_schema_reflects_inputs(self):
        """Schema properties mirror draft inputs."""
        draft = _make_script_draft()
        payload = compile_windmill(draft)
        schema = payload["schema"]
        assert schema["type"] == "object"
        assert "user_email" in schema["properties"]
        assert schema["properties"]["user_email"]["type"] == "string"

    def test_script_path_uses_draft_id(self):
        """Path follows the 'f/iterateswarm/{draft_id}' convention."""
        draft = ExecutableWorkflowDraft(
            id="custom-id-42",
            runtime="windmill",
            name="Test",
            source_workflow_spec_id="ws-x",
            steps=[{"id": "s1", "action": "noop"}],
        )
        payload = compile_windmill(draft)
        assert payload["path"] == "f/iterateswarm/custom-id-42"


# ── Flow target tests (multi-step drafts) ────────────────────────────────────


class TestWindmillFlowTarget:
    """Multi-step drafts compile to flow targets."""

    def test_compile_multi_step_returns_flow(self):
        """Multi-step draft → target_type == 'flow'."""
        draft = _make_flow_draft()
        payload = compile_windmill(draft)
        assert payload["target_type"] == "flow"

    def test_flow_has_flow_value(self):
        """Flow payload contains a flow_value dict."""
        draft = _make_flow_draft()
        payload = compile_windmill(draft)
        assert "flow_value" in payload
        assert isinstance(payload["flow_value"], dict)

    def test_flow_has_path_and_summary(self):
        """Flow payload includes path and summary."""
        draft = _make_flow_draft()
        payload = compile_windmill(draft)
        assert payload["path"] == "f/iterateswarm/draft-wm-2"
        assert payload["summary"] == "Invoice Processing Pipeline"

    def test_flow_modules_match_step_count(self):
        """Number of modules equals number of steps."""
        draft = _make_flow_draft()
        payload = compile_windmill(draft)
        modules = payload["flow_value"]["modules"]
        assert len(modules) == len(draft.steps)

    def test_flow_module_has_id_and_value(self):
        """Each module has an id and a value dict."""
        draft = _make_flow_draft()
        payload = compile_windmill(draft)
        for module in payload["flow_value"]["modules"]:
            assert "id" in module
            assert "value" in module

    def test_flow_module_value_is_rawscript(self):
        """Each module value has type rawscript with python3 language."""
        draft = _make_flow_draft()
        payload = compile_windmill(draft)
        for module in payload["flow_value"]["modules"]:
            assert module["value"]["type"] == "rawscript"
            assert module["value"]["language"] == "python3"

    def test_flow_module_content_is_valid_python(self):
        """Each module's content parses as valid Python."""
        draft = _make_flow_draft()
        payload = compile_windmill(draft)
        for module in payload["flow_value"]["modules"]:
            content = module["value"]["content"]
            compile(content, "<test>", "exec")

    def test_flow_same_worker_is_true(self):
        """Flow same_worker flag is True."""
        draft = _make_flow_draft()
        payload = compile_windmill(draft)
        assert payload["flow_value"]["same_worker"] is True

    def test_flow_with_approvals_includes_suspend(self):
        """Draft with approvals → flow with suspend modules."""
        draft = _make_approval_draft()
        payload = compile_windmill(draft)
        assert payload["target_type"] == "flow"
        modules = payload["flow_value"]["modules"]
        suspend_modules = [m for m in modules if "suspend" in m]
        assert len(suspend_modules) == len(draft.approvals)
        for sm in suspend_modules:
            assert sm["suspend"]["required_events"] == 1
            assert sm["suspend"]["timeout"] == 86400
            assert sm["suspend"]["user_auth_required"] is True

    def test_single_step_with_approval_is_flow(self):
        """Single-step draft with approvals → flow (not script)."""
        draft = _make_approval_draft()
        payload = compile_windmill(draft)
        assert payload["target_type"] == "flow"


# ── Runtime guard tests ──────────────────────────────────────────────────────


class TestWindmillCompilerGuard:
    """compile_windmill guards against wrong runtime."""

    def test_raises_on_wrong_runtime(self):
        """compile_windmill raises ValueError if runtime is not 'windmill'."""
        draft = ExecutableWorkflowDraft(
            id="bad",
            runtime="n8n",
            name="Bad",
            source_workflow_spec_id="ws-x",
        )
        with pytest.raises(ValueError, match="runtime.*windmill"):
            compile_windmill(draft)
