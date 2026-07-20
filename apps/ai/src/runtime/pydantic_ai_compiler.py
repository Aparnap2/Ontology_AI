"""OntologyAI V5.1 — PydanticAI compiler.

Generates valid Python source code that uses ``pydantic`` and ``pydantic_ai``
to define a typed agent with tool decorators. Produces a single file:

* ``agent.py`` — Pydantic output model, agent instance, tool decorators, runner.

Determinism
-----------
No ``uuid`` / ``random``. Output is purely a function of the draft dict.
"""

from __future__ import annotations

import textwrap
from typing import Any

from src.runtime.base import RuntimeCompiler


def _pascal_case(name: str) -> str:
    """Convert snake_case or kebab-case to PascalCase."""
    return "".join(word.capitalize() for word in name.replace("-", "_").split("_"))


def _generate_agent_py(draft: dict[str, Any]) -> str:
    """Generate ``agent.py`` content with Pydantic model + tools."""
    steps: list[dict[str, Any]] = list(draft.get("steps", []))
    side_effects: list[dict[str, Any]] = list(draft.get("side_effects", []))
    outputs: dict[str, Any] = draft.get("outputs", {})
    inputs: dict[str, Any] = draft.get("inputs", {})

    lines: list[str] = [
        '"""Auto-generated PydanticAI agent — OntologyAI V5.1."""',
        "from __future__ import annotations",
        "",
        "from pydantic import BaseModel",
        "from pydantic_ai import Agent",
        "",
    ]

    # -- Output model ----------------------------------------------------------
    output_model_name = "WorkflowOutputModel"
    lines.append(f"class {output_model_name}(BaseModel):")
    if isinstance(outputs, dict) and outputs:
        for field_name, field_type in outputs.items():
            py_type = _pydantic_type(field_type)
            lines.append(f"    {field_name}: {py_type}")
    else:
        lines.append("    result: str = ''")
    lines.append("")

    # -- Agent instance --------------------------------------------------------
    lines.append(
        f'agent = Agent("openai:gpt-4o", result_type={output_model_name})'
    )
    lines.append("")

    # -- Tool decorators from side effects ------------------------------------
    for se in side_effects:
        fn_name = _python_fn_name(se.get("type", "unknown"))
        se_params: dict[str, Any] = se.get("params", {})
        desc = se.get("description", fn_name)

        params_list: list[str] = ["ctx"]
        for k, v in se_params.items():
            params_list.append(f"{k}: {_pydantic_type(v)}")

        params_str = ", ".join(params_list)
        return_type = "str"

        lines.append("@agent.tool")
        lines.append(f"def {fn_name}({params_str}) -> {return_type}:")
        lines.append(f'    """{desc}."""')
        lines.append(f'    return f"Executed: {desc}"')

        # Return appropriate type based on output shape
        lines.append("")

    # -- Runner ----------------------------------------------------------------
    lines.append("")
    lines.append("def run(")
    if isinstance(inputs, dict) and inputs:
        for idx, (field_name, field_type) in enumerate(inputs.items()):
            comma = "," if idx < len(inputs) - 1 else ""
            lines.append(f"    {field_name}: {_pydantic_type(field_type)}{comma}")
    lines.append(") -> " + output_model_name + ":")
    lines.append(
        '    """Execute the agent workflow and return structured output."""'
    )

    if isinstance(inputs, dict) and inputs:
        prompt_parts = [f"{k}={{{k}}}" for k in inputs]
        prompt = ", ".join(prompt_parts)
    else:
        prompt = "execute workflow"

    lines.append(f'    prompt = f"Process {prompt}"')
    lines.append("    result = agent.run_sync(prompt)")
    lines.append("    return result.data")
    lines.append("")

    return "\n".join(lines)


def _pydantic_type(field_type: Any) -> str:
    """Map a type label to a Python / Pydantic type annotation."""
    mapping: dict[str, str] = {
        "string": "str",
        "integer": "int",
        "float": "float",
        "boolean": "bool",
        "dict": "dict",
        "list": "list",
        "any": "Any",
    }
    if isinstance(field_type, str):
        return mapping.get(field_type.lower(), "str")
    return "str"


def _python_fn_name(name: str) -> str:
    """Convert a type identifier to a valid Python function name."""
    return name.replace(".", "_").replace("-", "_")


class PydanticAICompiler(RuntimeCompiler):
    """Compiler targeting the PydanticAI Python runtime.

    Generates ``agent.py`` with a Pydantic output model, an ``Agent`` instance,
    ``@agent.tool`` decorated tool functions, and a ``run()`` entry point.
    """

    def compile(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Compile a draft dict into a PydanticAI Python agent.

        Returns:
            Dict with ``runtime="pydantic_ai"`` and ``files`` containing
            ``agent.py``.
        """
        return {
            "runtime": "pydantic_ai",
            "files": {
                "agent.py": _generate_agent_py(draft),
            },
        }
