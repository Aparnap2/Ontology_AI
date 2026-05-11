"""Alert Rate Limiting per PRD Rule 4."""
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional

@dataclass
class RateLimitResult:
    allowed: bool
    reason: Optional[str] = None
    alerts_today: int = 0
    hours_until_retry: Optional[float] = None

_alert_counts: dict[str, list[datetime]] = {}
_blindspot_last_sent: dict[str, datetime] = {}

MAX_ALERTS_PER_DAY = 3
BLINDSPOT_COOLDOWN_HOURS = 48

def can_send_alert(
    tenant_id: str,
    alert_id: str,
    blindspot_id: Optional[str] = None,
    severity: str = "warning"
) -> bool:
    """Check if alert can be sent (rate limiting)."""
    key = f"{tenant_id}"
    now = datetime.now(timezone.utc)

    if key not in _alert_counts:
        _alert_counts[key] = []

    _alert_counts[key] = [
        t for t in _alert_counts[key]
        if now - t < timedelta(hours=24)
    ]

    if len(_alert_counts[key]) >= MAX_ALERTS_PER_DAY:
        return False

    if blindspot_id:
        blindspot_key = f"{tenant_id}:{blindspot_id}"
        if blindspot_key in _blindspot_last_sent:
            last_sent = _blindspot_last_sent[blindspot_key]
            if now - last_sent < timedelta(hours=BLINDSPOT_COOLDOWN_HOURS):
                return False

    _alert_counts[key].append(now)
    if blindspot_id:
        _blindspot_last_sent[f"{tenant_id}:{blindspot_id}"] = now

    return True

def is_info_alert(severity: str) -> bool:
    """Check if alert is info severity (for weekly digest accumulation)."""
    return "info" in severity.lower()

def reset_rate_limiter():
    """Reset all rate limiter state (for testing)."""
    global _alert_counts, _blindspot_last_sent
    _alert_counts.clear()
    _blindspot_last_sent.clear()

def get_alerts_today(tenant_id: str) -> int:
    """Get count of alerts sent today for tenant."""
    key = f"{tenant_id}"
    if key not in _alert_counts:
        return 0
    now = datetime.now(timezone.utc)
    return len([
        t for t in _alert_counts[key]
        if now - t < timedelta(hours=24)
    ])