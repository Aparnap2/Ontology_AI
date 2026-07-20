"""TDD tests for OntologyAI V5.1 runtime deployers.

RED phase: these imports will fail until src/runtime/deployers.py exists.
GREEN phase: after implementing deployers module.

Tests:
- deploy_to_n8n validates credentials before calling n8n_client
- deploy_custom_agent packages artifact bundles
- DeployerResult dataclass behaves correctly
"""

from __future__ import annotations

import httpx
import pytest

# These imports will fail in RED phase — that is the expected behaviour.
from src.runtime.deployers import (
    DeployerResult,
    deploy_to_n8n,
    deploy_custom_agent,
)


def _mock_client(json_body: dict, status: int = 200) -> httpx.Client:
    """Return an httpx.Client with mock transport (no real network)."""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(status, json=json_body)
    )
    return httpx.Client(transport=transport, verify=False)


class TestDeployerResult:
    """DeployerResult dataclass tests."""

    def test_minimal_result(self):
        """Can create a DeployerResult with just success and runtime."""
        r = DeployerResult(success=True, runtime="n8n")
        assert r.success is True
        assert r.runtime == "n8n"
        assert r.workflow_id is None
        assert r.export_url is None
        assert r.files == {}
        assert r.error is None

    def test_result_with_all_fields(self):
        """Can create a fully populated DeployerResult."""
        r = DeployerResult(
            success=True,
            runtime="custom_agent",
            workflow_id="wf-123",
            export_url="http://export/123",
            files={"config.json": "{}"},
            error=None,
        )
        assert r.workflow_id == "wf-123"
        assert r.export_url == "http://export/123"
        assert r.files == {"config.json": "{}"}

    def test_result_with_error(self):
        """Failure result carries an error message."""
        r = DeployerResult(success=False, runtime="n8n", error="API unreachable")
        assert r.success is False
        assert r.error == "API unreachable"


class TestN8NDeployer:
    """deploy_to_n8n credential validation tests.

    These are pure-unit tests — they do NOT require a running n8n instance.
    The mock-level tests for n8n_client.create_workflow already exist in
    test_n8n_client.py; here we only validate that the deployer guards its
    preconditions before calling out.
    """

    def test_deploy_raises_without_credentials(self):
        """deploy_to_n8n must raise ValueError when credentials dict is empty."""
        with pytest.raises(ValueError, match="credentials|required"):
            deploy_to_n8n({"name": "test"}, {})

    def test_deploy_raises_without_api_key(self):
        """deploy_to_n8n must raise ValueError when api_key is missing."""
        with pytest.raises(ValueError, match="api_key|required"):
            deploy_to_n8n(
                {"name": "test"}, {"url": "http://localhost:5678"}
            )

    def test_deploy_raises_without_url(self):
        """deploy_to_n8n must raise ValueError when url is missing."""
        with pytest.raises(ValueError, match="url|required"):
            deploy_to_n8n(
                {"name": "test"}, {"api_key": "test-key"}
            )

    def test_deploy_returns_result_on_success(self):
        """With valid credentials + mock transport, returns a DeployerResult."""
        client = _mock_client({"id": "wf-999"})
        result = deploy_to_n8n(
            {"name": "test", "nodes": [], "connections": {}},
            {"url": "http://n8n:5678/api/v1", "api_key": "test-key-123", "client": client},
        )
        assert isinstance(result, DeployerResult)
        assert result.runtime == "n8n"
        assert result.success is True

    def test_deploy_result_has_workflow_id(self):
        """Successful deploy returns a workflow_id."""
        client = _mock_client({"id": "wf-999"})
        result = deploy_to_n8n(
            {"name": "test", "nodes": [], "connections": {}},
            {"url": "http://n8n:5678/api/v1", "api_key": "test-key-123", "client": client},
        )
        assert result.workflow_id == "wf-999"

    def test_deploy_fails_on_api_error(self):
        """When n8n returns an error, deploy returns success=False."""
        client = _mock_client({"message": "bad request"}, status=400)
        result = deploy_to_n8n(
            {"name": "test", "nodes": [], "connections": {}},
            {"url": "http://n8n:5678/api/v1", "api_key": "bad-key", "client": client},
        )
        assert isinstance(result, DeployerResult)
        assert result.success is False
        assert result.error is not None


class TestCustomAgentDeployer:
    """deploy_custom_agent tests."""

    def test_returns_artifact_bundle(self):
        """deploy_custom_agent returns a DeployerResult with files."""
        result = deploy_custom_agent(
            {"name": "test-agent", "steps": []},
            {"tenant_id": "test"},
        )
        assert isinstance(result, DeployerResult)
        assert result.runtime == "custom_agent"
        assert isinstance(result.files, dict)

    def test_artifact_has_expected_files(self):
        """The artifact bundle contains expected files."""
        result = deploy_custom_agent(
            {
                "name": "test-agent",
                "steps": [{"id": "s1", "action": "greet"}],
            },
            {"tenant_id": "test"},
        )
        expected_files = {"config.json", "instructions.txt"}
        assert expected_files.issubset(result.files.keys())

    def test_result_indicates_success(self):
        """Successful deploy returns success=True."""
        result = deploy_custom_agent(
            {"name": "test-agent", "steps": []},
            {"tenant_id": "test"},
        )
        assert result.success is True

    def test_files_contain_meaningful_content(self):
        """Generated files have valid content."""
        result = deploy_custom_agent(
            {
                "name": "my-agent",
                "steps": [
                    {"id": "s1", "action": "fetch_data"},
                    {"id": "s2", "action": "analyze"},
                ],
            },
            {"tenant_id": "t1"},
        )
        config = result.files["config.json"]
        assert "my-agent" in config
        assert "custom_agent" in config
        instructions = result.files["instructions.txt"]
        assert "fetch_data" in instructions
        assert "analyze" in instructions
