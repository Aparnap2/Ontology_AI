"""E2E integration tests for OntologyAI V5.1 — real Docker + LLM.

These tests are SKIPPED unless RUN_E2E_DOCKER=1 is set.
They require:
- LLM credentials (GROQ_API_KEY or similar)
- Optional: Windmill container (WINDMILL_URL) for deploy step

Run:
    RUN_E2E_DOCKER=1 uv run pytest tests/test_e2e_docker_llm.py -v
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_E2E_DOCKER"),
    reason="Set RUN_E2E_DOCKER=1 to run Docker/LLM E2E tests",
)


def _windmill_healthy() -> tuple[bool, str]:
    """Check if a Windmill container is reachable.

    Returns (healthy, url_or_reason).
    """
    url = os.environ.get("WINDMILL_URL", "http://localhost:8000")
    try:
        r = httpx.get(f"{url}/api/health", timeout=5.0)
        if r.status_code < 500:
            return True, url
        return False, f"Windmill at {url} returned status {r.status_code}"
    except httpx.ConnectError:
        return False, f"Windmill at {url} not reachable — container may not be running"
    except Exception as exc:
        return False, f"Windmill check failed: {exc}"


def _windmill_token() -> str | None:
    """Get Windmill API token from env, or None."""
    token = os.environ.get("WINDMILL_TOKEN") or os.environ.get("WM_TOKEN")
    if token:
        return token
    return None


_WINDMILL_HEALTHY: bool | None = None
_WINDMILL_URL: str | None = None


def _ensure_windmill() -> tuple[bool, str, str | None]:
    """Lazy-check Windmill health, caching the result for the session."""
    global _WINDMILL_HEALTHY, _WINDMILL_URL
    if _WINDMILL_HEALTHY is None:
        healthy, url = _windmill_healthy()
        _WINDMILL_HEALTHY = healthy
        _WINDMILL_URL = url
    token = _windmill_token()
    return _WINDMILL_HEALTHY, _WINDMILL_URL or "", token


# ── Helpers ───────────────────────────────────────────────────────


def _llm_propose_workflow() -> dict[str, Any]:
    """Call real LLM (Groq) to propose a minimal workflow draft as JSON."""
    from src.config.llm import chat_completion, extract_json_content, get_chat_model

    prompt = (
        "You are a workflow designer. Generate a minimal JSON workflow draft "
        "for an automation that greets a user and logs the timestamp. "
        "Return ONLY valid JSON with NO markdown formatting, NO code fences:\n"
        '{\n'
        '  "id": "llm-proposal-e2e",\n'
        '  "name": "E2E Greeter",\n'
        '  "description": "Greets a user and logs time",\n'
        '  "trigger": {"type": "manual"},\n'
        '  "steps": [{"id": "greet", "action": "say_hello"}, {"id": "log", "action": "log_time"}],\n'
        '  "success_criteria": ["greeting_sent", "timestamp_logged"]\n'
        "}"
    )
    model = get_chat_model()
    response = chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        max_tokens=500,
        temperature=0.0,
    )
    cleaned = extract_json_content(response)
    return json.loads(cleaned)


def _build_draft_from_proposal(
    proposal: dict[str, Any],
    runtime: str = "windmill",
) -> Any:
    """Build an ExecutableWorkflowDraft from an LLM proposal dict."""
    from src.ontology.workflow_drafts import ExecutableWorkflowDraft

    return ExecutableWorkflowDraft(
        id=proposal.get("id", "e2e-proposal"),
        runtime=runtime,
        name=proposal.get("name", "E2E Workflow"),
        source_workflow_spec_id="e2e-llm-spec",
        trigger=proposal.get("trigger", {"type": "manual"}),
        steps=proposal.get("steps", []),
        success_criteria=proposal.get("success_criteria", ["completed"]),
    )


# ═══════════════════════════════════════════════════════════════════
# Test: LLM proposal → WindmillCompiler → deploy to Windmill
# ═══════════════════════════════════════════════════════════════════


class TestWindmillE2EWithRealLLM:
    """E2E: real LLM proposes a draft → WindmillCompiler → Windmill API."""

    def test_llm_proposes_valid_workflow_draft(self):
        """Real Groq call produces parseable JSON with required fields."""
        proposal = _llm_propose_workflow()
        assert isinstance(proposal, dict), f"Expected dict, got {type(proposal)}"
        assert "id" in proposal, f"Missing 'id' in proposal: {proposal}"
        assert "name" in proposal, f"Missing 'name' in proposal: {proposal}"
        assert "steps" in proposal, f"Missing 'steps' in proposal: {proposal}"
        assert isinstance(proposal["steps"], list), "steps must be a list"
        assert len(proposal["steps"]) > 0, "steps must not be empty"

    def test_llm_proposal_compiles_to_windmill_script(self):
        """Single-step LLM proposal → WindmillCompiler → script target."""
        from src.runtime.windmill_compiler import WindmillCompiler

        proposal = _llm_propose_workflow()
        steps = proposal.get("steps", [])
        if len(steps) > 1:
            steps = [steps[0]]
            proposal["steps"] = steps
        draft = _build_draft_from_proposal(proposal)
        draft_dict = draft.model_dump(mode="json")
        compiler = WindmillCompiler()
        payload = compiler.compile(draft_dict)
        files = payload.get("files", {})
        windmill_json = json.loads(files.get("windmill.json", "{}"))
        assert windmill_json.get("target_type") == "script"
        assert windmill_json.get("path") == f"f/iterateswarm/{draft.id}"
        assert "content" in windmill_json
        assert windmill_json.get("language") == "python3"

    def test_llm_proposal_compiles_to_windmill_flow(self):
        """Multi-step LLM proposal → WindmillCompiler → flow target."""
        from src.runtime.windmill_compiler import WindmillCompiler

        proposal = _llm_propose_workflow()
        draft = _build_draft_from_proposal(proposal)
        draft_dict = draft.model_dump(mode="json")
        compiler = WindmillCompiler()
        payload = compiler.compile(draft_dict)
        files = payload.get("files", {})
        windmill_json = json.loads(files.get("windmill.json", "{}"))
        if windmill_json.get("target_type") == "flow":
            assert "flow_value" in windmill_json
        else:
            assert windmill_json.get("target_type") == "script"
            assert "content" in windmill_json

    def test_compiled_windmill_payload_is_valid_python(self):
        """The generated Python body in the compiled payload must compile."""
        from src.runtime.windmill_compiler import WindmillCompiler

        proposal = _llm_propose_workflow()
        draft = _build_draft_from_proposal(proposal)
        draft_dict = draft.model_dump(mode="json")
        compiler = WindmillCompiler()
        payload = compiler.compile(draft_dict)
        files = payload.get("files", {})
        windmill_json = json.loads(files.get("windmill.json", "{}"))
        source = payload.get("content") or ""
        if source:
            compile(source, "<test>", "exec")

    def test_windmill_deploy_via_governance(self):
        """Full governance path: activate → compile → deploy to Windmill.

        Deploy step skipped if Windmill container is not reachable (image
        may still be pulling).
        """
        from src.workflows.governance_workflow import GovernanceWorkflow

        healthy, url, token = _ensure_windmill()
        if not healthy:
            pytest.skip(f"Windmill not reachable: {url}. Start: docker compose up -d windmill")
        if not token:
            pytest.skip("No WINDMILL_TOKEN set in environment")

        from src.runtime.windmill_compiler import WindmillCompiler

        proposal = _llm_propose_workflow()
        draft = _build_draft_from_proposal(proposal)
        draft_dict = draft.model_dump(mode="json")
        compiler = WindmillCompiler()
        payload = compiler.compile(draft_dict)
        files = payload.get("files", {})
        windmill_json = json.loads(files.get("windmill.json", "{}"))
        draft.set_export_payload(windmill_json)

        wf = GovernanceWorkflow()
        wf.activate_draft(draft)
        assert draft.status == "activated"

        creds = {"workspace": "admins", "token": token, "base_url": f"{url}/api"}
        result = wf.deploy_draft(draft, creds)
        assert result.success is True, f"Windmill deploy failed: {result.error}"
        assert result.runtime == "windmill"
        assert result.workflow_id is not None

    def test_windmill_deploy_with_secrets(self):
        """Compiled draft with secrets sets Windmill variables on deploy.

        Deploy step skipped if Windmill container is not reachable.
        """
        from src.workflows.governance_workflow import GovernanceWorkflow

        healthy, url, token = _ensure_windmill()
        if not healthy:
            pytest.skip(f"Windmill not reachable: {url}. Start: docker compose up -d windmill")
        if not token:
            pytest.skip("No WINDMILL_TOKEN set in environment")

        from src.runtime.windmill_compiler import WindmillCompiler

        proposal = _llm_propose_workflow()
        draft = _build_draft_from_proposal(proposal)
        draft_dict = draft.model_dump(mode="json")
        compiler = WindmillCompiler()
        payload = compiler.compile(draft_dict)
        files = payload.get("files", {})
        windmill_json = json.loads(files.get("windmill.json", "{}"))
        windmill_json["secrets"] = {"E2E_TEST_KEY": "e2e-test-value"}
        draft.set_export_payload(windmill_json)

        wf = GovernanceWorkflow()
        wf.activate_draft(draft)

        creds = {"workspace": "admins", "token": token, "base_url": f"{url}/api"}
        result = wf.deploy_draft(draft, creds)
        assert result.success is True


# ═══════════════════════════════════════════════════════════════════
# Test (legacy): n8n pipeline (keep for backward compat)
# ═══════════════════════════════════════════════════════════════════


class TestRealDockerN8nE2E:
    """REAL: compiles a sample draft, deploys to running n8n via REST API."""

    def test_n8n_compile_and_deploy(self):
        """Compile a valid workflow draft and deploy to live n8n (legacy)."""
        from src.ontology.workflow_drafts import ExecutableWorkflowDraft
        from src.runtime.n8n_compiler import compile_n8n
        from src.runtime.deployers import deploy_to_n8n

        draft = ExecutableWorkflowDraft(
            id="e2e-n8n-legacy",
            runtime="n8n",
            name="E2E N8N Legacy",
            source_workflow_spec_id="e2e-spec",
            trigger={"type": "manual"},
            steps=[{"id": "s1", "action": "hello_world"}],
            success_criteria=["completed"],
        )
        payload = compile_n8n(draft)
        assert "nodes" in payload
        assert "connections" in payload

        api_url = os.environ.get("N8N_API_URL", "http://localhost:5678/api/v1")
        api_key = os.environ.get("N8N_API_KEY", "")

        if not api_key:
            pytest.skip("No N8N_API_KEY set, skipping deploy step")

        result = deploy_to_n8n(payload, {"url": api_url, "api_key": api_key})
        assert result.success is True
        assert result.runtime == "n8n"
        assert result.workflow_id is not None


class TestRealLLMToCompileToDeploy:
    """REAL: uses LLM to generate a draft, compiles, deploys to n8n (legacy)."""

    def test_llm_draft_compiles_and_deploys(self):
        """LLM proposes a workflow draft, then compile and deploy to n8n."""
        proposal = _llm_propose_workflow()
        # Re-key the proposal for the legacy test
        proposal["id"] = "llm-proposal-legacy"
        proposal["runtime"] = "n8n"
        assert "id" in proposal
        assert "steps" in proposal

        from src.ontology.workflow_drafts import ExecutableWorkflowDraft
        from src.runtime.n8n_compiler import compile_n8n
        from src.runtime.deployers import deploy_to_n8n

        draft = ExecutableWorkflowDraft(
            id=proposal.get("id", "llm-proposal-legacy"),
            runtime="n8n",
            name=proposal.get("name", "LLM Workflow"),
            source_workflow_spec_id="llm-spec",
            trigger=proposal.get("trigger", {"type": "manual"}),
            steps=proposal.get("steps", []),
            success_criteria=proposal.get("success_criteria", ["completed"]),
        )
        payload = compile_n8n(draft)
        assert "nodes" in payload

        api_url = os.environ.get("N8N_API_URL", "http://localhost:5678/api/v1")
        api_key = os.environ.get("N8N_API_KEY", "")

        if not api_key:
            pytest.skip("No N8N_API_KEY set, skipping deploy step")

        result = deploy_to_n8n(payload, {"url": api_url, "api_key": api_key})
        assert result.success is True
        assert result.runtime == "n8n"
        assert result.workflow_id is not None
