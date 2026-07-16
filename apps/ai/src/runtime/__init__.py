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

from src.runtime import artifact_export
from src.runtime.custom_agent_compiler import compile_custom_agent
from src.runtime.n8n_compiler import compile_n8n

__all__ = [
    "compile_n8n",
    "compile_custom_agent",
    "artifact_export",
]
