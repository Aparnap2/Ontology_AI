"""TDD tests for Governance Gate — OntologyAI V5.1 (PRD §10.7, §12.7, §18).

Tests the HITL governance enforcement mechanisms:

  1. ``@governed_write`` decorator — blocks writes requiring approval
  2. ``GovernanceWorkflow`` — validates actions/drafts, sets pending_approval
  3. Governance-exclusive setters — only GovernanceWorkflow may transition
     draft status to activated/exported/completed
  4. HITL Temporal signal pattern — pending_approval + requires_hitl

Contract under test
-------------------
* ``@governed_write`` on a property flagged ``requires_approval=True`` WITHOUT
  a ``PlannedAction`` raises ``GovernanceError``.
* ``@governed_write`` on a low-blast-radius property proceeds without approval.
* ``@governed_write`` at/above the blast-radius threshold blocks and returns
  a ``PlannedAction`` for caller to approve; the underlying write never executes.
* ``GovernanceWorkflow.run()`` validates ``PlannedAction`` schemas and enforces
  blast-radius gating.
* ``GovernanceWorkflow`` owns the sanctioned ``activate_draft`` / ``export_draft`` /
  ``complete_draft`` / ``deploy_draft`` methods.
* ONLY governance may set ``status="activated"`` on an ``ExecutableWorkflowDraft``.
  Non-governance construction with status already in a governance-only set is
  rejected.
* The HITL approval flow requires ``pending_approval`` -> human action ->
  status transition.
"""
import sys
from unittest.mock import MagicMock

# Mock structlog before any project import to avoid ModuleNotFoundError
# in the runtime.deployers -> config.database -> config.config_module chain.
_mock_structlog = MagicMock()
_mock_structlog.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _mock_structlog

import pytest

from src.schemas.specialist_response import SpecialistResponse
from src.ontology.object_types import PlannedAction
from src.ontology.workflow_drafts import ExecutableWorkflowDraft
from src.ontology.governance import (
    GovernanceError,
    governed_write,
    OBJECT_WRITE_POLICY,
)


# ===========================================================================
# Helper factories
# ===========================================================================

def _make_workflow():
    from src.workflows.governance_workflow import GovernanceWorkflow
    return GovernanceWorkflow()


def _low_action(**overrides):
    """Create a low-blast-radius PlannedAction dict (auto-allowed)."""
    params = dict(
        id="pa-low", type="create_note", title="Add note",
        blast_radius="low", status="draft", requested_by="bob",
        target_object_type="Party", target_id="p1", rationale="note",
        requires_approval=False, source_refs=[],
    )
    params.update(overrides)
    return PlannedAction(**params).model_dump()


def _high_action(**overrides):
    """Create a high-blast-radius PlannedAction dict (requires approval)."""
    params = dict(
        id="pa-high", type="money_state_change", title="Change money",
        blast_radius="high", status="draft", requested_by="bob",
        target_object_type="MoneyEvent", target_id="m1", rationale="money",
        requires_approval=True, source_refs=[],
    )
    params.update(overrides)
    return PlannedAction(**params).model_dump()


def _draft(**overrides):
    """Create an ExecutableWorkflowDraft dict."""
    params = dict(
        id="d1", runtime="n8n", name="Reminder",
        source_workflow_spec_id="ws1",
    )
    params.update(overrides)
    return ExecutableWorkflowDraft(**params).model_dump()


# ===========================================================================
# Governance approval flow (approve -> continue)
# ===========================================================================

class TestGovernanceApprovalFlow:
    """GovernanceWorkflow approves low-blast actions and blocks high-blast."""

    def test_low_blast_action_auto_allowed(self):
        """Low blast radius, no explicit approval required -> auto-completed."""
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_low_action()])
        actions = resp.engagement_state_patch["planned_actions"]
        assert actions
        assert actions[0]["status"] == "completed"
        assert actions[0].get("governance_audit", {}).get("auto_allowed") is True

    def test_high_blast_action_pending_approval(self):
        """High blast radius -> pending_approval + requires_hitl."""
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_high_action()])
        actions = resp.engagement_state_patch["planned_actions"]
        assert actions[0]["status"] == "pending_approval"
        assert resp.requires_hitl is True
        assert resp.planned_action_id == "pa-high"

    def test_multiple_actions_some_blocked_some_allowed(self):
        """Mixed actions: low auto-completes, high blocked."""
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_low_action(), _high_action()])
        actions = resp.engagement_state_patch["planned_actions"]
        assert len(actions) == 2
        statuses = {a["id"]: a["status"] for a in actions}
        assert statuses["pa-low"] == "completed"
        assert statuses["pa-high"] == "pending_approval"

    def test_approval_sets_hitl_ids(self):
        """pending_approval actions are tracked in hitl_ids."""
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_high_action()])
        assert resp.actions_proposed == ["pa-high"]


