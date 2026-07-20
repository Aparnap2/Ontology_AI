"""OntologyAI V5.1 — Credentials binding model (PRD §17, §20.1.5).

Defines the :class:`CredentialBinding` Pydantic model and the
:class:`CredentialStore` for managing runtime credentials across tenants.

The binding model holds a provider, display name, secret reference, scopes,
and lifecycle status. The store is an in-memory dict (swappable for Vault or
env-variable resolution in production).
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

# ── Allowed provider values — matches the runtime integrations catalogue ────
_PROVIDER_VALUES = Literal[
    "slack",
    "gmail",
    "hubspot",
    "postgres",
    "http_api",
    "n8n",
    "openai",
    "groq",
]

_STATUS_VALUES = Literal["pending", "validated", "failed"]


class CredentialBinding(BaseModel):
    """A single credential binding for a runtime integration.

    Stores the provider, display name, secret reference, scopes, and lifecycle
    status.

    Attributes:
        provider: The integration provider name (one of the allowed Literal).
        display_name: Human-readable label for this binding.
        secret_ref: Reference to the secret storage, e.g.
            ``"secret://tenant/acme/slack/main"``.
        scopes: Optional OAuth-style scope list.
        status: Lifecycle status — starts as ``"pending"``, transitions to
            ``"validated"`` or ``"failed"``.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    provider: _PROVIDER_VALUES
    display_name: str
    secret_ref: str
    scopes: list[str] = []
    status: _STATUS_VALUES = "pending"


class CredentialStore:
    """In-memory credential store (swap for Vault / Env later).

    Provides per-tenant credential CRUD operations. This is the default local
    implementation; in production it would be replaced with HashiCorp Vault,
    AWS Secrets Manager, or environment-variable-based resolution.

    Thread-safety is not required at this stage; Temporal workflow tasks are
    logically single-threaded per execution.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, CredentialBinding]] = {}

    def store(self, tenant_id: str, binding: CredentialBinding) -> str:
        """Store a credential binding for a tenant.

        Args:
            tenant_id: The tenant identifier.
            binding: The credential binding to store.

        Returns:
            A binding id string (UUID) that can later be used to retrieve
            the binding via :meth:`get`.
        """
        if tenant_id not in self._store:
            self._store[tenant_id] = {}
        binding_id = str(uuid.uuid4())
        self._store[tenant_id][binding_id] = binding
        return binding_id

    def get(self, tenant_id: str, binding_id: str) -> CredentialBinding | None:
        """Retrieve a credential binding by id.

        Args:
            tenant_id: The tenant identifier.
            binding_id: The binding id returned by :meth:`store`.

        Returns:
            The :class:`CredentialBinding` if found, else ``None``.
        """
        return self._store.get(tenant_id, {}).get(binding_id)

    def delete(self, tenant_id: str, binding_id: str) -> None:
        """Delete a credential binding.

        Args:
            tenant_id: The tenant identifier.
            binding_id: The binding id to remove.

        Note:
            Deleting a non-existent binding is a silent no-op.
        """
        self._store.get(tenant_id, {}).pop(binding_id, None)
