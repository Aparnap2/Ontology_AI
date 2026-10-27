"""Integration tests for SlackAlertForwarder with real Redis and Mockoon."""

import os
from unittest.mock import patch

import pytest
from src.states.schemas import MissionStateV2, SupportHealth


class TestSlackAlertForwarderDocker:
    """Integration tests requiring a running Redis instance."""

    def test_forward_delivers_with_real_redis(self):
        from src.services.state_store import StateStore, reset_redis_client
        from src.notifications.slack_alert_forwarder import SlackAlertForwarder

        reset_redis_client()
        store = StateStore(prefix="inttest-af")
        fwd = SlackAlertForwarder(store=store)
        try:
            state = MissionStateV2(
                tenant_id="int-tenant-1",
                run_id="int-run-1",
                overall_health=SupportHealth.CRITICAL,
            )
            with patch(
                "src.integrations.slack.send_message_sync",
                return_value={"ok": True, "channel": "slack"},
            ):
                result = fwd.forward_mission_alert(state)

            assert result["ok"] is True
            assert result.get("skipped") is not True
            assert store.exists("alert:sent:int-tenant-1:critical") is True
        finally:
            store.clear_prefix()

    def test_forward_dedup_with_real_redis(self):
        from src.services.state_store import StateStore, reset_redis_client
        from src.notifications.slack_alert_forwarder import SlackAlertForwarder

        reset_redis_client()
        store = StateStore(prefix="inttest-dedup")
        fwd = SlackAlertForwarder(store=store)
        try:
            state = MissionStateV2(
                tenant_id="dedup-tenant",
                run_id="run-dedup",
                overall_health=SupportHealth.ATTENTION,
            )
            with patch(
                "src.integrations.slack.send_message_sync",
                return_value={"ok": True, "channel": "slack"},
            ):
                result1 = fwd.forward_mission_alert(state)
                result2 = fwd.forward_mission_alert(state)

            assert result1["ok"] is True
            assert result1.get("skipped") is not True
            assert result2["skipped"] is True
            assert result2["reason"] == "duplicate"
        finally:
            store.clear_prefix()

    def test_forward_different_healths_no_dedup(self):
        from src.services.state_store import StateStore, reset_redis_client
        from src.notifications.slack_alert_forwarder import SlackAlertForwarder

        reset_redis_client()
        store = StateStore(prefix="inttest-diff")
        fwd = SlackAlertForwarder(store=store)
        try:
            state_crit = MissionStateV2(
                tenant_id="diff-tenant",
                run_id="run-crit",
                overall_health=SupportHealth.CRITICAL,
            )
            state_attn = MissionStateV2(
                tenant_id="diff-tenant",
                run_id="run-attn",
                overall_health=SupportHealth.ATTENTION,
            )
            with patch(
                "src.integrations.slack.send_message_sync",
                return_value={"ok": True, "channel": "slack"},
            ):
                r1 = fwd.forward_mission_alert(state_crit)
                r2 = fwd.forward_mission_alert(state_attn)

            assert r1.get("skipped") is not True
            assert r2.get("skipped") is not True
            assert store.exists("alert:sent:diff-tenant:critical") is True
            assert store.exists("alert:sent:diff-tenant:attention") is True
        finally:
            store.clear_prefix()

    def test_forward_different_tenants_no_dedup(self):
        from src.services.state_store import StateStore, reset_redis_client
        from src.notifications.slack_alert_forwarder import SlackAlertForwarder

        reset_redis_client()
        store = StateStore(prefix="inttest-tenants")
        fwd = SlackAlertForwarder(store=store)
        try:
            t1 = MissionStateV2(
                tenant_id="tenant-a",
                run_id="r1",
                overall_health=SupportHealth.CRITICAL,
            )
            t2 = MissionStateV2(
                tenant_id="tenant-b",
                run_id="r2",
                overall_health=SupportHealth.CRITICAL,
            )
            with patch(
                "src.integrations.slack.send_message_sync",
                return_value={"ok": True, "channel": "slack"},
            ):
                r1 = fwd.forward_mission_alert(t1)
                r2 = fwd.forward_mission_alert(t2)

            assert r1.get("skipped") is not True
            assert r2.get("skipped") is not True
            assert store.exists("alert:sent:tenant-a:critical") is True
            assert store.exists("alert:sent:tenant-b:critical") is True
        finally:
            store.clear_prefix()

    def test_forward_good_health_no_redis_write(self):
        from src.services.state_store import StateStore, reset_redis_client
        from src.notifications.slack_alert_forwarder import SlackAlertForwarder

        reset_redis_client()
        store = StateStore(prefix="inttest-good")
        fwd = SlackAlertForwarder(store=store)
        try:
            state = MissionStateV2(
                tenant_id="good-tenant",
                run_id="run-good",
                overall_health=SupportHealth.GOOD,
            )
            result = fwd.forward_mission_alert(state)
            assert result["skipped"] is True
            assert store.exists("alert:sent:good-tenant:good") is False
        finally:
            store.clear_prefix()

    def test_forward_clears_after_ttl(self):
        from src.services.state_store import StateStore, reset_redis_client
        from src.notifications.slack_alert_forwarder import SlackAlertForwarder

        reset_redis_client()
        store = StateStore(prefix="inttest-ttl")
        fwd = SlackAlertForwarder(store=store)
        try:
            state = MissionStateV2(
                tenant_id="ttl-tenant",
                run_id="r1",
                overall_health=SupportHealth.CRITICAL,
            )
            with patch(
                "src.integrations.slack.send_message_sync",
                return_value={"ok": True, "channel": "slack"},
            ):
                result = fwd.forward_mission_alert(state)

            assert result["ok"] is True
            key = "alert:sent:ttl-tenant:critical"
            assert store.exists(key) is True

            store.delete(key)
            assert store.exists(key) is False
        finally:
            store.clear_prefix()

    def test_forward_with_failed_connectors(self):
        from src.services.state_store import StateStore, reset_redis_client
        from src.notifications.slack_alert_forwarder import SlackAlertForwarder

        reset_redis_client()
        store = StateStore(prefix="inttest-fail")
        fwd = SlackAlertForwarder(store=store)
        try:
            state = MissionStateV2(
                tenant_id="fail-tenant",
                run_id="r1",
                overall_health=SupportHealth.CRITICAL,
                connectors_ok={"erpnext": False, "hubspot": True},
            )
            with patch(
                "src.integrations.slack.send_message_sync",
                return_value={"ok": True, "channel": "slack"},
            ) as mock_deliver:
                fwd.forward_mission_alert(state)

            args, kwargs = mock_deliver.call_args
            assert "erpnext" in kwargs.get("text", args[0] if args else "")
        finally:
            store.clear_prefix()

    def test_postgres_connectivity(self):
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
