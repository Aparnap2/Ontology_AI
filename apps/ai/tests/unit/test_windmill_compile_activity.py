"""Tests for compile_windmill_workflow Temporal activity.

Verifies that the activity correctly compiles a workflow and deploys it
to Windmill, returning a success/error result dict.

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run python -m pytest tests/unit/test_windmill_compile_activity.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_compile_windmill() -> MagicMock:
    """Mock the windmill_compiler.compile_windmill function."""
    with patch(
        "src.activities.compile_windmill_workflow.compile_windmill"
    ) as mock:
        mock.return_value = {
            "target_type": "script",
            "path": "f/iterateswarm/test-script",
            "summary": "Test script",
            "content": "def main():\n    pass\n",
            "language": "python3",
            "kind": "script",
            "tag": "default",
            "schema": {"type": "object", "properties": {}},
        }
        yield mock


@pytest.fixture
def mock_windmill_client() -> MagicMock:
    """Mock the windmill_client module."""
    with patch(
        "src.activities.compile_windmill_workflow.windmill_client"
    ) as mock:
        mock.create_script.return_value = {
            "id": "wm-script-123",
            "path": "f/iterateswarm/test-script",
            "workspace": "iterateswarm",
        }
        mock.create_flow.return_value = {
            "id": "wm-flow-456",
            "path": "f/iterateswarm/test-flow",
            "workspace": "iterateswarm",
        }
        yield mock


class TestWindmillCompileActivity:
    """Tests for the compile_windmill_workflow Temporal activity."""

    def test_activity_exists(self):
        """The activity function is importable and has the expected name."""
        from src.activities.compile_windmill_workflow import (
            compile_windmill_workflow,
        )

        assert compile_windmill_workflow is not None
        assert callable(compile_windmill_workflow)

    def test_compile_script_returns_success(
        self,
        mock_compile_windmill: MagicMock,
        mock_windmill_client: MagicMock,
    ):
        """Compiling a single-step workflow returns success with deployment URL."""
        from src.activities.compile_windmill_workflow import (
            compile_windmill_workflow,
        )

        result = compile_windmill_workflow(
            workflow_name="test-script",
            script_content="print('hello')",
            env_vars={"API_KEY": "test"},
        )

        assert result["success"] is True
        assert "deployment_url" in result
        assert "f/iterateswarm/test-script" in result["deployment_url"]
        assert result["workflow_name"] == "test-script"
        assert mock_compile_windmill.called

    def test_compile_script_sets_runtime_windmill(
        self,
        mock_compile_windmill: MagicMock,
        mock_windmill_client: MagicMock,
    ):
        """The draft passed to compile_windmill must have runtime='windmill'."""
        from src.activities.compile_windmill_workflow import (
            compile_windmill_workflow,
        )

        compile_windmill_workflow(
            workflow_name="test-script",
            script_content="print('hello')",
            env_vars={"KEY": "val"},
        )

        # Extract the draft argument passed to compile_windmill
        call_draft = mock_compile_windmill.call_args[0][0]
        assert call_draft.runtime == "windmill"

    @pytest.mark.parametrize(
        "error_side_effect,expected_error",
        [
            (ValueError("compile failed"), "compile failed"),
            (RuntimeError("API timeout"), "API timeout"),
            (OSError("connection refused"), "connection refused"),
        ],
    )
    def test_compile_returns_error_on_failure(
        self,
        error_side_effect: Exception,
        expected_error: str,
        mock_compile_windmill: MagicMock,
    ):
        """When compilation fails, the activity returns an error result dict."""
        mock_compile_windmill.side_effect = error_side_effect

        from src.activities.compile_windmill_workflow import (
            compile_windmill_workflow,
        )

        result = compile_windmill_workflow(
            workflow_name="failing-script",
            script_content="invalid content",
            env_vars={},
        )

        assert result["success"] is False
        assert "error" in result
        assert expected_error in result["error"]
        assert result["workflow_name"] == "failing-script"

    def test_activity_has_defn_decorator(self):
        """The activity function must be decorated with @activity.defn."""
        import inspect

        from src.activities.compile_windmill_workflow import (
            compile_windmill_workflow,
        )

        source = inspect.getsource(compile_windmill_workflow)
        # The decorator should be present in the source or the function
        # should have the __temporal_activity_definition attribute
        assert hasattr(
            compile_windmill_workflow, "__temporal_activity_definition"
        ) or "@activity.defn" in source
