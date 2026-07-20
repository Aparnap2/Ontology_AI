"""OntologyAI V5.1 — PythonAgent (smolagents) compiler.

Generates valid Python source code using the ``smolagents`` library to define
a ``CodeAgent`` with ``@tool`` decorated functions. Produces a single file:

* ``agent.py`` — tool definitions, CodeAgent instantiation, runner function.

Determinism
-----------
No ``uuid`` / ``random``. Output is purely a function of the draft dict.
"""

from __future__ import annotations

from typing import Any

from src.runtime.base import RuntimeCompiler


def _python_fn_name(name: str) -> str:
    """Convert a type identifier to a valid Python function name."""
    return name.replace(".", "_").replace("-", "_")


def _generate_agent_py(draft: dict[str, Any]) -> str:
    """Generate ``agent.py`` content with smolagents CodeAgent."""
    steps: list[dict[str, Any]] = list(draft.get("steps", []))
    side_effects: list[dict[str, Any]] = list(draft.get("side_effects", []))
    inputs: dict[str, Any] = draft.get("inputs", {})

    lines: list[str] = [
        '"""Auto-generated smolagents CodeAgent — OntologyAI V5.1."""',
        "from __future__ import annotations",
        "",
        "from smolagents import CodeAgent, tool",
        "from smolagents.models import HfApiModel",
        "",
    ]

    # -- @tool decorated functions from side effects ---------------------------
    tool_names: list[str] = []
    for se in side_effects:
        fn_name = _python_fn_name(se.get("type", "unknown"))
        tool_names.append(fn_name)
        se_params: dict[str, Any] = se.get("params", {})
        desc = se.get("description", fn_name)

        lines.append("@tool")
        lines.append(f"def {fn_name}(")
        params = list(se_params.keys())
        for idx, k in enumerate(params):
            v = se_params[k]
            comma = "," if idx < len(params) - 1 else ""
            lines.append(f"    {k}: {_py_type(v)}{comma}")
        lines.append(") -> str:")
        lines.append(f'    """{desc}."""')
        if params:
            param_reprs = ", ".join(repr(p) for p in params)
            lines.append(f"    # Process parameters: {param_reprs}")
            lines.append(f'    return "Executed {fn_name}"')
        else:
            lines.append(f'    return "Executed {fn_name}"')
        lines.append("")

    # -- CodeAgent instantiation -----------------------------------------------
    tool_list = ", ".join(tool_names) if tool_names else ""
    lines.append(f"agent = CodeAgent(")
    lines.append(f"    tools=[{tool_list}],")
    lines.append(f"    model=HfApiModel(),")
    lines.append(f")")
    lines.append("")

    # -- Runner ----------------------------------------------------------------
    lines.append("")
    lines.append("def run(")
    if isinstance(inputs, dict) and inputs:
        items = list(inputs.items())
        for idx, (field_name, field_type) in enumerate(items):
            comma = "," if idx < len(items) - 1 else ""
            lines.append(f"    {field_name}: {_py_type(field_type)}{comma}")
    lines.append(") -> dict:")

    if isinstance(inputs, dict) and inputs:
        prompt_parts = [f"{k}={{{k}}}" for k in inputs]
        prompt = ", ".join(prompt_parts)
    else:
        prompt = "execute workflow"

    lines.append(f'    prompt = f"Process {prompt}"')
    lines.append("    return agent.run(prompt)")
    lines.append("")

    return "\n".join(lines)


def _py_type(field_type: Any) -> str:
    """Map a type label to a Python type annotation."""
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


class PythonAgentCompiler(RuntimeCompiler):
    """Compiler targeting the smolagents CodeAgent Python runtime.

    Generates ``agent.py`` with ``@tool`` decorated functions, a ``CodeAgent``
    instance, and a ``run()`` entry point.
    """

    def compile(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Compile a draft dict into a smolagents CodeAgent.

        Returns:
            Dict with ``runtime="python_agent"`` and ``files`` containing
            ``agent.py``.
        """
        return {
            "runtime": "python_agent",
            "files": {
                "agent.py": _generate_agent_py(draft),
            },
        }
