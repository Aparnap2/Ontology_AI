"""TDD tests for AgentBus and BaseAgent mesh primitives (V5.1).

Tests the typed peer-to-peer message bus and base agent send/receive:

  1. ``AgentMessage`` — constructor, to_dict(), from_dict(), default fields,
     thread_id fallback
  2. ``AgentBus.publish()`` — creates message with correct sender/recipient/
     type/payload
  3. ``AgentBus.deliver()`` — dispatches to registered handlers
  4. ``AgentBus.register()`` — registers handlers by message type
  5. ``AgentBus.drain()`` — drains unread from inbox list, marks read in-place
  6. ``get_bus()`` — returns singleton
  7. ``BaseAgent.send()`` — publishes to AgentBus, returns dict matching
     agent_inbox schema
  8. ``BaseAgent.receive()`` — drains and returns unread messages
  9. ``EngagementState.agent_inbox`` — exists, is in _ALLOWED_PATCH_KEYS,
     mergeable via merge_patch
 10. ``AGENT_REGISTRY`` — exactly 6 canonical agent names, correct mappings
 11. GovernanceWorkflow auto-allowed audit — low-blast action has
     governance_audit with auto_allowed=True
"""
import importlib.util
import sys
from unittest.mock import MagicMock, patch

# Mock structlog before any project import to avoid ModuleNotFoundError
# in the runtime.deployers -> config.database -> config.config_module chain.
_mock_structlog = MagicMock()
_mock_structlog.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _mock_structlog

# ── Direct module loading to bypass src.agents.__init__ import chain ─────
# src.agents/__init__.py triggers a deep import chain (cofounder -> services
# -> qdrant/temporalio/redis/aiokafka) that requires many external deps.
# We load agent_bus.py and base.py directly via importlib to avoid this.

_agent_bus_path = "src/agents/agent_bus.py"
_base_path = "src/agents/base.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_agent_bus_mod = _load_module("src.agents.agent_bus", _agent_bus_path)
_base_mod = _load_module("src.agents.base", _base_path)

AgentMessage = _agent_bus_mod.AgentMessage
AgentBus = _agent_bus_mod.AgentBus
get_bus = _agent_bus_mod.get_bus
BaseAgent = _base_mod.BaseAgent
AgentResult = _base_mod.AgentResult

import pytest


# ===========================================================================
# AgentMessage tests
# ===========================================================================

class TestAgentMessageConstruction:
    """AgentMessage constructor sets all fields correctly."""

    def test_constructor_sets_all_fields(self):
        msg = AgentMessage(
            sender="ChiefOfStaff",
            recipient="TruthAnalyst",
            message_type="request_fact_check",
            payload={"claim": "Revenue is up 20%"},
            thread_id="thread-abc",
        )
        assert msg.sender == "ChiefOfStaff"
        assert msg.recipient == "TruthAnalyst"
        assert msg.message_type == "request_fact_check"
        assert msg.payload == {"claim": "Revenue is up 20%"}
        assert msg.thread_id == "thread-abc"
        assert msg.id is not None
        assert len(msg.id) > 0
        assert msg.read is False
        assert "T" in msg.ts  # ISO format

    def test_thread_id_falls_back_to_id(self):
        """When thread_id is None, it defaults to the message id."""
        msg = AgentMessage(
            sender="A", recipient="B",
            message_type="ping", payload={},
        )
        assert msg.thread_id == msg.id

    def test_explicit_thread_id_differs_from_id(self):
        msg = AgentMessage(
            sender="A", recipient="B",
            message_type="ping", payload={},
            thread_id="explicit-thread",
        )
        assert msg.thread_id == "explicit-thread"
        assert msg.thread_id != msg.id

    def test_read_defaults_to_false(self):
        msg = AgentMessage(
            sender="A", recipient="B",
            message_type="ping", payload={},
        )
        assert msg.read is False

    def test_id_is_unique_per_message(self):
        msg1 = AgentMessage(sender="A", recipient="B", message_type="t", payload={})
        msg2 = AgentMessage(sender="A", recipient="B", message_type="t", payload={})
        assert msg1.id != msg2.id

    def test_empty_payload_allowed(self):
        msg = AgentMessage(
            sender="A", recipient="B",
            message_type="ping", payload={},
        )
        assert msg.payload == {}

    def test_none_payload_converted_to_empty(self):
        """from_dict with missing payload defaults to {}."""
        d = {"from": "A", "to": "B", "type": "ping"}
        msg = AgentMessage.from_dict(d)
        assert msg.payload == {}


