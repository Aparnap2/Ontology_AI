"""
Canonical Event Envelope for TrackGuard v1.0.

This is the ONLY shape that flows through Redpanda and Temporal.
PayloadRef points to raw_events table — NEVER contains raw JSON.
"""
from __future__ import annotations
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, field_validator


class EventSource(str, Enum):
    """All event sources in TrackGuard v1.0."""
    RAZORPAY = "razorpay"
    STRIPE = "stripe"
    INTERCOM = "intercom"
    CRISP = "crisp"
    KEKA = "keka"
    DARWINBOX = "darwinbox"
    BANK = "bank"
    CRON = "cron"


class EventEnvelope(BaseModel):
    """
    EventEnvelope for TrackGuard v1.0.

    Attributes:
        tenant_id: Multi-tenant identifier (renamed from founder_id)
        event_type: Normalized event type (renamed from event_name)
        source: Event source (razorpay, stripe, intercom, etc.)
        payload_ref: Storage reference ("raw_events:<uuid>")
        payload_hash: SHA-256 hash of raw payload
        idempotency_key: Deduplication key
        occurred_at: When the event occurred
        received_at: When TrackGuard received the event
        trace_id: Distributed tracing ID
    """
    tenant_id: str
    event_type: str
    source: str
    payload_ref: str
    payload_hash: str
    idempotency_key: str
    occurred_at: datetime
    received_at: datetime
    trace_id: str

    @field_validator("event_type")
    @classmethod
    def event_type_not_empty(cls, v: str) -> str:
        """Event type must not be empty."""
        if not v or not v.strip():
            raise ValueError("event_type must not be empty")
        return v

    @field_validator("payload_ref")
    @classmethod
    def payload_ref_is_storage_ref(cls, v: str) -> str:
        """
        payload_ref must be a storage reference, not raw JSON.

        Valid prefixes: raw_events:, files:, s3:, pg:

        Raises:
            ValueError: If payload_ref contains raw JSON or has invalid prefix
        """
        VALID_PREFIXES = ("raw_events:", "files:", "s3:", "pg:")
        if v.lstrip().startswith(("{", "[")):
            raise ValueError(
                "payload_ref must be a storage reference, not raw JSON. "
                "Store in PostgreSQL first, pass the row ID."
            )
        if not any(v.startswith(p) for p in VALID_PREFIXES):
            raise ValueError(
                f"payload_ref must start with one of {VALID_PREFIXES}. "
                f"Got: {v!r}"
            )
        return v

    class Config:
        """Pydantic config for JSON serialization."""
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
