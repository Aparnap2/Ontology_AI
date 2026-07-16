"""TDD tests for TruthAnalysisWorkflow (PRD §8.4 / §16.4).

Run FIRST — must FAIL, then implement truth_analysis_workflow.py to pass.

Key behaviors asserted:
  * deterministic findings fire (missing owner, overdue money event, blocked
    engagement, unresolved critical issue, unacted message, orphaned record),
  * LLM synthesis is mocked (not called in deterministic path),
  * candidate PlannedAction drafts produced for action-worthy items,
  * returns patches to truth_findings (+ optional planned_actions),
  * specialist="TruthAnalyst".
"""
import pytest

from src.schemas.specialist_response import SpecialistResponse


def _make_workflow(llm=None):
    from src.workflows.truth_analysis_workflow import TruthAnalysisWorkflow
    return TruthAnalysisWorkflow(llm_client=llm)


def _snapshot(**overrides):
    base = {
        "Party": [{"id": "p1", "kind": "customer", "name": "Acme",
                   "status": "active", "owner": None, "source_refs": ["n1"]}],
        "Engagement": [{"id": "e1", "kind": "deal", "title": "Deal",
                        "status": "blocked", "owner": "bob",
                        "value": 1000.0, "source_refs": ["n1"]}],
        "MoneyEvent": [{"id": "m1", "kind": "receivable", "amount": 500.0,
                        "currency": "USD", "status": "overdue",
                        "due_date": "2020-01-01", "source_refs": ["n1"]}],
        "Issue": [{"id": "i1", "kind": "blocker", "severity": "critical",
                   "status": "open", "owner": None, "summary": "stuck",
                   "source_refs": ["n1"]}],
        "Message": [{"id": "msg1", "channel": "email", "direction": "inbound",
                     "summary": "please help", "sentiment": "neutral",
                     "needs_action": True, "source_refs": ["n1"]}],
    }
    base.update(overrides)
    return base


class TestTruthDeterministicFindings:
    def test_missing_owner_finding(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      ontology_objects=_snapshot())
        findings = resp.engagement_state_patch["truth_findings"]
        kinds = {f["kind"] for f in findings}
        assert "missing_owner" in kinds

    def test_overdue_money_event_finding(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      ontology_objects=_snapshot())
        findings = resp.engagement_state_patch["truth_findings"]
        kinds = {f["kind"] for f in findings}
        assert "overdue_money_event" in kinds

    def test_blocked_engagement_finding(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      ontology_objects=_snapshot())
        kinds = {f["kind"] for f in resp.engagement_state_patch["truth_findings"]}
        assert "blocked_engagement" in kinds

    def test_unresolved_critical_issue_finding(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      ontology_objects=_snapshot())
        kinds = {f["kind"] for f in resp.engagement_state_patch["truth_findings"]}
        assert "unresolved_critical_issue" in kinds

    def test_unacted_message_finding(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      ontology_objects=_snapshot())
        kinds = {f["kind"] for f in resp.engagement_state_patch["truth_findings"]}
        assert "unacted_message" in kinds

    def test_orphaned_record_finding(self):
        # A MoneyEvent with no linked engagement is orphaned
        snap = _snapshot(
            MoneyEvent=[{"id": "m2", "kind": "payable", "amount": 10.0,
                         "currency": "USD", "status": "open",
                         "source_refs": ["n1"]}],
        )
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      ontology_objects=snap)
        kinds = {f["kind"] for f in resp.engagement_state_patch["truth_findings"]}
        assert "orphaned_record" in kinds


class TestTruthLLMIsMocked:
    def test_llm_synthesis_not_called_in_deterministic_path(self):
        calls = []

        class FakeLLM:
            def synthesize(self, *a, **k):
                calls.append(1)
                return "synthesized"

        wf = _make_workflow(llm=FakeLLM())
        wf.run(tenant_id="t1", engagement_id="e1",
               ontology_objects=_snapshot())
        # Deterministic findings must not require LLM; synthesis is optional
        # and only invoked when explicitly requested.
        assert calls == []

    def test_llm_synthesis_invoked_when_requested(self):
        calls = []

        class FakeLLM:
            def synthesize(self, *a, **k):
                calls.append(1)
                return "synthesized report"

        wf = _make_workflow(llm=FakeLLM())
        wf.run(tenant_id="t1", engagement_id="e1",
               ontology_objects=_snapshot(), synthesize=True)
        assert calls == [1]


class TestTruthCandidateActions:
    def test_candidate_actions_produced(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      ontology_objects=_snapshot())
        actions = resp.engagement_state_patch.get("planned_actions", [])
        assert actions, "action-worthy findings should produce candidate actions"
        # Each candidate action must be a valid PlannedAction dict
        from src.ontology.object_types import PlannedAction
        for a in actions:
            PlannedAction(**a)


class TestTruthResponse:
    def test_returns_truth_analyst_response(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      ontology_objects=_snapshot())
        assert isinstance(resp, SpecialistResponse)
        assert resp.specialist == "TruthAnalyst"
        assert resp.workflow_name == "TruthAnalysisWorkflow"
        assert "truth_findings" in resp.engagement_state_patch