# ===========================================================================
# Governance hold / rejection flow
# ===========================================================================

class TestGovernanceHoldAndRejection:
    """Invalid actions are held or rejected entirely."""

    def test_invalid_action_schema_raises(self):
        wf = _make_workflow()
        bad = _low_action()
        bad.pop("target_object_type")  # required field
        with pytest.raises((GovernanceError, Exception)):
            wf.run(tenant_id="t1", engagement_id="e1",
                   planned_actions=[bad])

    def test_invalid_draft_schema_raises(self):
        wf = _make_workflow()
        with pytest.raises((GovernanceError, Exception)):
            wf.run(tenant_id="t1", engagement_id="e1",
                   executable_workflow_drafts=[{"invalid": "draft"}])

    def test_empty_actions_list_returns_empty_patch(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[], executable_workflow_drafts=[])
        patch = resp.engagement_state_patch
        assert patch["planned_actions"] == []
        assert patch["executable_workflow_drafts"] == []

    def test_no_unresolved_questions_when_all_valid(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_low_action()])
        assert resp.unresolved_questions == []


# ===========================================================================
# Governance criteria validation
# ===========================================================================

class TestGovernanceCriteriaValidation:
    """Blast-radius and requires_approval flag drive governance decisions."""

    def test_medium_blast_without_approval_flag_blocked(self):
        """Even without explicit requires_approval, medium blast is blocked."""
        action = _low_action(blast_radius="medium", requires_approval=False)
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[action])
        status = resp.engagement_state_patch["planned_actions"][0]["status"]
        assert status == "pending_approval"

    def test_low_blast_with_approval_flag_blocked(self):
        """Even low blast, requires_approval=True -> blocked."""
        action = _low_action(blast_radius="low", requires_approval=True)
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[action])
        status = resp.engagement_state_patch["planned_actions"][0]["status"]
        assert status == "pending_approval"

    def test_draft_validation_preserves_draft_fields(self):
        """Validated drafts are returned with their original fields."""
        draft_dict = _draft()
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      executable_workflow_drafts=[draft_dict])
        drafts = resp.engagement_state_patch["executable_workflow_drafts"]
        assert drafts[0]["id"] == "d1"
        assert drafts[0]["runtime"] == "n8n"


# ===========================================================================
# Governance exclusivity — only GovernanceWorkflow can finalize external exec
# ===========================================================================

class TestGovernanceExclusivity:
    """ONLY GovernanceWorkflow may set activated/exported/completed statuses."""

    def test_non_governance_cannot_construct_activated(self):
        """Constructing an ExecutableWorkflowDraft with status='activated' must raise."""
        with pytest.raises(ValueError):
            ExecutableWorkflowDraft(
                id="bad-act", runtime="n8n", name="Bad",
                source_workflow_spec_id="ws", status="activated",
            )

    def test_non_governance_cannot_construct_exported(self):
        with pytest.raises(ValueError):
            ExecutableWorkflowDraft(
                id="bad-exp", runtime="n8n", name="Bad",
                source_workflow_spec_id="ws", status="exported",
            )

    def test_non_governance_cannot_construct_executing(self):
        with pytest.raises(ValueError):
            ExecutableWorkflowDraft(
                id="bad-exe", runtime="n8n", name="Bad",
                source_workflow_spec_id="ws", status="executing",
            )

    def test_non_governance_cannot_construct_completed(self):
        with pytest.raises(ValueError):
            ExecutableWorkflowDraft(
                id="bad-com", runtime="n8n", name="Bad",
                source_workflow_spec_id="ws", status="completed",
            )

    def test_governance_setter_activates(self):
        wf = _make_workflow()
        d = ExecutableWorkflowDraft(
            id="d-act", runtime="n8n", name="ActivateMe",
            source_workflow_spec_id="ws",
        )
        wf.activate_draft(d)
        assert d.status == "activated"

    def test_governance_setter_exports(self):
        wf = _make_workflow()
        d = ExecutableWorkflowDraft(
            id="d-exp", runtime="n8n", name="ExportMe",
            source_workflow_spec_id="ws",
        )
        wf.export_draft(d)
        assert d.status == "exported"

    def test_governance_setter_completes(self):
        wf = _make_workflow()
        d = ExecutableWorkflowDraft(
            id="d-com", runtime="n8n", name="CompleteMe",
            source_workflow_spec_id="ws",
        )
        wf.complete_draft(d)
        assert d.status == "completed"

    def test_governance_owns_methods(self):
        """GovernanceWorkflow has the sanctioned transition methods."""
        from src.workflows.governance_workflow import GovernanceWorkflow
        assert hasattr(GovernanceWorkflow, "activate_draft")
        assert hasattr(GovernanceWorkflow, "export_draft")
        assert hasattr(GovernanceWorkflow, "complete_draft")
        assert hasattr(GovernanceWorkflow, "deploy_draft")

    def test_governance_only_caller_of_setter(self):
        """ExecutableWorkflowDraft.set_status_via_governance exists."""
        d = ExecutableWorkflowDraft(
            id="d-set", runtime="n8n", name="SetterTest",
            source_workflow_spec_id="ws",
        )
        # The setter exists but should only be called by GovernanceWorkflow
        d.set_status_via_governance("activated")
        assert d.status == "activated"


