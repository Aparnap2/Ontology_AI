"""Integration tests for approval queue + StateStore with real Redis on localhost:6379."""

import os
import time
from unittest.mock import patch

import pytest


class TestApprovalQueueDocker:
    """Integration tests requiring a running Redis instance."""

    def test_statestore_redis_set_get(self):
        from src.services.state_store import StateStore, reset_redis_client

        reset_redis_client()
        store = StateStore(prefix="docktest-ss")
        try:
            store.set("foo", {"bar": 1})
            assert store.get("foo") == {"bar": 1}
        finally:
            store.clear_prefix()

    def test_statestore_redis_ttl(self):
        from src.services.state_store import StateStore, reset_redis_client

        reset_redis_client()
        store = StateStore(prefix="docktest-ttl")
        try:
            store.set("temp", "data", ttl=1)
            time.sleep(1.5)
            assert store.get("temp") is None
        finally:
            store.clear_prefix()

    def test_statestore_redis_increment(self):
        from src.services.state_store import StateStore, reset_redis_client

        reset_redis_client()
        store = StateStore(prefix="docktest-inc")
        try:
            store.increment("cnt")
            store.increment("cnt")
            store.increment("cnt")
            assert store.get("cnt") == 3
        finally:
            store.clear_prefix()

    def test_statestore_redis_delete_exists(self):
        from src.services.state_store import StateStore, reset_redis_client

        reset_redis_client()
        store = StateStore(prefix="docktest-del")
        try:
            store.set("x", "val")
            assert store.exists("x") is True
            store.delete("x")
            assert store.exists("x") is False
        finally:
            store.clear_prefix()

    def test_statestore_redis_clear_prefix(self):
        from src.services.state_store import StateStore, reset_redis_client

        reset_redis_client()
        store = StateStore(prefix="docktest-clear")
        store.set("a", 1)
        store.set("b", 2)
        store.set("c", 3)
        store.clear_prefix()
        assert store.get("a") is None
        assert store.get("b") is None
        assert store.get("c") is None

    def test_request_approval_persists_to_redis(self):
        from src.orchestrators.planned_action import PlannedAction
        from src.services.state_store import reset_redis_client
        from src.hitl import approval_queue as aq

        reset_redis_client()
        aq._pending_approvals.clear()
        aq._store.clear_prefix()

        action = PlannedAction(
            tenant_id="t1",
            actor="alice",
            action_type="post_slack_message",
            risk_level="low",
        )

        try:
            with patch(
                "src.integrations.slack.send_message_sync",
                return_value={"ok": True, "channel": "slack"},
            ):
                result = aq.request_approval(action)

            assert result["ok"] is True
            persisted = aq._store.get(f"pending:{action.id}")
            assert persisted is not None
            assert persisted["tenant_id"] == "t1"
            assert persisted["actor"] == "alice"
            assert persisted["action_type"] == "post_slack_message"
        finally:
            aq._store.clear_prefix()
            aq._pending_approvals.clear()

    def test_handle_approval_falls_back_to_redis(self):
        from src.orchestrators.planned_action import PlannedAction
        from src.services.state_store import reset_redis_client
        from src.hitl import approval_queue as aq

        reset_redis_client()
        aq._pending_approvals.clear()
        aq._store.clear_prefix()

        action = PlannedAction(
            tenant_id="t1",
            actor="bob",
            action_type="post_slack_message",
            risk_level="low",
        )

        try:
            with patch(
                "src.integrations.slack.send_message_sync",
                return_value={"ok": True, "channel": "slack"},
            ):
                aq.request_approval(action)

            # Simulate in-memory loss
            aq._pending_approvals.clear()

            result = aq.handle_approval_response(action.id, approved=True)
            assert result["ok"] is True
            assert result["action"]["status"] == "approved"
        finally:
            aq._store.clear_prefix()
            aq._pending_approvals.clear()

    def test_approval_lifecycle_approved(self):
        from src.orchestrators.planned_action import PlannedAction
        from src.services.state_store import reset_redis_client
        from src.hitl import approval_queue as aq

        reset_redis_client()
        aq._pending_approvals.clear()
        aq._store.clear_prefix()

        action = PlannedAction(
            tenant_id="t2",
            actor="carol",
            action_type="create_erpnext_issue",
            risk_level="medium",
            requires_approval=True,
        )

        try:
            with patch(
                "src.integrations.slack.send_message_sync",
                return_value={"ok": True, "channel": "slack"},
            ):
                aq.request_approval(action)

            result = aq.handle_approval_response(action.id, approved=True)
            assert result["ok"] is True
            assert result["action"]["status"] == "approved"
            assert result["action"]["executed_at"] is not None

            # Verify persisted via the same store instance used by the queue
            persisted = aq._store.get(f"pending:{action.id}")
            assert persisted["status"] == "approved"
            assert persisted["executed_at"] is not None
        finally:
            aq._store.clear_prefix()
            aq._pending_approvals.clear()

    def test_postgresql_connectivity(self):
        import psycopg2

        dsn = os.environ.get("TEST_DATABASE_URL")
        if not dsn:
            pytest.skip("TEST_DATABASE_URL is required for Postgres connectivity test")

        conn = psycopg2.connect(dsn)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1
            cur.close()
        finally:
            conn.close()
