"""OntologyAI V5.1 — ExecutableWorkflowDraft re-export (PRD §12.7).

This module is a thin re-export shim. The single source of truth for
:class:`ExecutableWorkflowDraft` lives in
``src.ontology.workflow_drafts`` (it carries the governance/compiler guard
validators). We re-export it here so schema-layer consumers can import from
``src.schemas.executable_workflow_draft`` without depending on the ontology
package directly.
"""
from __future__ import annotations

from src.ontology.workflow_drafts import ExecutableWorkflowDraft

# Primary symbol exposed by this module.
__all__ = ["ExecutableWorkflowDraft"]

# Thin alias kept for callers that prefer the explicit name.
ExecutableWorkflowDraftModel = ExecutableWorkflowDraft
