"""OntologyAI V5.1 — ADK (Agent Development Kit) Go compiler.

Generates syntactically valid Go source code for executing workflow drafts
as Go agents. Produces two files:

* ``main.go`` — entry point, step orchestration, side-effect execution.
* ``tools.go`` — tool / action function definitions.

Determinism
-----------
No ``uuid`` / ``random``. Output is purely a function of the draft dict.
"""

from __future__ import annotations

import textwrap
from typing import Any

from src.runtime.base import RuntimeCompiler


def _indent(code: str, level: int = 1) -> str:
    """Indent code block by ``level`` levels (one level = one tab)."""
    return textwrap.indent(code, "\t" * level)


def _go_fn_name(step_type: str) -> str:
    """Convert snake_case step type to a valid Go function name."""
    return step_type.replace(".", "_")


def _generate_main_go(draft: dict[str, Any]) -> str:
    """Generate ``main.go`` content."""
    steps: list[dict[str, Any]] = list(draft.get("steps", []))
    side_effects: list[dict[str, Any]] = list(draft.get("side_effects", []))
    inputs: dict[str, Any] = draft.get("inputs", {})
    if isinstance(inputs, dict):
        input_items = list(inputs.items())
    else:
        input_items = []

    lines: list[str] = [
        "package main",
        "",
        'import (',
        '\t"context"',
        '\t"fmt"',
        '\t"log"',
        '\t"os"',
        ')',
        "",
        "func main() {",
        _indent("ctx := context.Background()"),
        "",
        _indent("// Input parameters"),
    ]

    # Input env-var reading
    for key, _typ in input_items:
        lines.append(_indent('{} := os.Getenv("{}")'.format(key, key.upper())))

    lines.append("")
    lines.append(_indent('log.Println("Starting workflow execution")'))
    lines.append("")

    # -- Step execution --------------------------------------------------------
    if steps:
        lines.append(_indent("// Workflow steps"))
        prev_var = "input"
        lines.append(_indent(f'{prev_var} := map[string]any{{}}'))

        for i, step in enumerate(steps):
            step_type = step.get("type", f"step_{i}")
            step_var = f"result{i}"
            lines.append(
                _indent(f'{step_var} := {_go_fn_name(step_type)}(ctx, {prev_var})')
            )
            prev_var = step_var

    lines.append("")

    # -- Side effects ----------------------------------------------------------
    if side_effects:
        lines.append(_indent("// Side effects"))
        for se in side_effects:
            se_type = se.get("type", "unknown")
            se_params: dict[str, Any] = se.get("params", {})
            args = ", ".join(
                f'"{v}"' if isinstance(v, str) else str(v)
                for v in se_params.values()
            )
            lines.append(
                _indent(f'{_go_fn_name(se_type)}(ctx, {args})')
            )

    lines.append("")
    lines.append(_indent('fmt.Println("Workflow execution complete")'))
    lines.append("}")

    return "\n".join(lines) + "\n"


def _generate_tools_go(draft: dict[str, Any]) -> str:
    """Generate ``tools.go`` content with action + side-effect stubs."""
    steps: list[dict[str, Any]] = list(draft.get("steps", []))
    side_effects: list[dict[str, Any]] = list(draft.get("side_effects", []))

    lines: list[str] = [
        "package main",
        "",
        'import (',
        '\t"context"',
        '\t"fmt"',
        ')',
        "",
    ]

    # Step tool functions
    for step in steps:
        fn = _go_fn_name(step.get("type", "unknown"))
        lines.extend(
            [
                f"func {fn}(ctx context.Context, input map[string]any) map[string]any {{",
                _indent(f'fmt.Println("Executing: {step.get("description", fn)}")'),
                _indent('return map[string]any{"result": "done"}'),
                "}",
                "",
            ]
        )

    # Side-effect functions
    for se in side_effects:
        fn = _go_fn_name(se.get("type", "unknown"))
        se_params: dict[str, Any] = se.get("params", {})
        params_list = ", ".join(
            f"{k} string" if isinstance(v, str) else f"{k} any"
            for k, v in se_params.items()
        )
        params_str = f"ctx context.Context, {params_list}" if params_list else "ctx context.Context"
        lines.extend(
            [
                f"func {fn}({params_str}) string {{",
                _indent(
                    'fmt.Println("{}")'.format(se.get("description", fn))
                ),
                _indent('return "ok"'),
                "}",
                "",
            ]
        )

    return "\n".join(lines)


class ADKGoCompiler(RuntimeCompiler):
    """Compiler targeting the ADK (Agent Development Kit) Go runtime.

    Generates ``main.go`` and ``tools.go`` for a Go-based agent.
    """

    def compile(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Compile a draft dict into ADK Go source files.

        Returns:
            Dict with ``runtime="adk_go"`` and ``files`` containing
            ``main.go`` and ``tools.go``.
        """
        return {
            "runtime": "adk_go",
            "files": {
                "main.go": _generate_main_go(draft),
                "tools.go": _generate_tools_go(draft),
            },
        }