class TestAgentMessageToDict:
    """AgentMessage.to_dict() serializes correctly."""

    def test_to_dict_contains_all_fields(self):
        msg = AgentMessage(
            sender="ChiefOfStaff",
            recipient="TruthAnalyst",
            message_type="request_fact_check",
            payload={"claim": "Revenue is up 20%"},
            thread_id="thread-abc",
        )
        d = msg.to_dict()
        assert d["from"] == "ChiefOfStaff"
        assert d["to"] == "TruthAnalyst"
        assert d["type"] == "request_fact_check"
        assert d["payload"] == {"claim": "Revenue is up 20%"}
        assert d["thread_id"] == "thread-abc"
        assert d["id"] == msg.id
        assert d["ts"] == msg.ts
        assert d["read"] is False

    def test_to_dict_uses_from_key(self):
        """The sender field is serialized as 'from' (reserved word workaround)."""
        msg = AgentMessage(
            sender="Governance", recipient="ChiefOfStaff",
            message_type="approval", payload={"action_id": "pa-1"},
        )
        d = msg.to_dict()
        assert "from" in d
        assert d["from"] == "Governance"
        assert "sender" not in d


class TestAgentMessageFromDict:
    """AgentMessage.from_dict() deserializes correctly."""

    def test_from_dict_round_trip(self):
        original = AgentMessage(
            sender="ChiefOfStaff",
            recipient="TruthAnalyst",
            message_type="request_fact_check",
            payload={"claim": "Revenue is up 20%"},
            thread_id="thread-abc",
        )
        d = original.to_dict()
        restored = AgentMessage.from_dict(d)
        assert restored.sender == original.sender
        assert restored.recipient == original.recipient
        assert restored.message_type == original.message_type
        assert restored.payload == original.payload
        assert restored.thread_id == original.thread_id
        assert restored.id == original.id
        assert restored.ts == original.ts
        assert restored.read == original.read

    def test_from_dict_minimal(self):
        """Minimal dict with only required fields."""
        d = {
            "from": "A",
            "to": "B",
            "type": "ping",
        }
        msg = AgentMessage.from_dict(d)
        assert msg.sender == "A"
        assert msg.recipient == "B"
        assert msg.message_type == "ping"
        assert msg.payload == {}
        assert msg.thread_id == msg.id  # falls back to id
        assert msg.read is False

    def test_from_dict_preserves_read_flag(self):
        d = {
            "from": "A", "to": "B", "type": "ping",
            "read": True,
        }
        msg = AgentMessage.from_dict(d)
        assert msg.read is True

    def test_from_dict_preserves_ts(self):
        d = {
            "from": "A", "to": "B", "type": "ping",
            "ts": "2026-07-23T12:00:00+00:00",
        }
        msg = AgentMessage.from_dict(d)
        assert msg.ts == "2026-07-23T12:00:00+00:00"

    def test_from_dict_preserves_id(self):
        d = {
            "from": "A", "to": "B", "type": "ping",
            "id": "custom-id-42",
        }
        msg = AgentMessage.from_dict(d)
        assert msg.id == "custom-id-42"


# ===========================================================================
# AgentBus tests
# ===========================================================================

class TestAgentBusPublish:
    """AgentBus.publish() creates messages with correct fields."""

    def test_publish_creates_message(self):
        bus = AgentBus()
        msg = bus.publish(
            sender="ChiefOfStaff",
            recipient="TruthAnalyst",
            message_type="request_fact_check",
            payload={"claim": "Revenue is up 20%"},
        )
        assert isinstance(msg, AgentMessage)
        assert msg.sender == "ChiefOfStaff"
        assert msg.recipient == "TruthAnalyst"
        assert msg.message_type == "request_fact_check"
        assert msg.payload == {"claim": "Revenue is up 20%"}

    def test_publish_with_thread_id(self):
        bus = AgentBus()
        msg = bus.publish(
            sender="A", recipient="B",
            message_type="ping", payload={},
            thread_id="my-thread",
        )
        assert msg.thread_id == "my-thread"

    def test_publish_returns_new_message_each_time(self):
        bus = AgentBus()
        m1 = bus.publish("A", "B", "ping", {})
        m2 = bus.publish("A", "B", "ping", {})
        assert m1.id != m2.id


