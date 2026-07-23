"""OntologyAI V5.1 — ChiefOfStaffWorkflow (PRD §8.1 / §16.1).

Control-plane orchestrator. Loads ``EngagementState`` (init phase="discovery"
if none), classifies intent (deterministic), routes to one or more specialist
workflows, collects typed ``SpecialistResponse``s, deterministically merges
valid patches into ``EngagementState``, and produces a summary + next step +
unresolved questions.

Design (thin-LLM / fat-deterministic-core, PRD §11):
  * Intent classification + routing + state merge are deterministic.
  * The LLM is used ONLY for summary synthesis (injected + mocked in tests).

Backward compatibility: the workflow is still named ``ChiefOfStaffWorkflow``
and ``@sarthi`` still routes here (PRD §25.3).

The deterministic core (``ChiefOfStaffCore``) is importable and testable
without a running Temporal server. The Temporal ``@workflow.defn`` wrapper
delegates to it.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from src.agents.agent_bus import AgentBus
from src.schemas.specialist_response import SpecialistResponse
from src.schemas.engagement_state import EngagementState, merge_patch
from src.ontology.object_types import OBJECT_TYPES


# Deterministic intent classification keywords (PRD §16.1 step 3).
_INTENT_KEYWORDS: dict[str, str] = {
    # ── Wizard / setup intents (highest priority — PRD §25.2) ────────
    "setup": "setup_ontology",
    "wizard": "setup_ontology",
    # ── Standard intents ────────────────────────────────────────────
    "discovery": "discovery",
    "discover": "discovery",
    "ingest": "discovery",
    "upload": "discovery",
    "transcript": "discovery",
    "map": "ontology_mapping",
    "ontology": "ontology_mapping",
    "canonical": "ontology_mapping",
    "truth": "truth_analysis",
    "stuck": "truth_analysis",
    "overdue": "truth_analysis",
    "risk": "truth_analysis",
    "build": "workflow_design",
    "workflow": "workflow_design",
    "sop": "workflow_design",
    "automate": "workflow_design",
    "govern": "governance_review",
    "approve": "governance_review",
    "activation": "governance_review",
    "deploy": "governance_review",
    "handoff": "handoff",
    "summary": "handoff",
    "export": "handoff",
    "strategy": "strategy",
    "objective": "strategy",
    "current.state": "strategy",
    "change.strategy": "strategy",
    "risk.analysis": "strategy",
    "evaluate": "strategy",
}


class ChiefOfStaffCore:
    """Deterministic control-plane core (no Temporal dependency)."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm_client = llm_client

    # ------------------------------------------------------------------
    # Intent classification (deterministic)
    # ------------------------------------------------------------------
    def classify_intent(self, message: str) -> str:
        """Classify a workspace message into one of the engagement intents."""
        low = (message or "").lower()
        # Explicit @alias routing hints take priority.
        for alias, intent in {
            "@setup": "setup_ontology",
            "@discover": "discovery",
            "@map": "ontology_mapping",
            "@truth": "truth_analysis",
            "@build": "workflow_design",
            "@govern": "governance_review",
            "@strategy": "strategy",
        }.items():
            if alias in low:
                return intent
        # Keyword-based classification (first match wins, priority order).
        for kw, intent in _INTENT_KEYWORDS.items():
            if re.search(rf"\b{re.escape(kw)}\b", low):
                return intent
        # Default: discovery intake for freeform messages.
        return "discovery"

    # ------------------------------------------------------------------
    # Route intent -> specialist workflow class
    # ------------------------------------------------------------------
    def route(self, intent: str) -> list[type]:
        from src.workflows.discovery_workflow import DiscoveryWorkflow
        from src.workflows.ontology_mapping_workflow import OntologyMappingWorkflow
        from src.workflows.truth_analysis_workflow import TruthAnalysisWorkflow
        from src.workflows.workflow_builder_workflow import WorkflowBuilderWorkflow
        from src.workflows.governance_workflow import GovernanceWorkflow
        from src.workflows.strategy_workflow import StrategyWorkflow

        mapping = {
            "setup_ontology": [DiscoveryWorkflow],
            "discovery": [DiscoveryWorkflow],
            "ontology_mapping": [OntologyMappingWorkflow],
            "truth_analysis": [TruthAnalysisWorkflow],
            "workflow_design": [WorkflowBuilderWorkflow],
            "governance_review": [GovernanceWorkflow],
            "strategy": [StrategyWorkflow],
            "handoff": [WorkflowBuilderWorkflow, GovernanceWorkflow],
        }
        return mapping.get(intent, [DiscoveryWorkflow])

    # ------------------------------------------------------------------
    # State load / init
    # ------------------------------------------------------------------
    def load_state(
        self,
        state: Optional[Any],
        tenant_id: str,
        engagement_id: str,
        workspace_mode: str = "fde_assisted",
    ) -> EngagementState:
        if state is None:
            return EngagementState.create(
                engagement_id=engagement_id,
                tenant_id=tenant_id,
                workspace_mode=workspace_mode,
            )
        if isinstance(state, EngagementState):
            return state
        return EngagementState(**state)

    # ------------------------------------------------------------------
    # Agent inbox drain (P2P bypass)
    # ------------------------------------------------------------------
    def _process_agent_inbox(
        self, state: EngagementState
    ) -> list[dict[str, Any]]:
        """Drain and dispatch any unread inter-agent messages.

        Reads ``agent_inbox``, marks unread messages as read, and returns
        them for processing. This runs BEFORE intent classification so that
        direct agent-to-agent signals bypass human input.
        """
        inbox = list(state.agent_inbox)
        unread = AgentBus.drain(inbox)
        if not unread:
            return []

        # Lazy import to avoid circular dependency (__init__ imports this module).
        from src.workflows import AGENT_REGISTRY  # noqa: PLC0415

        dispatched: list[dict[str, Any]] = []
        for msg in unread:
            target_wf = AGENT_REGISTRY.get(msg.recipient)
            if target_wf is not None:
                dispatched.append({
                    "from": msg.sender,
                    "to": msg.recipient,
                    "type": msg.message_type,
                    "payload": msg.payload,
                    "thread_id": msg.thread_id,
                })
        return dispatched

    # ------------------------------------------------------------------
    # Orchestrate
    # ------------------------------------------------------------------
    def orchestrate(
        self,
        tenant_id: str,
        engagement_id: str,
        message: str,
        state: Optional[Any] = None,
        sources: Optional[list[dict]] = None,
        workspace_mode: str = "fde_assisted",
    ) -> SpecialistResponse:
        """Run the control plane and return a ChiefOfStaff SpecialistResponse."""
        eng_state = self.load_state(state, tenant_id, engagement_id, workspace_mode)

        # Drain agent inbox before processing human input (P2P bypass).
        inbox_messages = self._process_agent_inbox(eng_state)
        if inbox_messages:
            # If there are pending agent messages, they can trigger
            # automated dispatch without re-classifying intent.
            pass  # Future: route based on inbox message types

        intent = self.classify_intent(message)
        workflow_classes = self.route(intent)

        collected: list[SpecialistResponse] = []
        merged = eng_state

        for wf_cls in workflow_classes:
            wf = wf_cls()
            resp = self._invoke_specialist(wf, wf_cls, tenant_id, engagement_id,
                                           message, sources, eng_state)
            if resp is None:
                continue
            collected.append(resp)
            patch = resp.engagement_state_patch
            if patch:
                merged = merge_patch(merged, patch, provenance=resp.specialist)

        # Advance phase deterministically based on intent.
        next_phase = self._next_phase(intent, merged.phase)
        if next_phase != merged.phase:
            merged = merge_patch(merged, {"phase": next_phase},
                                 provenance="ChiefOfStaff")

        summary = self._summarize(intent, collected, merged)
        unresolved = list(dict.fromkeys(
            q for r in collected for q in (r.unresolved_questions or [])
        ))

        return SpecialistResponse(
            specialist="ChiefOfStaff",
            workflow_name="ChiefOfStaffWorkflow",
            summary=summary,
            detailed_response=summary,
            objects_read=["engagement_state"],
            objects_written=["engagement_state"],
            requires_hitl=any(r.requires_hitl for r in collected),
            engagement_state_patch={"phase": merged.phase},
            citations=sorted({c for r in collected for c in r.citations}),
            followups=unresolved[:5],
            unresolved_questions=unresolved,
            confidence=0.85,
        )

    # ------------------------------------------------------------------
    # Specialist invocation (deterministic arg assembly)
    # ------------------------------------------------------------------
    def _invoke_specialist(
        self, wf: Any, wf_cls: type, tenant_id: str, engagement_id: str,
        message: str, sources: Optional[list[dict]], eng_state: EngagementState,
    ) -> Optional[SpecialistResponse]:
        name = wf_cls.__name__
        try:
            if name == "DiscoveryWorkflow":
                return wf.run(
                    tenant_id=tenant_id, engagement_id=engagement_id,
                    sources=sources or [{"type": "note", "content": message, "ref": "chat"}],
                )
            if name == "OntologyMappingWorkflow":
                return wf.run(
                    tenant_id=tenant_id, engagement_id=engagement_id,
                    discovery_notes=eng_state.discovery_notes,
                )
            if name == "TruthAnalysisWorkflow":
                return wf.run(
                    tenant_id=tenant_id, engagement_id=engagement_id,
                    ontology_objects=eng_state.ontology_objects,
                    ontology_links=eng_state.ontology_links,
                )
            if name == "WorkflowBuilderWorkflow":
                return wf.run(
                    tenant_id=tenant_id, engagement_id=engagement_id,
                    truth_findings=eng_state.truth_findings,
                    ontology_objects=eng_state.ontology_objects,
                )
            if name == "GovernanceWorkflow":
                return wf.run(
                    tenant_id=tenant_id, engagement_id=engagement_id,
                    planned_actions=eng_state.planned_actions,
                    executable_workflow_drafts=eng_state.executable_workflow_drafts,
                )
        except Exception:
            # Degrade gracefully on missing data (PRD §4 principle 10).
            return None
        return None

    # ------------------------------------------------------------------
    # Phase progression (deterministic)
    # ------------------------------------------------------------------
    def _next_phase(self, intent: str, current: str) -> str:
        order = [
            "discovery", "ontology_mapping", "truth_analysis",
            "workflow_design", "governance_review", "deployment_planning", "handoff",
        ]
        target = {
            "setup_ontology": "discovery",
            "discovery": "discovery",
            "ontology_mapping": "ontology_mapping",
            "truth_analysis": "truth_analysis",
            "workflow_design": "workflow_design",
            "governance_review": "governance_review",
            "handoff": "handoff",
        }.get(intent, current)
        # Never skip phases backward; only advance forward.
        if order.index(target) > order.index(current):
            return target
        return current

    # ------------------------------------------------------------------
    # Summary synthesis (LLM optional, deterministic fallback)
    # ------------------------------------------------------------------
    def _summarize(self, intent: str, collected: list[SpecialistResponse],
                   state: EngagementState) -> str:
        if self.llm_client is not None and collected:
            try:
                synth = self.llm_client.synthesize(  # type: ignore[attr-defined]
                    intent=intent, responses=[r.model_dump() for r in collected]
                )
                if synth:
                    return str(synth)
            except Exception:
                pass
        parts = [f"Routed to {intent}."]
        for r in collected:
            parts.append(f"- {r.specialist}: {r.summary}")
        parts.append(f"Phase now: {state.phase}.")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Temporal wrapper (preserves @workflow.defn name="ChiefOfStaffWorkflow")
# ---------------------------------------------------------------------------
try:
    from temporalio import workflow

    with workflow.unsafe.imports_passed_through():
        pass

    @workflow.defn(name="ChiefOfStaffWorkflow")
    class ChiefOfStaffWorkflow:
        """Temporal workflow wrapper around ChiefOfStaffCore."""

        @workflow.run
        async def run(self, input: dict) -> dict:
            core = ChiefOfStaffCore()
            resp = core.orchestrate(
                tenant_id=input.get("tenant_id", ""),
                engagement_id=input.get("engagement_id", ""),
                message=input.get("message", input.get("question", "")),
                state=input.get("engagement_state"),
                sources=input.get("sources"),
                workspace_mode=input.get("workspace_mode", "fde_assisted"),
            )
            return resp.model_dump()

except Exception:  # pragma: no cover - Temporal optional at import time
    # Fallback: expose the core class under the workflow name when Temporal is
    # not available (keeps imports/tests working without a Temporal server).
    ChiefOfStaffWorkflow = ChiefOfStaffCore  # type: ignore[assignment,misc]
