"""Event type normalizer for OntologyAI.

Maps raw source + event name to normalized event types.
Mirrors apps/core/internal/events/normalizer.go.
"""

# Mapping of source::event_name -> normalized event type
# Extends to match the Go normalizer as integrations are added.
NORMALIZER_INDEX: dict[str, str] = {
    "zoho_books::expense.created": "EXPENSE_RECORDED",
}


def normalize_event(source: str, event_name: str) -> str:
    """Normalize a raw event source + name to a standardized event type.

    Args:
        source: The event source (e.g. ``"zoho_books"``, ``"stripe"``).
        event_name: The raw event name (e.g. ``"expense.created"``).

    Returns:
        Normalized event type string (e.g. ``"EXPENSE_RECORDED"``),
        or ``"UNKNOWN"`` if no mapping exists.
    """
    key = f"{source}::{event_name}"
    return NORMALIZER_INDEX.get(key, "UNKNOWN")