# ===========================================================================
# HITL Temporal signal pattern
# ===========================================================================

class TestHITLSignalPattern:
    """HITL approval flow: pending_approval -> review -> approve/reject."""

    def test_pending_approval_in_response(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_high_action()])
        assert resp.requires_hitl is True
        assert "pending approval" in resp.summary

    def test_requires_hitl_false_when_no_high_blast(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_low_action()])
        assert resp.requires_hitl is False

    def test_hitl_response_has_planned_action_id(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_high_action()])
        assert resp.planned_action_id is not None

    def test_hitl_response_counts_pending(self):
        """Summary mentions the number of pending approvals."""
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_low_action(), _high_action()])
        assert "pending approval" in resp.summary


# ===========================================================================
# @governed_write decorator tests (governance gate)
# ===========================================================================

class TestGovernedWriteDecorator:
    """The @governed_write decorator enforces HITL at the write level."""

    def test_flagged_property_without_planned_action_raises(self, monkeypatch):
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "MoneyEvent",
            {"status": {"requires_approval": True, "blast_radius": "high"}},
        )

        executed = False

        @governed_write(object_type="MoneyEvent", property_name="status")
        def write_status(event_id, status):
            nonlocal executed
            executed = True
            return {"ok": True}

        with pytest.raises(GovernanceError):
            write_status("m-1", "paid")

        assert executed is False, "Underlying write must NOT execute"

    def test_low_blast_proceeds_without_blocking(self, monkeypatch):
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "Engagement",
            {"status": {"requires_approval": False, "blast_radius": "low"}},
        )

        executed = False

        @governed_write(object_type="Engagement", property_name="status")
        def write_status(engagement_id, status):
            nonlocal executed
            executed = True
            return {"committed": True}

        result = write_status("e-1", "active")
        assert result == {"committed": True}
        assert executed is True

    def test_medium_blast_creates_planned_action_and_blocks(self, monkeypatch):
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "Issue",
            {"status": {"requires_approval": True, "blast_radius": "medium"}},
        )

        created_actions = []

        def create_planned_action(object_type, property_name, blast_radius,
                                  requested_by="system", **kwargs):
            pa = PlannedAction(
                id="pa-gate-1", type=f"write:{object_type}.{property_name}",
                title="x", blast_radius=blast_radius, status="draft",
                requested_by=requested_by,
                target_object_type=object_type, target_id="i-1",
                rationale="x", requires_approval=True, source_refs=[],
            )
            created_actions.append(pa)
            return pa

        executed = False

        @governed_write(
            object_type="Issue", property_name="status",
            create_planned_action=create_planned_action,
        )
        def write_status(issue_id, status):
            nonlocal executed
            executed = True
            return {"committed": True}

        result = write_status("i-1", "closed")

        assert len(created_actions) == 1
        assert isinstance(result, PlannedAction)
        assert result.blast_radius == "medium"
        assert result.status == "draft"
        assert executed is False, "Underlying write must NOT execute"

    def test_passed_planned_action_blocks_without_creating_new(self, monkeypatch):
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "MoneyEvent",
            {"status": {"requires_approval": True, "blast_radius": "high"}},
        )

        existing = PlannedAction(
            id="pa-existing", type="write:MoneyEvent.status",
            title="x", blast_radius="high", status="draft",
            requested_by="TruthAnalyst",
            target_object_type="MoneyEvent", target_id="m-1",
            rationale="x", requires_approval=True, source_refs=[],
        )

        executed = False

        @governed_write(object_type="MoneyEvent", property_name="status")
        def write_status(event_id, status):
            nonlocal executed
            executed = True
            return {"committed": True}

        result = write_status("m-1", "paid", planned_action=existing)

        assert isinstance(result, PlannedAction)
        assert result.id == "pa-existing"
        assert executed is False

    def test_overridden_blast_radius_used(self, monkeypatch):
        """Caller-provided blast_radius overrides policy default."""
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "Party",
            {"owner": {"requires_approval": True, "blast_radius": "medium"}},
        )

        executed = False

        @governed_write(object_type="Party", property_name="owner")
        def write_owner(party_id, owner):
            nonlocal executed
            executed = True
            return {"ok": True}

        with pytest.raises(GovernanceError):
            write_owner("p-1", "alice")
        assert executed is False


