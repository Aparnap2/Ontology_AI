"""TDD tests for the V5.1 multi-runtime compiler architecture.

RED phase: these imports will fail until compilers are implemented.
GREEN phase: after implementing src/runtime/{base,n8n,adk_go,pydantic_ai,python_agent}.py

Tests:
- RuntimeCompiler ABC enforces contract
- N8NCompiler wraps existing deterministic compile_n8n
- ADKGoCompiler produces valid Go source code
- PydanticAICompiler produces valid Python with Pydantic models + tool decorators
- PythonAgentCompiler produces smolagents-style CodeAgent
- RuntimeFactory routes correct compiler by name
"""

from __future__ import annotations

import ast
import json
import textwrap
from typing import Any, Dict

import pytest

# These imports will fail in RED phase — that's the expected behaviour.
from src.runtime import (
    RuntimeCompiler,
    N8NCompiler,
    ADKGoCompiler,
    PydanticAICompiler,
    PythonAgentCompiler,
    get_compiler,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def sample_draft() -> dict:
    """Return a realistic minimal workflow draft dict (canonical test fixture).

    Used by ALL compiler tests so that outputs are comparable across runtimes.
    """
    return {
        "tenant_id": "test_tenant",
        "mission_id": "test_mission",
        "trigger": "new_support_ticket",
        "inputs": {"ticket_id": "string", "priority": "integer"},
        "outputs": {"resolution": "string", "escalated": "boolean"},
        "steps": [
            {
                "id": "s1",
                "type": "classify_ticket",
                "params": {"model": "fast"},
                "description": "Classify the ticket",
            },
            {
                "id": "s2",
                "type": "route_to_team",
                "params": {"team_field": "priority"},
                "description": "Route by priority",
            },
        ],
        "side_effects": [
            {
                "id": "e1",
                "type": "slack_notify",
                "params": {"channel": "#support"},
                "description": "Notify support channel",
            },
            {
                "id": "e2",
                "type": "update_ticket",
                "params": {"status": "in_progress"},
                "description": "Update ticket status",
            },
        ],
        "success_criteria": {
            "metric": "response_time",
            "target": "5m",
            "weight": 1.0,
        },
        "governance_level": "auto",
    }


# ── ABC contract tests ───────────────────────────────────────────────────────


class TestRuntimeCompilerABC:
    """RuntimeCompiler is abstract and defines the compile() contract."""

    def test_base_class_cannot_be_instantiated(self):
        """ABC with abstractmethod → TypeError when instantiated directly."""
        with pytest.raises(TypeError):
            RuntimeCompiler()  # type: ignore[abstract]

    def test_all_compilers_have_compile_method(self):
        """Every concrete compiler exposes a callable compile()."""
        for compiler_cls in (N8NCompiler, ADKGoCompiler, PydanticAICompiler, PythonAgentCompiler):
            instance = compiler_cls()
            assert hasattr(instance, "compile"), f"{compiler_cls.__name__} missing compile"
            assert callable(instance.compile), f"{compiler_cls.__name__}.compile not callable"

    def test_n8n_compiler_wraps_existing(self):
        """N8NCompiler delegates to deterministic compile_n8n producing n8n shape."""
        draft = sample_draft()
        result = N8NCompiler().compile(draft)
        assert result["runtime"] == "n8n"
        assert "workflow.json" in result["files"]
        payload = json.loads(result["files"]["workflow.json"])
        assert "nodes" in payload, "n8n payload must have nodes"
        assert "connections" in payload, "n8n payload must have connections"
        assert len(payload["nodes"]) >= 1, "at least trigger node expected"

    def test_compiler_output_has_runtime_key(self):
        """Every compile result includes a 'runtime' key."""
        draft = sample_draft()
        for compiler in (N8NCompiler(), ADKGoCompiler(), PydanticAICompiler(), PythonAgentCompiler()):
            result = compiler.compile(draft)
            assert "runtime" in result, f"{type(compiler).__name__} result missing 'runtime'"

    def test_compiler_output_has_files_key(self):
        """Every compile result includes a 'files' dict key."""
        draft = sample_draft()
        for compiler in (N8NCompiler(), ADKGoCompiler(), PydanticAICompiler(), PythonAgentCompiler()):
            result = compiler.compile(draft)
            assert "files" in result, f"{type(compiler).__name__} result missing 'files'"
            assert isinstance(result["files"], dict), f"{type(compiler).__name__}.files not a dict"
            assert len(result["files"]) > 0, f"{type(compiler).__name__}.files is empty"


# ── ADK Go compiler tests ────────────────────────────────────────────────────


class TestADKGoCompiler:
    """ADKGoCompiler generates syntactically valid Go source files."""

    def test_compiles_valid_go_syntax(self):
        """Output contains essential Go boilerplate keywords."""
        draft = sample_draft()
        result = ADKGoCompiler().compile(draft)
        content = result["files"]["main.go"]
        assert "package main" in content, "missing package declaration"
        assert "func main()" in content, "missing main function"
        assert "import" in content, "missing import block"

    def test_includes_tools_from_side_effects(self):
        """Side-effect entries become tool/action functions."""
        draft = sample_draft()
        result = ADKGoCompiler().compile(draft)
        content = result["files"]["main.go"]
        # Each side-effect type should appear as a function call or reference
        assert "slack_notify" in content, "side-effect slack_notify not found"
        assert "update_ticket" in content, "side-effect update_ticket not found"

    def test_includes_tools_file(self):
        """Separate tools.go is produced alongside main.go."""
        draft = sample_draft()
        result = ADKGoCompiler().compile(draft)
        assert "tools.go" in result["files"], "missing tools.go output file"


# ── PydanticAI compiler tests ────────────────────────────────────────────────


class TestPydanticAICompiler:
    """PydanticAICompiler generates valid Python with Pydantic models + tools."""

    def test_compiles_valid_python(self):
        """Generated code parses as valid Python AST and contains a Pydantic model."""
        draft = sample_draft()
        result = PydanticAICompiler().compile(draft)
        code = result["files"]["agent.py"]
        tree = ast.parse(code)  # raises SyntaxError if invalid
        assert any(
            isinstance(n, ast.ClassDef) and "Model" in n.name
            for n in ast.walk(tree)
        ), "no Pydantic model class found"

    def test_has_output_model(self):
        """Code includes a BaseModel subclass for structured output."""
        draft = sample_draft()
        result = PydanticAICompiler().compile(draft)
        code = result["files"]["agent.py"]
        assert "BaseModel" in code, "missing BaseModel import or usage"
        assert "class " in code, "no class definition"

    def test_has_tool_decorators(self):
        """Code uses @agent.tool decorators for side effects."""
        draft = sample_draft()
        result = PydanticAICompiler().compile(draft)
        code = result["files"]["agent.py"]
        assert "@agent.tool" in code or "@agent_tool" in code, "no tool decorator found"


# ── Python Agent (smolagents) compiler tests ─────────────────────────────────


class TestPythonAgentCompiler:
    """PythonAgentCompiler generates valid smolagents-style CodeAgent code."""

    def test_compiles_valid_python(self):
        """Generated code parses as valid Python AST."""
        draft = sample_draft()
        result = PythonAgentCompiler().compile(draft)
        code = result["files"]["agent.py"]
        ast.parse(code)  # raises SyntaxError if invalid
        assert True  # reached => valid syntax

    def test_has_codeagent_class(self):
        """Code references CodeAgent from smolagents."""
        draft = sample_draft()
        result = PythonAgentCompiler().compile(draft)
        code = result["files"]["agent.py"]
        assert "CodeAgent" in code, "missing CodeAgent reference"


# ── Runtime factory tests ────────────────────────────────────────────────────


class TestRuntimeFactory:
    """get_compiler() routes by runtime name."""

    def test_returns_correct_compiler(self):
        """Factory returns the right compiler type for each runtime key."""
        assert type(get_compiler("n8n")).__name__ == "N8NCompiler"
        assert type(get_compiler("adk_go")).__name__ == "ADKGoCompiler"
        assert type(get_compiler("pydantic_ai")).__name__ == "PydanticAICompiler"
        assert type(get_compiler("python_agent")).__name__ == "PythonAgentCompiler"

    def test_invalid_runtime_raises(self):
        """Unknown runtime raises ValueError with helpful message."""
        with pytest.raises(ValueError, match="Unknown runtime|not found|unrecognized"):
            get_compiler("nonexistent")