class TestAgentBusRegister:
    """AgentBus.register() registers handlers by message type."""

    def test_register_adds_handler(self):
        bus = AgentBus()
        handler = MagicMock()
        bus.register("request_fact_check", handler)
        assert "request_fact_check" in bus._handlers
        assert handler in bus._handlers["request_fact_check"]

    def test_register_multiple_handlers_same_type(self):
        bus = AgentBus()
        h1 = MagicMock()
        h2 = MagicMock()
        bus.register("ping", h1)
        bus.register("ping", h2)
        assert len(bus._handlers["ping"]) == 2

    def test_register_different_types(self):
        bus = AgentBus()
        h1 = MagicMock()
        h2 = MagicMock()
        bus.register("ping", h1)
        bus.register("pong", h2)
        assert "ping" in bus._handlers
        assert "pong" in bus._handlers


class TestAgentBusDeliver:
    """AgentBus.deliver() dispatches to registered handlers."""

    def test_deliver_calls_handler(self):
        bus = AgentBus()
        handler = MagicMock()
        bus.register("ping", handler)
        msg = AgentMessage(sender="A", recipient="B", message_type="ping", payload={})
        bus.deliver(msg)
        handler.assert_called_once_with(msg)

    def test_deliver_calls_all_handlers(self):
        bus = AgentBus()
        h1 = MagicMock()
        h2 = MagicMock()
        bus.register("ping", h1)
        bus.register("ping", h2)
        msg = AgentMessage(sender="A", recipient="B", message_type="ping", payload={})
        bus.deliver(msg)
        h1.assert_called_once_with(msg)
        h2.assert_called_once_with(msg)

    def test_deliver_skips_unregistered_types(self):
        """Delivering an unregistered message type does nothing (no error)."""
        bus = AgentBus()
        handler = MagicMock()
        bus.register("ping", handler)
        msg = AgentMessage(sender="A", recipient="B", message_type="pong", payload={})
        bus.deliver(msg)
        handler.assert_not_called()

    def test_deliver_passes_message_object(self):
        bus = AgentBus()
        captured = []

        def handler(msg):
            captured.append(msg)

        bus.register("ping", handler)
        msg = AgentMessage(sender="A", recipient="B", message_type="ping", payload={"x": 1})
        bus.deliver(msg)
        assert len(captured) == 1
        assert captured[0].payload == {"x": 1}


