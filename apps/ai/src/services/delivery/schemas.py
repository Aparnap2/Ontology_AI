"""
Delivery Service Schemas — Pydantic models for delivery contracts.

Defines the contract for decision results consumed from Redpanda
and delivery status events published back to Redpanda.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DeliveryStatus(str, Enum):
    """Delivery outcome status."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    FALLBACK_USED = "fallback_used"


class DeliveryChannel(str, Enum):
    """Available delivery channels."""
    SLACK = "slack"
    TELEGRAM = "telegram"
    MOCK = "mock"


class DecisionResultInput(BaseModel):
    """Input schema for decision results from trackguard.decision.results topic."""

    tenant_id: str = Field(..., description="Tenant identifier")
    decision_id: str = Field(..., description="Unique decision identifier")
    pattern_name: str = Field(..., description="Pattern that triggered the decision")
    severity: str = Field(..., description="Severity level: critical, warning, info")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    insight: str = Field(..., description="Generated insight message")
    hitl_required: bool = Field(..., description="Whether human review is required")
    signals: dict[str, Any] = Field(default_factory=dict, description="Triggering signals")
    occurred_at: str = Field(..., description="ISO timestamp of decision")


class DeliveryResult(BaseModel):
    """Output schema for delivery operations."""

    ok: bool = Field(..., description="Whether delivery succeeded")
    decision_id: str = Field(..., description="The decision that was delivered")
    channel: DeliveryChannel = Field(..., description="Channel used for delivery")
    status: DeliveryStatus = Field(..., description="Final delivery status")
    message_id: Optional[str] = Field(None, description="Provider message ID if available")
    error: Optional[str] = Field(None, description="Error message if failed")


class DeliveryStatusEvent(BaseModel):
    """Schema for delivery status events published to Redpanda."""

    tenant_id: str = Field(..., description="Tenant identifier")
    decision_id: str = Field(..., description="Decision identifier")
    event_type: str = Field(default="DELIVERY_STATUS", description="Event type")
    source: str = Field(default="delivery_service", description="Event source")
    status: DeliveryStatus = Field(..., description="Delivery status")
    channel: DeliveryChannel = Field(..., description="Channel used")
    error: Optional[str] = Field(None, description="Error details if failed")
    delivered_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class PendingApproval(BaseModel):
    """Schema for pending HITL items in review queue."""

    item_id: str = Field(..., description="Unique item identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    decision_id: str = Field(..., description="Associated decision ID")
    pattern_name: str = Field(..., description="Pattern that triggered this")
    severity: str = Field(..., description="Severity level")
    insight: str = Field(..., description="Generated insight")
    signals: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(..., description="When item was created")
    status: str = Field(default="pending", description="Current status")


class ApprovalAction(BaseModel):
    """Schema for approval/rejection actions."""

    item_id: str = Field(..., description="Item to approve/reject")
    action: str = Field(..., pattern="^(approve|reject)$", description="Action to take")
    reason: Optional[str] = Field(None, description="Optional reason for action")
    acted_by: Optional[str] = Field(None, description="User who performed action")