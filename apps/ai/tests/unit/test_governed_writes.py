"""TDD tests for Governed Write Enforcement — OntologyAI V4.2 (Task 3).

These tests are written FIRST and must FAIL until ``src/ontology/governance.py``
is implemented.

Run:
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    uv run pytest tests/unit/test_governed_writes.py -v

Contract under test
-------------------
* A write to a property flagged ``requires_approval=True`` WITHOUT an associated
  ``PlannedAction`` raises :class:`GovernanceError`.
* A write below the blast-radius threshold proceeds without approval (no error,
  returns normally, underlying write executes).
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


# ---------------------------------------------------------------------------
# 1. requires_approval=True WITHOUT a PlannedAction -> raises GovernanceError
# ---------------------------------------------------------------------------
class TestGovernedWriteRequiresApproval:
    def test_write_to_requires_approval_property_without_planned_action_raises(self, monkeypatch):
        """A flagged property written without a PlannedAction must be blocked."""
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "Customer",
            {"mrr": {"requires_approval": True, "blast_radius": "high"}},
        )

        @governed_write(object_type="Customer", property_name="mrr")
        def write_mrr(customer_id: str, value: float) -> dict:
            write_mrr.executed = True
            return {"ok": True}

        write_mrr.executed = False
        with pytest.raises(GovernanceError):
            write_mrr("cust-1", 1000.0)

        # The underlying write must never have run.
        assert write_mrr.executed is False

    def test_positional_decorator_args_also_enforce(self, monkeypatch):
        """@governed_write("Customer", "mrr") (positional) must behave the same."""
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "Customer",
            {"mrr": {"requires_approval": True, "blast_radius": "high"}},
        )

        @governed_write("Customer", "mrr")
        def write_mrr(customer_id: str, value: float) -> dict:
            return {"ok": True}

        with pytest.raises(GovernanceError):
            write_mrr("cust-1", 1000.0)


# ---------------------------------------------------------------------------
# 2. write below blast-radius threshold -> proceeds without approval
# ---------------------------------------------------------------------------
class TestGovernedWriteBelowThreshold:
    def test_low_blast_radius_proceeds_without_approval(self, monkeypatch):
        """A low-blast-radius write commits directly with no PlannedAction."""
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "Deal",
            {"stage": {"requires_approval": False, "blast_radius": "low"}},
        )

        @governed_write(object_type="Deal", property_name="stage")
        def write_stage(deal_id: str, stage: str) -> dict:
            write_stage.executed = True
            return {"committed": True}

        write_stage.executed = False
        result = write_stage("deal-1", "negotiation")

        assert result == {"committed": True}
        assert write_stage.executed is True


# ---------------------------------------------------------------------------
# 3. write at/above threshold -> creates PlannedAction + blocks
# ---------------------------------------------------------------------------
class TestGovernedWriteAtOrAboveThreshold:
    def test_medium_blast_radius_creates_planned_action_and_blocks(self, monkeypatch):
        """A medium-blast-radius write produces exactly one PlannedAction and blocks."""
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "Incident",
            {"severity": {"requires_approval": False, "blast_radius": "medium"}},
        )

        created: list[PlannedAction] = []

        def create_planned_action(
            object_type: str,
            property_name: str,
            blast_radius: str,
            requested_by: str = "system",
            **kwargs,
        ) -> PlannedAction:
            pa = PlannedAction(
                id="pa-1",
                type=f"write:{object_type}.{property_name}",
                blast_radius=blast_radius,
                status="planned",
                requested_by=requested_by,
            )
            created.append(pa)
            return pa

        @governed_write(
            object_type="Incident",
            property_name="severity",
            create_planned_action=create_planned_action,
        )
        def write_severity(incident_id: str, severity: str) -> dict:
            write_severity.executed = True
            return {"committed": True}

        write_severity.executed = False
        result = write_severity("inc-1", "critical")

        # Exactly one PlannedAction must be produced.
        assert len(created) == 1
        assert isinstance(result, PlannedAction)
        assert result.blast_radius == "medium"
        assert result.status == "planned"

        # The underlying write must NOT silently commit.
        assert write_severity.executed is False

    def test_passed_planned_action_blocks_without_creating_new(self, monkeypatch):
        """If a PlannedAction is supplied, the write blocks using it (no new one)."""
        monkeypatch.setitem(
            OBJECT_WRITE_POLICY,
            "RevenueMetric",
            {"burn": {"requires_approval": True, "blast_radius": "high"}},
        )

        existing = PlannedAction(
            id="pa-existing",
            type="write:RevenueMetric.burn",
            blast_radius="high",
            status="planned",
            requested_by="FP&A",
        )

        @governed_write(object_type="RevenueMetric", property_name="burn")
        def write_burn(period: str, burn: float) -> dict:
            write_burn.executed = True
            return {"committed": True}

        write_burn.executed = False
        result = write_burn("2026-07", 50000.0, planned_action=existing)

        assert isinstance(result, PlannedAction)
        assert result.id == "pa-existing"
        assert write_burn.executed is False


# ---------------------------------------------------------------------------
# 4. Reference implementations — one governed write path per specialist
# ---------------------------------------------------------------------------
class TestGovernedWriteReferenceWrappers:
    def test_governed_fpa_cancel_requires_approval(self):
        """FP&A cancellation/collection action is governed (blocks without approval)."""
        from src.ontology.governance import governed_fpa_cancel

        with pytest.raises(GovernanceError):
            governed_fpa_cancel("cust-9", "payment failed")

    def test_governed_reliability_incident_update_creates_planned_action(self):
        """Reliability incident update produces a PlannedAction and blocks."""
        from src.ontology.governance import governed_reliability_incident_update

        created: list[PlannedAction] = []

        def create_planned_action(
            object_type: str,
            property_name: str,
            blast_radius: str,
            requested_by: str = "system",
            **kwargs,
        ) -> PlannedAction:
            pa = PlannedAction(
                id="pa-rel-1",
                type=f"write:{object_type}.{property_name}",
                blast_radius=blast_radius,
                status="planned",
                requested_by=requested_by,
            )
            created.append(pa)
            return pa

        result = governed_reliability_incident_update(
            "inc-42", "critical", create_planned_action=create_planned_action
        )
        assert len(created) == 1
        assert isinstance(result, PlannedAction)
        assert result.blast_radius == "medium"