class TestAgentBusDrain:
    """AgentBus.drain() drains unread messages and marks them read in-place."""

    def test_drain_returns_unread_messages(self):
        inbox = [
            {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": False},
            {"from": "C", "to": "D", "type": "pong", "payload": {}, "read": False},
        ]
        unread = AgentBus.drain(inbox)
        assert len(unread) == 2
        assert all(isinstance(m, AgentMessage) for m in unread)
        assert unread[0].sender == "A"
        assert unread[1].sender == "C"

    def test_drain_marks_read_in_place(self):
        inbox = [
            {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": False},
        ]
        AgentBus.drain(inbox)
        assert inbox[0]["read"] is True

    def test_drain_skips_already_read_messages(self):
        inbox = [
            {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": True},
            {"from": "C", "to": "D", "type": "pong", "payload": {}, "read": False},
        ]
        unread = AgentBus.drain(inbox)
        assert len(unread) == 1
        assert unread[0].sender == "C"

    def test_drain_empty_inbox(self):
        unread = AgentBus.drain([])
        assert unread == []

    def test_drain_all_read_returns_empty(self):
        inbox = [
            {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": True},
        ]
        unread = AgentBus.drain(inbox)
        assert unread == []

    def test_drain_preserves_message_fields(self):
        inbox = [
            {
                "from": "ChiefOfStaff",
                "to": "TruthAnalyst",
                "type": "request_fact_check",
                "payload": {"claim": "Revenue up"},
                "thread_id": "t-1",
                "id": "msg-1",
                "ts": "2026-07-23T12:00:00+00:00",
                "read": False,
            },
        ]
        unread = AgentBus.drain(inbox)
        assert len(unread) == 1
        m = unread[0]
        assert m.sender == "ChiefOfStaff"
        assert m.recipient == "TruthAnalyst"
        assert m.message_type == "request_fact_check"
        assert m.payload == {"claim": "Revenue up"}
        assert m.thread_id == "t-1"
        assert m.id == "msg-1"
        assert m.ts == "2026-07-23T12:00:00+00:00"

    def test_drain_idempotent_second_call_returns_empty(self):
        inbox = [
            {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": False},
        ]
        first = AgentBus.drain(inbox)
        assert len(first) == 1
        second = AgentBus.drain(inbox)
        assert second == []


class TestGetBus:
    """get_bus() returns the module-level singleton."""

    def test_get_bus_returns_agent_bus_instance(self):
        bus = get_bus()
        assert isinstance(bus, AgentBus)

    def test_get_bus_is_singleton(self):
        bus1 = get_bus()
        bus2 = get_bus()
        assert bus1 is bus2

    def test_get_bus_has_expected_methods(self):
        bus = get_bus()
        assert hasattr(bus, "publish")
        assert hasattr(bus, "deliver")
        assert hasattr(bus, "register")
        assert hasattr(bus, "drain")


# ===========================================================================
# BaseAgent tests
# ===========================================================================

class TestBaseAgentSend:
    """BaseAgent.send() publishes to AgentBus and returns a dict."""

    def test_send_returns_dict(self):
        agent = BaseAgent()
        agent.agent_name = "ChiefOfStaff"
        result = agent.send(
            recipient="TruthAnalyst",
            message_type="request_fact_check",
            payload={"claim": "Revenue is up 20%"},
        )
        assert isinstance(result, dict)

    def test_send_dict_has_correct_fields(self):
        agent = BaseAgent()
        agent.agent_name = "ChiefOfStaff"
        result = agent.send(
            recipient="TruthAnalyst",
            message_type="request_fact_check",
            payload={"claim": "Revenue is up 20%"},
        )
        assert result["from"] == "ChiefOfStaff"
        assert result["to"] == "TruthAnalyst"
        assert result["type"] == "request_fact_check"
        assert result["payload"] == {"claim": "Revenue is up 20%"}
        assert "id" in result
        assert "ts" in result
        assert "thread_id" in result
        assert result["read"] is False

    def test_send_with_thread_id(self):
        agent = BaseAgent()
        agent.agent_name = "ChiefOfStaff"
        result = agent.send(
            recipient="TruthAnalyst",
            message_type="request_fact_check",
            payload={},
            thread_id="custom-thread",
        )
        assert result["thread_id"] == "custom-thread"

    def test_send_uses_agent_name_as_sender(self):
        agent = BaseAgent()
        agent.agent_name = "Governance"
        result = agent.send(
            recipient="ChiefOfStaff",
            message_type="approval",
            payload={"action_id": "pa-1"},
        )
        assert result["from"] == "Governance"

    def test_send_result_compatible_with_agent_inbox(self):
        """The dict returned by send() can be appended to agent_inbox."""
        agent = BaseAgent()
        agent.agent_name = "ChiefOfStaff"
        msg_dict = agent.send(
            recipient="TruthAnalyst",
            message_type="request_fact_check",
            payload={"claim": "test"},
        )
        # Simulate appending to agent_inbox and draining
        inbox = [msg_dict]
        unread = AgentBus.drain(inbox)
        assert len(unread) == 1
        assert unread[0].sender == "ChiefOfStaff"
        assert unread[0].recipient == "TruthAnalyst"


class TestBaseAgentReceive:
    """BaseAgent.receive() drains and returns unread messages."""

    def test_receive_returns_list_of_dicts(self):
        agent = BaseAgent()
        inbox = [
            {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": False},
        ]
        messages = agent.receive(inbox)
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert isinstance(messages[0], dict)

    def test_receive_marks_read_in_place(self):
        agent = BaseAgent()
        inbox = [
            {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": False},
        ]
        agent.receive(inbox)
        assert inbox[0]["read"] is True

    def test_receive_skips_read_messages(self):
        agent = BaseAgent()
        inbox = [
            {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": True},
            {"from": "C", "to": "D", "type": "pong", "payload": {}, "read": False},
        ]
        messages = agent.receive(inbox)
        assert len(messages) == 1
        assert messages[0]["from"] == "C"

    def test_receive_empty_inbox(self):
        agent = BaseAgent()
        messages = agent.receive([])
        assert messages == []

    def test_receive_preserves_message_fields(self):
        agent = BaseAgent()
        inbox = [
            {
                "from": "ChiefOfStaff",
                "to": "TruthAnalyst",
                "type": "request_fact_check",
                "payload": {"claim": "Revenue up"},
                "thread_id": "t-1",
                "id": "msg-1",
                "ts": "2026-07-23T12:00:00+00:00",
                "read": False,
            },
        ]
        messages = agent.receive(inbox)
        assert len(messages) == 1
        m = messages[0]
        assert m["from"] == "ChiefOfStaff"
        assert m["to"] == "TruthAnalyst"
        assert m["type"] == "request_fact_check"
        assert m["payload"] == {"claim": "Revenue up"}
        assert m["thread_id"] == "t-1"
        assert m["id"] == "msg-1"


class TestBaseAgentAgentName:
    """BaseAgent has a default agent_name and it can be overridden."""

    def test_default_agent_name(self):
        agent = BaseAgent()
        assert agent.agent_name == "base_agent"

    def test_agent_name_can_be_set(self):
        agent = BaseAgent()
        agent.agent_name = "CustomAgent"
        assert agent.agent_name == "CustomAgent"


class TestBaseAgentRun:
    """BaseAgent.run() raises NotImplementedError."""

    def test_run_raises_not_implemented(self):
        agent = BaseAgent()
        with pytest.raises(NotImplementedError, match="Subclasses must implement run"):
            agent.run({}, {})


class TestAgentResult:
    """AgentResult dataclass has correct defaults."""

    def test_minimal_agent_result(self):
        r = AgentResult(tenant_id="t1")
        assert r.tenant_id == "t1"
        assert r.agent_name == "unknown"
        assert r.summary == ""
        assert r.output_json == {}
        assert r.agent_output_id is None
        assert r.qdrant_point_id is None

    def test_full_agent_result(self):
        r = AgentResult(
            tenant_id="t1",
            agent_name="TruthAnalyst",
            summary="Found 3 anomalies",
            output_json={"anomalies": [1, 2, 3]},
            agent_output_id="ao-1",
            qdrant_point_id="qp-1",
        )
        assert r.tenant_id == "t1"
        assert r.agent_name == "TruthAnalyst"
        assert r.summary == "Found 3 anomalies"
        assert r.output_json == {"anomalies": [1, 2, 3]}
        assert r.agent_output_id == "ao-1"
        assert r.qdrant_point_id == "qp-1"


# ===========================================================================
# EngagementState agent_inbox tests
# ===========================================================================

class TestEngagementStateAgentInbox:
    """EngagementState.agent_inbox exists and is patchable."""

    def test_agent_inbox_defaults_to_empty_list(self):
        from src.schemas.engagement_state import EngagementState
        state = EngagementState.create(
            engagement_id="e1", tenant_id="t1", workspace_mode="workspace",
        )
        assert state.agent_inbox == []

    def test_agent_inbox_in_allowed_patch_keys(self):
        from src.schemas.engagement_state import _ALLOWED_PATCH_KEYS
        assert "agent_inbox" in _ALLOWED_PATCH_KEYS

    def test_agent_inbox_can_be_merged_via_patch(self):
        from src.schemas.engagement_state import EngagementState
        state = EngagementState.create(
            engagement_id="e1", tenant_id="t1", workspace_mode="workspace",
        )
        msg = {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": False}
        merged = state.merge_patch({"agent_inbox": [msg]})
        assert len(merged.agent_inbox) == 1
        assert merged.agent_inbox[0]["from"] == "A"

    def test_agent_inbox_append_via_merge(self):
        from src.schemas.engagement_state import EngagementState
        state = EngagementState.create(
            engagement_id="e1", tenant_id="t1", workspace_mode="workspace",
        )
        m1 = {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": False}
        state = state.merge_patch({"agent_inbox": [m1]})
        m2 = {"from": "C", "to": "D", "type": "pong", "payload": {}, "read": False}
        merged = state.merge_patch({"agent_inbox": [m2]})
        assert len(merged.agent_inbox) == 2

    def test_agent_inbox_immutability_of_original(self):
        from src.schemas.engagement_state import EngagementState
        state = EngagementState.create(
            engagement_id="e1", tenant_id="t1", workspace_mode="workspace",
        )
        msg = {"from": "A", "to": "B", "type": "ping", "payload": {}, "read": False}
        state.merge_patch({"agent_inbox": [msg]})
        assert state.agent_inbox == []


# ===========================================================================
# AGENT_REGISTRY tests
# ===========================================================================

class TestAgentRegistry:
    """AGENT_REGISTRY contains exactly 6 canonical agent names."""

    def test_agent_registry_has_exactly_6_entries(self):
        from src.workflows import AGENT_REGISTRY
        assert len(AGENT_REGISTRY) == 6

    def test_agent_registry_has_correct_names(self):
        from src.workflows import AGENT_REGISTRY
        expected = {
            "ChiefOfStaff",
            "Discovery",
            "OntologyMapper",
            "TruthAnalyst",
            "WorkflowBuilder",
            "Governance",
        }
        assert set(AGENT_REGISTRY.keys()) == expected

    def test_agent_registry_maps_to_correct_workflows(self):
        from src.workflows import AGENT_REGISTRY
        from src.workflows.chief_of_staff_workflow import ChiefOfStaffWorkflow
        from src.workflows.discovery_workflow import DiscoveryWorkflow
        from src.workflows.ontology_mapping_workflow import OntologyMappingWorkflow
        from src.workflows.truth_analysis_workflow import TruthAnalysisWorkflow
        from src.workflows.workflow_builder_workflow import WorkflowBuilderWorkflow
        from src.workflows.governance_workflow import GovernanceWorkflow

        assert AGENT_REGISTRY["ChiefOfStaff"] is ChiefOfStaffWorkflow
        assert AGENT_REGISTRY["Discovery"] is DiscoveryWorkflow
        assert AGENT_REGISTRY["OntologyMapper"] is OntologyMappingWorkflow
        assert AGENT_REGISTRY["TruthAnalyst"] is TruthAnalysisWorkflow
        assert AGENT_REGISTRY["WorkflowBuilder"] is WorkflowBuilderWorkflow
        assert AGENT_REGISTRY["Governance"] is GovernanceWorkflow

    def test_agent_registry_each_has_run_or_orchestrate_method(self):
        """Each agent in the registry has a run() or orchestrate() entry point.
        
        ChiefOfStaffCore exposes orchestrate() (Temporal wrapper adds run()).
        All other canonical workflows expose run() directly.
        """
        from src.workflows import AGENT_REGISTRY
        for name, wf_cls in AGENT_REGISTRY.items():
            has_entry = hasattr(wf_cls, "run") or hasattr(wf_cls, "orchestrate")
            assert has_entry, f"{name} missing run() or orchestrate()"

    def test_agent_registry_no_legacy_names(self):
        from src.workflows import AGENT_REGISTRY
        legacy = {
            "Pulse", "Investor", "FPA", "GrowthAnalytics",
            "Reliability", "Comms", "QA", "Finance", "Data", "Ops",
        }
        assert not (set(AGENT_REGISTRY.keys()) & legacy)


# ===========================================================================
# GovernanceWorkflow auto-allowed audit tests
# ===========================================================================

class TestGovernanceAutoAllowedAudit:
    """Low-blast auto-allowed action has governance_audit with auto_allowed=True."""

    def test_low_blast_action_has_auto_allowed_audit(self):
        from src.workflows.governance_workflow import GovernanceWorkflow
        from src.ontology.object_types import PlannedAction

        wf = GovernanceWorkflow()
        action = PlannedAction(
            id="pa-audit-1", type="create_note", title="Add note",
            blast_radius="low", status="draft", requested_by="bob",
            target_object_type="Party", target_id="p1", rationale="note",
            requires_approval=False, source_refs=[],
        )
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            planned_actions=[action.model_dump()],
        )
        actions = resp.engagement_state_patch["planned_actions"]
        assert len(actions) == 1
        assert actions[0]["status"] == "completed"
        audit = actions[0].get("governance_audit", {})
        assert audit.get("auto_allowed") is True
        assert audit.get("blast_radius") == "low"
        assert audit.get("ruling") == "auto_execute"

    def test_high_blast_action_has_no_auto_allowed_audit(self):
        from src.workflows.governance_workflow import GovernanceWorkflow
        from src.ontology.object_types import PlannedAction

        wf = GovernanceWorkflow()
        action = PlannedAction(
            id="pa-audit-2", type="money_state_change", title="Change money",
            blast_radius="high", status="draft", requested_by="bob",
            target_object_type="MoneyEvent", target_id="m1", rationale="money",
            requires_approval=True, source_refs=[],
        )
        resp = wf.run(
            tenant_id="t1", engagement_id="e1",
            planned_actions=[action.model_dump()],
        )
        actions = resp.engagement_state_patch["planned_actions"]
        assert len(actions) == 1
        assert actions[0]["status"] == "pending_approval"
        assert "governance_audit" not in actions[0]