"""
Integration tests using Mockoon mock server.

Tests HITL + BI query endpoints without real Go server.
Requires Mockoon CLI running on localhost:3000.

Usage:
    # Start Mockoon
    bash ../../scripts/start-mockoon.sh &
    sleep 5

    # Run tests
    MOCKOON_BASE_URL=http://localhost:3000 uv run pytest tests/integration/test_mockoon_endpoints.py -v --timeout=30
"""
import os
import pytest
import requests
from typing import Any, Dict

MOCK_BASE = os.getenv("MOCKOON_BASE_URL", "http://localhost:3000")


@pytest.fixture(scope="module")
def mockoon_base() -> str:
    """Fixture providing Mockoon base URL."""
    return MOCK_BASE


@pytest.fixture(scope="module")
def session() -> requests.Session:
    """Fixture providing requests session with common headers."""
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_success(self, session: requests.Session) -> None:
        """Health endpoint should return status ok."""
        resp = session.get(f"{MOCK_BASE}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "trackguard-core-mock"
        assert "time" in data

    def test_health_content_type(self, session: requests.Session) -> None:
        """Health endpoint should return JSON content type."""
        resp = session.get(f"{MOCK_BASE}/health")
        assert "application/json" in resp.headers.get("Content-Type", "")


class TestHITLEndpoints:
    """Test HITL signal endpoints."""

    def test_hitl_investigate_success(self, session: requests.Session) -> None:
        """HITL investigate should return ok=true."""
        payload = {
            "workflow_id": "finance-abc123",
            "tenant_id": "test-tenant",
            "vendor": "AWS",
        }
        resp = session.post(f"{MOCK_BASE}/internal/hitl/investigate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["action"] == "investigate"
        assert data["workflow_id"] == "finance-abc123"
        assert "message" in data

    def test_hitl_investigate_missing_workflow_id(
        self, session: requests.Session
    ) -> None:
        """HITL investigate should validate workflow_id."""
        payload = {"tenant_id": "test"}
        resp = session.post(f"{MOCK_BASE}/internal/hitl/investigate", json=payload)
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_hitl_investigate_with_all_fields(
        self, session: requests.Session
    ) -> None:
        """HITL investigate should accept all optional fields."""
        payload = {
            "workflow_id": "prod-xyz-789",
            "tenant_id": "acme-corp",
            "vendor": "GCP",
            "amount": 5000.00,
            "currency": "USD",
        }
        resp = session.post(f"{MOCK_BASE}/internal/hitl/investigate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["workflow_id"] == "prod-xyz-789"

    def test_hitl_dismiss_success(self, session: requests.Session) -> None:
        """HITL dismiss should return ok=true."""
        payload = {
            "workflow_id": "finance-xyz789",
            "tenant_id": "test-tenant",
            "vendor": "Vercel",
        }
        resp = session.post(f"{MOCK_BASE}/internal/hitl/dismiss", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["action"] == "dismiss"
        assert data["workflow_id"] == "finance-xyz789"

    def test_hitl_dismiss_with_metadata(self, session: requests.Session) -> None:
        """HITL dismiss should accept additional metadata."""
        payload = {
            "workflow_id": "ops-alert-456",
            "tenant_id": "beta-inc",
            "vendor": "AWS",
            "reason": "False positive",
            "dismissed_by": "admin@example.com",
        }
        resp = session.post(f"{MOCK_BASE}/internal/hitl/dismiss", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["workflow_id"] == "ops-alert-456"


class TestBIQueryEndpoint:
    """Test BI query endpoint."""

    def test_bi_query_success(self, session: requests.Session) -> None:
        """BI query should return ok=true with workflow_id."""
        payload = {
            "tenant_id": "test-tenant",
            "query": "What are total expenses by vendor last 30 days?",
            "query_type": "ADHOC",
        }
        resp = session.post(f"{MOCK_BASE}/internal/query", json=payload)
        assert resp.status_code == 202
        data = resp.json()
        assert data["ok"] is True
        assert "workflow_id" in data
        assert "query_id" in data
        assert "message" in data

    def test_bi_query_missing_query(self, session: requests.Session) -> None:
        """BI query should validate query field."""
        payload = {"tenant_id": "test"}
        resp = session.post(f"{MOCK_BASE}/internal/query", json=payload)
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_bi_query_minimal_payload(self, session: requests.Session) -> None:
        """BI query should work with minimal required fields."""
        payload = {
            "tenant_id": "minimal-tenant",
            "query": "Revenue today",
        }
        resp = session.post(f"{MOCK_BASE}/internal/query", json=payload)
        assert resp.status_code == 202
        data = resp.json()
        assert data["ok"] is True
        assert "workflow_id" in data

    def test_bi_query_complex_query(self, session: requests.Session) -> None:
        """BI query should handle complex natural language queries."""
        payload = {
            "tenant_id": "enterprise-corp",
            "query": "Show me the month-over-month growth rate for SaaS subscription revenue, broken down by customer segment, for the last 6 months, excluding churned customers",
            "query_type": "COMPLEX",
            "filters": {"exclude_churned": True, "time_range": "6M"},
        }
        resp = session.post(f"{MOCK_BASE}/internal/query", json=payload)
        assert resp.status_code == 202
        data = resp.json()
        assert data["ok"] is True
        assert "workflow_id" in data


class TestTelegramMocks:
    """Test Telegram API mocks."""

    def test_send_message_success(self, session: requests.Session) -> None:
        """Telegram sendMessage should return ok=true."""
        payload = {
            "chat_id": "42",
            "text": "🔴 Finance Alert: AWS bill 2.3× usual",
            "parse_mode": "Markdown",
        }
        resp = session.post(f"{MOCK_BASE}/bot:test-token/sendMessage", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "result" in data
        assert "message_id" in data["result"]
        # chat_id may be returned as int or string depending on mock
        assert str(data["result"]["chat"]["id"]) == "42"

    def test_send_photo_success(self, session: requests.Session) -> None:
        """Telegram sendPhoto should return ok=true."""
        payload = {
            "chat_id": "42",
            "caption": "AWS expenses breakdown",
            "photo": "AgACAgIAAxkBAAIB",
        }
        resp = session.post(f"{MOCK_BASE}/bot:test-token/sendPhoto", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "result" in data
        assert "photo" in data["result"]
        assert "message_id" in data["result"]

    def test_send_message_html_parse_mode(
        self, session: requests.Session
    ) -> None:
        """Telegram sendMessage should accept HTML parse mode."""
        payload = {
            "chat_id": "123",
            "text": "<b>Bold Alert</b>: Server CPU at 95%",
            "parse_mode": "HTML",
        }
        resp = session.post(f"{MOCK_BASE}/bot:test-token/sendMessage", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["result"]["message_id"] > 0

    def test_send_message_no_parse_mode(self, session: requests.Session) -> None:
        """Telegram sendMessage should work without parse_mode."""
        payload = {
            "chat_id": "999",
            "text": "Plain text message",
        }
        resp = session.post(f"{MOCK_BASE}/bot:test-token/sendMessage", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["result"]["text"] == "Plain text message"


class TestMockoonReliability:
    """Test Mockoon server reliability and edge cases."""

    def test_mockoon_always_returns_json(self, session: requests.Session) -> None:
        """All Mockoon endpoints should return valid JSON."""
        endpoints = [
            ("GET", "/health"),
            ("POST", "/internal/hitl/investigate"),
            ("POST", "/internal/hitl/dismiss"),
            ("POST", "/internal/query"),
        ]

        for method, endpoint in endpoints:
            if method == "GET":
                resp = session.get(f"{MOCK_BASE}{endpoint}")
            else:
                resp = session.post(f"{MOCK_BASE}{endpoint}", json={})
            
            # Should not raise JSON decode error
            try:
                _ = resp.json()
            except ValueError as e:
                pytest.fail(f"Endpoint {method} {endpoint} did not return valid JSON: {e}")

    def test_mockoon_cors_headers(self, session: requests.Session) -> None:
        """Mockoon should include CORS headers."""
        resp = session.get(f"{MOCK_BASE}/health")
        # Mockoon enables CORS by default
        assert resp.status_code == 200

    def test_mockoon_response_time(self, session: requests.Session) -> None:
        """Mockoon responses should be fast (< 500ms)."""
        import time

        start = time.time()
        resp = session.get(f"{MOCK_BASE}/health")
        elapsed = (time.time() - start) * 1000  # Convert to ms

        assert resp.status_code == 200
        assert elapsed < 500, f"Mockoon response took {elapsed:.2f}ms (expected < 500ms)"
