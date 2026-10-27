"""RED contract: ActionIntent (LLM output) vs AuthorizedAction (control plane).

Expected to FAIL until both exist in src/ontology/action_types.py.
LLM output validates as Intent only; AuthorizedAction requires
tenant/mission/employee/actor/permissions/policy/risk/idempotency fields.
Idempotency key = tenant+mission+action_type+target+business_scope
(never thread+seq).
"""
import pytest
from pydantic import ValidationError

from src.ontology.action_types import ActionIntent, AuthorizedAction

INTENT_FIELDS = {
    "capability", "operation", "target_reference", "requested_parameters",
    "reason", "evidence_ids", "expected_outcome", "confidence", "requested_by",
}
CONTROL_PLANE_FIELDS = {
    "tenant_id", "mission_id", "employee_id", "actor_identity",
    "permissions", "policy_decision", "risk_tier", "idempotency_key",
}


def _llm_payload():
    # Arrange helper: what an LLM is allowed to emit — intent fields only
    return {
        "capability": "crm", "operation": "update_record",
        "target_reference": "acct-123",
        "requested_parameters": {"stage": "negotiation"},
        "reason": "Slack thread asks for stage update",
        "evidence_ids": ["ev-1"], "expected_outcome": "stage=negotiation",
        "confidence": 0.72, "requested_by": "llm-planner",
    }


class TestActionIntentContract:
    def test_intent_has_llm_fields(self):
        assert INTENT_FIELDS <= set(ActionIntent.model_fields)

    def test_authorized_action_requires_control_plane_fields(self):
        assert CONTROL_PLANE_FIELDS <= set(AuthorizedAction.model_fields)

    def test_llm_output_validates_as_intent_only(self):
        # Arrange
        payload = _llm_payload()
        # Act
        intent = ActionIntent.model_validate(payload)
        # Assert
        assert intent.operation == "update_record"
        with pytest.raises(ValidationError):
            AuthorizedAction.model_validate(payload)

    def test_idempotency_key_format_excludes_thread_seq(self):
        # Arrange: business-scoped key parts (no thread id / sequence number)
        key = "tenant-acme:mission-m1:update_record:acct-123:onboarding"
        # Act
        action = AuthorizedAction.model_validate({
            **_llm_payload(), "tenant_id": "tenant-acme", "mission_id": "mission-m1",
            "employee_id": "emp-1", "actor_identity": "human-approver",
            "permissions": ["crm.write"], "policy_decision": "approve",
            "risk_tier": "MEDIUM", "idempotency_key": key,
        })
        # Assert
        for part in ("tenant-acme", "mission-m1", "update_record", "acct-123"):
            assert part in action.idempotency_key
        assert "thread" not in action.idempotency_key
        assert "seq" not in action.idempotency_key

    def test_models_reject_extra_fields(self):
        assert ActionIntent.model_config.get("extra") == "forbid"
        assert AuthorizedAction.model_config.get("extra") == "forbid"
