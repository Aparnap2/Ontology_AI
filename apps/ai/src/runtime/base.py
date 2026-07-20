"""OntologyAI V5.1 — Multi-runtime compiler ABC (PRD §17, §12.7).

All runtime compilers inherit from :class:`RuntimeCompiler` and implement the
deterministic ``compile(draft: dict) -> dict`` method.

Output contract
---------------
Every ``compile()`` result dict MUST contain at minimum:

* ``runtime`` (str) — canonical runtime name: ``"n8n"``, ``"adk_go"``,
  ``"pydantic_ai"``, or ``"python_agent"``.
* ``files`` (dict[str, str]) — filename → generated source code / payload.
  At least one file entry is required.

Determinism (PRD §11, §28.2)
-----------------------------
Every compiler MUST produce the same output dict (byte-identical when
serialized) for the same input draft. No ``uuid4()``, ``random``, or time-based
values.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RuntimeCompiler(ABC):
    """Abstract base for all deterministic runtime compilers."""

    @abstractmethod
    def compile(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Compile a workflow draft dict into runtime-specific output.

        Args:
            draft: A workflow draft dict (canonical intermediate representation).

        Returns:
            A dict with ``runtime`` (str) and ``files`` (dict[str, str]) keys.
            Additional keys may be added per compiler but are not required.
        """
        ...
