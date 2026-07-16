"""TDD tests for Governed Write Enforcement — OntologyAI V5.1 (PRD §18).

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_governed_writes.py -v

Contract under test
-------------------
* A write to a property flagged ``requires_approval=True`` WITHOUT an associated
  ``PlannedAction`` raises :class:`GovernanceError`.
* A write below the blast-radius threshold proceeds without approval.
* A write at/above the blast-radius threshold creates a ``PlannedAction`` record
  (exactly one is produced) and BLOCKS — the underlying write must NOT silently
  commit (HITL-style pattern mirroring Temporal ``AwaitWithTimeout``).
"""
import pytest

from src.ontology.governance import (
    GovernanceError,
    governed_write,
    OBJECT_WRITE_POLICY,
    PlannedAction,
)


class TestGovernedWriteRequiresApproval:
    def test_write_to_requires_approval_property_without_planned_action_raises(self, monkeypatch):
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "MoneyEvent",
            {"status": {"requires_approval": True, "blast_radius": "high"}},
        )

        @governed_write(object_type="MoneyEvent", property_name="status")
        def write_status(event_id: str, status: str) -> dict:
            write_status.executed = True
            return {"ok": True}

        write_status.executed = False
        with pytest.raises(GovernanceError):
            write_status("m-1", "paid")

        assert write_status.executed is False

    def test_positional_decorator_args_also_enforce(self, monkeypatch):
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "MoneyEvent",
            {"status": {"requires_approval": True, "blast_radius": "high"}},
        )

        @governed_write("MoneyEvent", "status")
        def write_status(event_id: str, status: str) -> dict:
            return {"ok": True}

        with pytest.raises(GovernanceError):
            write_status("m-1", "paid")


class TestGovernedWriteBelowThreshold:
    def test_low_blast_radius_proceeds_without_approval(self, monkeypatch):
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "Engagement",
            {"status": {"requires_approval": False, "blast_radius": "low"}},
        )

        @governed_write(object_type="Engagement", property_name="status")
        def write_status(engagement_id: str, status: str) -> dict:
            write_status.executed = True
            return {"committed": True}

        write_status.executed = False
        result = write_status("e-1", "active")

        assert result == {"committed": True}
        assert write_status.executed is True


class TestGovernedWriteAtOrAboveThreshold:
    def test_medium_blast_radius_creates_planned_action_and_blocks(self, monkeypatch):
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "Issue",
            {"status": {"requires_approval": True, "blast_radius": "medium"}},
        )

        created: list[PlannedAction] = []

        def create_planned_action(
            object_type: str, property_name: str, blast_radius: str,
            requested_by: str = "system", **kwargs,
        ) -> PlannedAction:
            pa = PlannedAction(
                id="pa-1", type=f"write:{object_type}.{property_name}",
                title="x", blast_radius=blast_radius, status="draft",
                requested_by=requested_by,
                target_object_type=object_type, target_id="i-1",
                rationale="x", requires_approval=True, source_refs=[],
            )
            created.append(pa)
            return pa

        @governed_write(
            object_type="Issue", property_name="status",
            create_planned_action=create_planned_action,
        )
        def write_status(issue_id: str, status: str) -> dict:
            write_status.executed = True
            return {"committed": True}

        write_status.executed = False
        result = write_status("i-1", "closed")

        assert len(created) == 1
        assert isinstance(result, PlannedAction)
        assert result.blast_radius == "medium"
        assert result.status == "draft"
        assert write_status.executed is False

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

        @governed_write(object_type="MoneyEvent", property_name="status")
        def write_status(event_id: str, status: str) -> dict:
            write_status.executed = True
            return {"committed": True}

        write_status.executed = False
        result = write_status("m-1", "paid", planned_action=existing)

        assert isinstance(result, PlannedAction)
        assert result.id == "pa-existing"
        assert write_status.executed is False


class TestGovernedWriteReferenceWrappers:
    def test_governed_money_state_change_requires_approval(self):
        from src.ontology.governance import governed_money_state_change

        with pytest.raises(GovernanceError):
            governed_money_state_change("m-9", "paid")

    def test_governed_issue_close_creates_planned_action(self):
        from src.ontology.governance import governed_issue_close

        created: list[PlannedAction] = []

        def create_planned_action(
            object_type: str, property_name: str, blast_radius: str,
            requested_by: str = "system", **kwargs,
        ) -> PlannedAction:
            pa = PlannedAction(
                id="pa-rel-1", type=f"write:{object_type}.{property_name}",
                title="x", blast_radius=blast_radius, status="draft",
                requested_by=requested_by,
                target_object_type=object_type, target_id="i-42",
                rationale="x", requires_approval=True, source_refs=[],
            )
            created.append(pa)
            return pa

        result = governed_issue_close(
            "i-42", "closed", create_planned_action=create_planned_action
        )
        assert len(created) == 1
        assert isinstance(result, PlannedAction)
        assert result.blast_radius == "medium"
