"""Semantic explanation layer for Revenue Protection findings.

Combines deterministic math with LLM-generated narrative summaries.
The LLM is optional — a deterministic fallback is always available.
"""

from __future__ import annotations

from typing import Any, Optional


def explain_mismatch(
    order: dict[str, Any],
    shipment_count: int,
    shipped_total: float,
    delta: float,
    delta_pct: float,
    shipment_statuses: list[str],
    llm_client: Optional[Any] = None,
) -> str:
    """Generate a human-readable explanation for an Order↔Shipment mismatch.

    Uses the LLM when available for richer semantic reasoning; falls back to
    a deterministic template when no LLM is injected.

    Args:
        order: The Engagement (kind='order') dict.
        shipment_count: Number of linked shipments.
        shipped_total: Sum of shipment shipped_values.
        delta: order_value - shipped_total.
        delta_pct: abs(delta) / order_value * 100.
        shipment_statuses: List of shipment statuses (e.g., ['delivered', 'returned']).
        llm_client: Optional LLM client with a .predict() or .synthesize() method.

    Returns:
        A narrative explanation string.
    """
    direction = "under_shipped" if delta > 0 else "over_shipped"
    order_id = order.get("id", "?")
    order_value = order.get("value", 0) or 0
    order_status = order.get("status", "unknown")

    if llm_client is not None:
        try:
            prompt = (
                f"Order {order_id} (status={order_status}, value={order_value}) has "
                f"{shipment_count} shipment(s) totaling {shipped_total} (delta={delta:+.2f}, "
                f"{delta_pct:.1f}% off). Shipment statuses: {shipment_statuses}. "
                f"Explain the revenue risk in one sentence."
            )
            result = llm_client.predict(prompt) if hasattr(llm_client, 'predict') else None
            if result:
                return str(result)
        except Exception:
            pass

    # Deterministic fallback
    status_summary = ", ".join(sorted(set(shipment_statuses))) if shipment_statuses else "none"
    return (
        f"Revenue risk ({direction}): Order {order_id} (${order_value:.2f}, {order_status}) "
        f"has {shipment_count} shipment(s) [{status_summary}] totaling ${shipped_total:.2f}. "
        f"Delta: ${delta:+.2f} ({delta_pct:.1f}% off). "
        f"Recommended: {'follow up on missing shipments' if delta > 0 else 'review over-shipment.'}"
    )
