"""OntologyAI V5.1 — TruthAnalysisWorkflow (PRD §8.4 / §16.4).

Loads the ontology snapshot and computes DETERMINISTIC findings first
(missing owners, overdue money events, blocked engagements, unresolved
critical issues, unacted messages, orphaned records). The LLM is used ONLY
for synthesis across findings (injected + mocked in tests). Produces a truth
report + candidate ``PlannedAction`` drafts for action-worthy items.

Design (thin-LLM / fat-deterministic-core, PRD §11):
  * All six deterministic checks are pure code — no LLM.
  * LLM synthesis is optional and only invoked when ``synthesize=True``.
  * Never executes external actions.
"""
from __future__ import annotations

from typing import Any, Optional

from src.agents.semantic_layer import explain_mismatch
from src.schemas.specialist_response import SpecialistResponse
from src.ontology.action_types import ActionRegistry
from src.ontology.object_types import PlannedAction


class TruthAnalysisWorkflow:
    """Truth Analyst specialist workflow (PRD §8.4 / §16.4)."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm_client = llm_client

    def run(
        self,
        tenant_id: str,
        engagement_id: str,
        ontology_objects: dict[str, list[dict]],
        ontology_links: Optional[list[dict]] = None,
        synthesize: bool = False,
    ) -> SpecialistResponse:
        """Analyze the ontology snapshot and return truth findings + candidate actions.

        Args:
            tenant_id: Tenant identifier.
            engagement_id: Engagement identifier.
            ontology_objects: Dict keyed by object type name -> list of dicts.
            ontology_links: Optional list of link dicts (for orphan detection).
            synthesize: If True and an LLM client is injected, synthesize a
                narrative report across findings.

        Returns:
            SpecialistResponse with specialist="TruthAnalyst" and a patch to
            ``truth_findings`` (+ optional ``planned_actions``).
        """
        ontology_objects = ontology_objects or {}
        ontology_links = ontology_links or []
        findings: list[dict] = []
        candidate_actions: list[dict] = []

        # ── Deterministic checks (PRD §10.4) ──
        findings += self._check_missing_owners(ontology_objects)
        findings += self._check_overdue_money(ontology_objects)
        findings += self._check_blocked_engagements(ontology_objects)
        findings += self._check_unresolved_critical_issues(ontology_objects)
        findings += self._check_unacted_messages(ontology_objects)
        findings += self._check_orphaned(ontology_objects, ontology_links)

        # Revenue Protection: Order↔Shipment mismatch detection
        findings += self._check_order_shipment_mismatch(ontology_objects, ontology_links)

        # ── Candidate actions for action-worthy findings (deterministic) ──
        for f in findings:
            if f.get("action_worthy"):
                action = self._candidate_action(f, tenant_id)
                if action is not None:
                    candidate_actions.append(action)

        # ── Optional LLM synthesis across findings ──
        report = self._build_report(findings)
        if synthesize and self.llm_client is not None:
            try:
                synthesized = self.llm_client.synthesize(  # type: ignore[attr-defined]
                    findings=findings
                )
                if synthesized:
                    report = str(synthesized)
            except Exception:
                pass

        patch: dict[str, Any] = {"truth_findings": findings}
        if candidate_actions:
            patch["planned_actions"] = candidate_actions

        summary = (
            f"Truth analysis found {len(findings)} finding(s); "
            f"{len(candidate_actions)} candidate action(s) proposed."
        )

        return SpecialistResponse(
            specialist="TruthAnalyst",
            workflow_name="TruthAnalysisWorkflow",
            summary=summary,
            detailed_response=report,
            objects_read=["ontology_objects", "ontology_links"],
            objects_written=["truth_findings"],
            actions_proposed=[a["id"] for a in candidate_actions],
            requires_hitl=any(a.get("requires_approval") for a in candidate_actions),
            engagement_state_patch=patch,
            confidence=0.8,
            unresolved_questions=[
                f["summary"] for f in findings if f.get("needs_clarification")
            ],
        )

    # ------------------------------------------------------------------
    # Deterministic finding checks
    # ------------------------------------------------------------------
    def _check_missing_owners(self, objs: dict) -> list[dict]:
        out: list[dict] = []
        for type_name in ("Party", "Engagement", "Issue"):
            for o in objs.get(type_name, []):
                if not o.get("owner"):
                    out.append({
                        "kind": "missing_owner",
                        "target_type": type_name,
                        "target_id": o.get("id"),
                        "severity": "medium",
                        "summary": f"{type_name} {o.get('id')} has no owner",
                        "action_worthy": True,
                        "needs_clarification": True,
                    })
        return out

    def _check_overdue_money(self, objs: dict) -> list[dict]:
        out: list[dict] = []
        for m in objs.get("MoneyEvent", []):
            if m.get("status") == "overdue":
                out.append({
                    "kind": "overdue_money_event",
                    "target_type": "MoneyEvent",
                    "target_id": m.get("id"),
                    "severity": "high",
                    "summary": f"MoneyEvent {m.get('id')} is overdue",
                    "action_worthy": True,
                })
        return out

    def _check_blocked_engagements(self, objs: dict) -> list[dict]:
        out: list[dict] = []
        for e in objs.get("Engagement", []):
            if e.get("status") == "blocked":
                out.append({
                    "kind": "blocked_engagement",
                    "target_type": "Engagement",
                    "target_id": e.get("id"),
                    "severity": "high",
                    "summary": f"Engagement {e.get('id')} is blocked",
                    "action_worthy": True,
                })
        return out

    def _check_unresolved_critical_issues(self, objs: dict) -> list[dict]:
        out: list[dict] = []
        for i in objs.get("Issue", []):
            if i.get("severity") == "critical" and i.get("status") in ("open", "investigating", "waiting"):
                out.append({
                    "kind": "unresolved_critical_issue",
                    "target_type": "Issue",
                    "target_id": i.get("id"),
                    "severity": "critical",
                    "summary": f"Issue {i.get('id')} is critical and unresolved",
                    "action_worthy": True,
                })
        return out

    def _check_unacted_messages(self, objs: dict) -> list[dict]:
        out: list[dict] = []
        for msg in objs.get("Message", []):
            if msg.get("needs_action") and msg.get("direction") == "inbound":
                out.append({
                    "kind": "unacted_message",
                    "target_type": "Message",
                    "target_id": msg.get("id"),
                    "severity": "low",
                    "summary": f"Message {msg.get('id')} needs action and is unacted",
                    "action_worthy": True,
                })
        return out

    def _check_orphaned(self, objs: dict, links: list[dict]) -> list[dict]:
        out: list[dict] = []
        # A MoneyEvent with no engagement_money_event link is orphaned.
        linked_money = {
            l["target_id"] for l in links
            if l.get("name") == "engagement_money_event"
        }
        for m in objs.get("MoneyEvent", []):
            if m.get("id") not in linked_money:
                out.append({
                    "kind": "orphaned_record",
                    "target_type": "MoneyEvent",
                    "target_id": m.get("id"),
                    "severity": "medium",
                    "summary": f"MoneyEvent {m.get('id')} is not linked to any engagement",
                    "action_worthy": True,
                })
        return out

    _REVENUE_THRESHOLD = 0.05  # 5% — configurable threshold

    def _check_order_shipment_mismatch(
        self, objs: dict[str, list[dict]], links: Optional[list[dict]] = None
    ) -> list[dict]:
        """Detect Order↔Shipment value mismatches (Revenue Protection vertical slice).

        Deterministic math check, optional LLM explanation. Compares each
        Engagement(kind='order') value against total shipped_value of linked
        Shipments. Returns findings with action_worthy=True when |delta| > threshold.
        """
        out: list[dict] = []
        orders = [o for o in objs.get("Engagement", []) if o.get("kind") == "order"]
        if not orders:
            return out

        # Build linked shipment IDs from order_shipment links
        use_links = links is not None
        linked_shipment_ids: set[str] = set()
        if use_links:
            linked_shipment_ids = {
                l["target_id"] for l in links
                if l.get("name") == "order_shipment"
            }

        # Index all shipments by order_id
        shipments_by_order: dict[str, list[dict]] = {}
        for s in objs.get("Shipment", []):
            oid = s.get("order_id", "")
            if oid:
                shipments_by_order.setdefault(oid, []).append(s)

        for order in orders:
            order_id = order.get("id", "")
            order_value = order.get("value") or 0.0

            # Skip zero-value orders (division-safe guard)
            if order_value <= 0:
                continue

            # Resolve linked shipments
            if use_links:
                # When links are provided, only consider shipments explicitly linked
                order_links = {
                    l["target_id"] for l in links
                    if l.get("name") == "order_shipment" and l.get("source_id") == order_id
                }
                if not order_links:
                    continue  # No link evidence for this order — skip
                all_shipments = shipments_by_order.get(order_id, [])
                linked = [s for s in all_shipments if s.get("id") in order_links]
            else:
                linked = shipments_by_order.get(order_id, [])
            shipped_total = sum(s.get("shipped_value") or 0.0 for s in linked)
            delta = order_value - shipped_total

            if abs(delta) <= order_value * self._REVENUE_THRESHOLD:
                continue

            severity = "high" if abs(delta) > order_value * 0.15 else "medium"
            direction = "under_shipped" if delta > 0 else "over_shipped"
            delta_pct = round(abs(delta) / order_value * 100, 1) if order_value else 0
            shipment_statuses = [s.get("status", "unknown") for s in linked]

            summary = explain_mismatch(
                order=order,
                shipment_count=len(linked),
                shipped_total=shipped_total,
                delta=delta,
                delta_pct=delta_pct,
                shipment_statuses=shipment_statuses,
                llm_client=self.llm_client,
            )

            out.append({
                "kind": f"order_shipment_mismatch_{direction}",
                "target_type": "Engagement",
                "target_id": order_id,
                "severity": severity,
                "summary": summary,
                "details": {
                    "order_value": order_value,
                    "shipped_total": shipped_total,
                    "delta": delta,
                    "delta_pct": delta_pct,
                    "shipment_count": len(linked),
                    "shipment_ids": [s.get("id") for s in linked],
                    "shipment_statuses": shipment_statuses,
                },
                "action_worthy": True,
            })

        return out

    # ------------------------------------------------------------------
    # Candidate action generation (deterministic via ActionRegistry)
    # ------------------------------------------------------------------
    def _candidate_action(self, finding: dict, tenant_id: str) -> Optional[dict]:
        kind = finding["kind"]
        target_type = finding["target_type"]
        target_id = finding["target_id"] or "unknown"

        action_type_map = {
            "missing_owner": "change_ownership",
            "overdue_money_event": "money_state_change",
            "blocked_engagement": "create_draft_action",
            "unresolved_critical_issue": "close_issue",
            "unacted_message": "send_communication",
            "orphaned_record": "create_draft_action",
            "order_shipment_mismatch_under_shipped": "create_draft_action",
            "order_shipment_mismatch_over_shipped": "create_draft_action",
        }
        action_type = action_type_map.get(kind, "create_draft_action")
        action = ActionRegistry.create(
            action_type=action_type,
            target_object_type=target_type,
            target_id=target_id,
            requested_by="TruthAnalyst",
            rationale=finding["summary"],
            status="draft",
            source_refs=[f"truth:{kind}:{target_id}"],
            action_id=f"pa-truth-{kind}-{target_id}",
        )
        return action.model_dump()

    # ------------------------------------------------------------------
    # Report builder
    # ------------------------------------------------------------------
    def _build_report(self, findings: list[dict]) -> str:
        if not findings:
            return "No truth findings — the ontology snapshot is consistent."
        lines = ["Truth Analysis Report:"]
        for f in findings:
            lines.append(f"- [{f['severity']}] {f['kind']}: {f['summary']}")
        return "\n".join(lines)
