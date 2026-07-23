"""OntologyAI V5.1 — Runtime / Export layer (PRD §17, §19.3, §20.1.5, §12.7).

This package contains the DETERMINISTIC compilers that turn an
:class:`ExecutableWorkflowDraft` into a runtime-specific export payload, plus
the artifact export generators (PRD §19.3).

Hard rule (PRD §10.6, §11.2, §12.7, §30.11)
-------------------------------------------
``export_payload`` may ONLY be populated by deterministic compiler logic. The
LLM path may propose structure but must never write ``export_payload``. Every
compiler therefore calls ``draft.set_export_payload(...)`` — the ONLY sanctioned
setter — and never constructs a draft with ``export_payload`` already set.

Determinism (PRD §11, §28.2)
----------------------------
No ``uuid4()`` / ``random`` in output payloads. Node/state identifiers are
ordered indices or stable hashes of the draft's own fields, so the same draft
always compiles to byte-identical JSON.
"""
from __future__ import annotations

from typing import Type  # noqa: TYP001 — used for Type[RuntimeCompiler]

from src.runtime import artifact_export
from src.runtime.adk_go_compiler import ADKGoCompiler
from src.runtime.base import RuntimeCompiler
from src.runtime.credentials import CredentialBinding, CredentialStore
from src.runtime.custom_agent_compiler import compile_custom_agent
from src.runtime.deployers import (
    DeployerResult,
    deploy_custom_agent,
    deploy_to_n8n,
    deploy_to_windmill,
)
from src.runtime.n8n_compiler import compile_n8n
from src.runtime.n8n import N8NCompiler
from src.runtime.pydantic_ai_compiler import PydanticAICompiler
from src.runtime.python_agent_compiler import PythonAgentCompiler
from src.runtime.experimental.windmill_compiler import WindmillCompiler
from src.runtime.experimental.windmill_client import WindmillClientError

# ── Compiler registry (V5.1 multi-runtime) ───────────────────────────────────
_COMPILERS: dict[str, Type[RuntimeCompiler]] = {
    "n8n": N8NCompiler,
    "adk_go": ADKGoCompiler,
    "pydantic_ai": PydanticAICompiler,
    "python_agent": PythonAgentCompiler,
    "windmill": WindmillCompiler,
}


def get_compiler(runtime: str) -> RuntimeCompiler:
    """Return a compiler instance for the given runtime name.

    Args:
        runtime: One of ``"n8n"``, ``"adk_go"``, ``"pydantic_ai"``,
            ``"python_agent"``, ``"windmill"``.

    Returns:
        A ready-to-use :class:`RuntimeCompiler` instance.

    Raises:
        ValueError: If ``runtime`` is not a recognised compiler name.
    """
    if runtime not in _COMPILERS:
        raise ValueError(
            f"Unknown runtime: {runtime!r}. "
            f"Available runtimes: {list(_COMPILERS.keys())}"
        )
    return _COMPILERS[runtime]()


__all__ = [
    "compile_n8n",
    "compile_custom_agent",
    "artifact_export",
    # V5.1 class-based compilers
    "RuntimeCompiler",
    "N8NCompiler",
    "ADKGoCompiler",
    "PydanticAICompiler",
    "PythonAgentCompiler",
    "WindmillCompiler",
    "get_compiler",
    # V5.1 credentials
    "CredentialBinding",
    "CredentialStore",
    # V5.1 deployers
    "DeployerResult",
    "deploy_to_n8n",
    "deploy_to_windmill",
    "deploy_custom_agent",
    # V5.1 windmill client
    "WindmillClientError",
]