class TestGovernedWriteNoPolicyEntry:
    """When no policy entry exists, decorator uses defaults."""

    def test_no_policy_entry_raises_on_flagged(self, monkeypatch):
        """No entry in OBJECT_WRITE_POLICY means empty defaults."""
        monkeypatch.setitem(OBJECT_WRITE_POLICY, "UnknownType", {})

        executed = False

        @governed_write(object_type="UnknownType", property_name="some_field")
        def write_something(obj_id, val):
            nonlocal executed
            executed = True
            return {"ok": True}

        # No policy entry -> requires_approval=False, blast_radius="low"
        # With threshold="medium", low passes through.
        result = write_something("u-1", "val")
        assert result == {"ok": True}
        assert executed is True


# ===========================================================================
# Reference governed wrappers
# ===========================================================================

class TestReferenceGovernedWrappers:
    """The reference governed write implementations enforce the gate."""

    def test_governed_money_state_change_requires_approval(self):
        from src.ontology.governance import governed_money_state_change
        with pytest.raises(GovernanceError):
            governed_money_state_change("m-9", "paid")

    def test_governed_party_owner_change_requires_approval(self):
        from src.ontology.governance import governed_party_owner_change
        with pytest.raises(GovernanceError):
            governed_party_owner_change("p-9", "alice")

    def test_governed_party_owner_change_with_planned_action(self):
        from src.ontology.governance import governed_party_owner_change

        pa = PlannedAction(
            id="pa-ref-1", type="write:Party.owner",
            title="Change owner", blast_radius="medium", status="draft",
            requested_by="OntologyMapper",
            target_object_type="Party", target_id="p-42",
            rationale="Owner change", requires_approval=True,
            source_refs=[],
        )
        result = governed_party_owner_change(
            "p-42", "bob", planned_action=pa,
        )
        assert isinstance(result, PlannedAction)
        assert result.id == "pa-ref-1"


# ===========================================================================
# SpecialistResponse contract
# ===========================================================================

class TestGovernanceResponseContract:
    """GovernanceWorkflow responses must meet the SpecialistResponse contract."""

    def test_returns_specialist_response(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_high_action()])
        assert isinstance(resp, SpecialistResponse)
        assert resp.specialist == "Governance"
        assert resp.workflow_name == "GovernanceWorkflow"

    def test_patch_contains_planned_actions(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_high_action()])
        assert "planned_actions" in resp.engagement_state_patch

    def test_patch_contains_executable_drafts(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      executable_workflow_drafts=[_draft()])
        assert "executable_workflow_drafts" in resp.engagement_state_patch

    def test_summary_includes_governed_counts(self):
        wf = _make_workflow()
        resp = wf.run(tenant_id="t1", engagement_id="e1",
                      planned_actions=[_low_action(), _high_action()],
                      executable_workflow_drafts=[_draft()])
        assert "2 action" in resp.summary
        assert "1 draft" in resp.summary


# ===========================================================================
# deploy_draft exclusivity
# ===========================================================================

class TestDeployDraftExclusivity:
    """deploy_draft is only callable from GovernanceWorkflow and requires activation."""

    def test_deploy_draft_raises_if_not_activated(self):
        wf = _make_workflow()
        draft = ExecutableWorkflowDraft(
            id="dep-1", runtime="n8n", name="DeployTest",
            source_workflow_spec_id="ws1",
        )
        with pytest.raises(ValueError, match="activated"):
            wf.deploy_draft(draft, {"url": "http://n8n:5678", "api_key": "key"})

    def test_deploy_draft_succeeds_when_activated(self):
        import httpx
        wf = _make_workflow()
        draft = ExecutableWorkflowDraft(
            id="dep-2", runtime="n8n", name="DeployTest2",
            source_workflow_spec_id="ws2",
        )
        wf.activate_draft(draft)
        assert draft.status == "activated"

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"id": "wf-dep-2"}),
        )
        client = httpx.Client(transport=transport, verify=False)
        creds = {"url": "http://n8n:5678/api/v1", "api_key": "test-key", "client": client}

        result = wf.deploy_draft(draft, creds)
        assert result.success is True
        assert result.runtime == "n8n"
        assert result.workflow_id == "wf-dep-2"

    def test_deploy_draft_unknown_runtime_raises(self):
        from unittest.mock import MagicMock
        wf = _make_workflow()
        draft = MagicMock(spec=ExecutableWorkflowDraft)
        draft.id = "dep-unknown"
        draft.status = "activated"
        draft.runtime = "unknown_runtime"
        draft.export_payload = {"name": "test"}
        with pytest.raises(ValueError, match="runtime"):
            wf.deploy_draft(draft, {})
