"""TDD tests for OntologyAI V5.1 credentials binding model.

RED phase: these imports will fail until src/runtime/credentials.py exists.
GREEN phase: after implementing CredentialBinding + CredentialStore.

Tests:
- Pydantic validation (provider Literal, secret_ref required, status transitions)
- CredentialStore CRUD operations
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# These imports will fail in RED phase — that is the expected behaviour.
from src.runtime.credentials import CredentialBinding, CredentialStore


class TestCredentialBinding:
    """CredentialBinding Pydantic model validation tests."""

    def test_valid_binding(self):
        """A valid CredentialBinding with minimal fields."""
        binding = CredentialBinding(
            provider="slack",
            display_name="Workspace Slack",
            secret_ref="secret://tenant/acme/slack/main",
        )
        assert binding.provider == "slack"
        assert binding.display_name == "Workspace Slack"
        assert binding.secret_ref == "secret://tenant/acme/slack/main"
        assert binding.scopes == []
        assert binding.status == "pending"

    def test_invalid_provider_raises(self):
        """Unknown provider string must raise ValidationError."""
        with pytest.raises(ValidationError):
            CredentialBinding(
                provider="unknown_provider",
                display_name="Bad",
                secret_ref="secret://bad",
            )

    def test_secret_ref_required(self):
        """secret_ref is required — missing it must raise ValidationError."""
        with pytest.raises(ValidationError):
            CredentialBinding(
                provider="slack",
                display_name="No Secret",
                # secret_ref omitted
            )

    def test_status_transitions(self):
        """Status can be set to validated/failed from pending."""
        b = CredentialBinding(
            provider="gmail",
            display_name="Gmail",
            secret_ref="secret://gmail",
            status="validated",
        )
        assert b.status == "validated"

        b2 = CredentialBinding(
            provider="hubspot",
            display_name="HubSpot",
            secret_ref="secret://hubspot",
            status="failed",
        )
        assert b2.status == "failed"

    def test_extra_field_forbidden(self):
        """extra="forbid" — any unknown field must raise."""
        with pytest.raises(ValidationError):
            CredentialBinding(
                provider="slack",
                display_name="Test",
                secret_ref="secret://test",
                extra_field="should_not_exist",
            )

    def test_all_providers_accepted(self):
        """All allowed provider values pass validation."""
        for prov in [
            "slack",
            "gmail",
            "hubspot",
            "postgres",
            "http_api",
            "n8n",
            "openai",
            "groq",
        ]:
            binding = CredentialBinding(
                provider=prov,
                display_name=f"Test {prov}",
                secret_ref=f"secret://tenant/acme/{prov}/main",
            )
            assert binding.provider == prov

    def test_scopes_optional(self):
        """Scopes is optional and defaults to empty list."""
        binding = CredentialBinding(
            provider="slack",
            display_name="Test",
            secret_ref="secret://test",
            scopes=["chat:write", "users:read"],
        )
        assert binding.scopes == ["chat:write", "users:read"]


class TestCredentialStore:
    """CredentialStore in-memory CRUD tests."""

    def test_credential_store_create(self):
        """Store a credential and get back a binding id."""
        store = CredentialStore()
        binding = CredentialBinding(
            provider="postgres",
            display_name="Analytics DB",
            secret_ref="secret://tenant/acme/postgres/main",
        )
        binding_id = store.store("tenant_acme", binding)
        assert isinstance(binding_id, str)
        assert len(binding_id) > 0

    def test_credential_store_get_missing(self):
        """Getting a non-existent binding returns None."""
        store = CredentialStore()
        result = store.get("tenant_acme", "nonexistent_id")
        assert result is None

    def test_credential_store_round_trip(self):
        """Store then retrieve the same binding."""
        store = CredentialStore()
        binding = CredentialBinding(
            provider="openai",
            display_name="OpenAI Key",
            secret_ref="secret://tenant/acme/openai/main",
        )
        binding_id = store.store("tenant_acme", binding)
        retrieved = store.get("tenant_acme", binding_id)
        assert retrieved is not None
        assert retrieved.provider == "openai"
        assert retrieved.display_name == "OpenAI Key"
        assert retrieved.secret_ref == "secret://tenant/acme/openai/main"

    def test_credential_store_delete(self):
        """Delete a binding returns None on subsequent get."""
        store = CredentialStore()
        binding = CredentialBinding(
            provider="groq",
            display_name="Groq API",
            secret_ref="secret://tenant/acme/groq/main",
        )
        binding_id = store.store("tenant_acme", binding)
        store.delete("tenant_acme", binding_id)
        assert store.get("tenant_acme", binding_id) is None

    def test_tenant_isolation(self):
        """Credentials for different tenants do not leak."""
        store = CredentialStore()
        b1 = CredentialBinding(
            provider="slack",
            display_name="T1 Slack",
            secret_ref="secret://t1/slack",
        )
        b2 = CredentialBinding(
            provider="gmail",
            display_name="T2 Gmail",
            secret_ref="secret://t2/gmail",
        )
        id1 = store.store("tenant_a", b1)
        id2 = store.store("tenant_b", b2)
        # tenant_a should not see tenant_b's credentials
        assert store.get("tenant_a", id2) is None
        assert store.get("tenant_b", id1) is None
