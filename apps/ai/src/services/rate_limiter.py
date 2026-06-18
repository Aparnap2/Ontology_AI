"""Alert Rate Limiting per PRD Rule 4."""
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional

from src.services.state_store import StateStore

@dataclass
class RateLimitResult:
    allowed: bool
    reason: Optional[str] = None
    alerts_today: int = 0
    hours_until_retry: Optional[float] = None

_store = StateStore(prefix="ratelimit")

MAX_ALERTS_PER_DAY = 3
BLINDSPOT_COOLDOWN_HOURS = 48
_DAILY_TTL = 86400  # 24 hours
_BLINDSPOT_TTL = 172800  # 48 hours

def can_send_alert(
    tenant_id: str,
    alert_id: str,
    blindspot_id: Optional[str] = None,
    severity: str = "warning"
) -> bool:
    """Check if alert can be sent (rate limiting)."""
    now = datetime.now(timezone.utc)

    # Load existing alert timestamps for this tenant
    counts_key = f"counts:{tenant_id}"
    raw_timestamps = _store.get(counts_key) or []
    # Deserialize and filter to last 24h
    timestamps = []
    for ts_str in raw_timestamps:
        try:
            ts = datetime.fromisoformat(ts_str)
            if now - ts < timedelta(hours=24):
                timestamps.append(ts)
        except (ValueError, TypeError):
            continue

    if len(timestamps) >= MAX_ALERTS_PER_DAY:
        return False

    if blindspot_id:
        blindspot_key = f"blindspot:{tenant_id}:{blindspot_id}"
        last_sent_str = _store.get(blindspot_key)
        if last_sent_str:
            try:
                last_sent = datetime.fromisoformat(last_sent_str)
                if now - last_sent < timedelta(hours=BLINDSPOT_COOLDOWN_HOURS):
                    return False
            except (ValueError, TypeError):
                pass

    # Record this alert
    timestamps.append(now)
    _store.set(counts_key, [ts.isoformat() for ts in timestamps], ttl=_DAILY_TTL)
    if blindspot_id:
        blindspot_key = f"blindspot:{tenant_id}:{blindspot_id}"
        _store.set(blindspot_key, now.isoformat(), ttl=_BLINDSPOT_TTL)

    return True

def is_info_alert(severity: str) -> bool:
    """Check if alert is info severity (for weekly digest accumulation)."""
    return "info" in severity.lower()

def reset_rate_limiter():
    """Reset all rate limiter state (for testing)."""
    _store.clear_prefix()

def get_alerts_today(tenant_id: str) -> int:
    """Get count of alerts sent today for tenant."""
    now = datetime.now(timezone.utc)
    counts_key = f"counts:{tenant_id}"
    raw_timestamps = _store.get(counts_key) or []
    count = 0
    for ts_str in raw_timestamps:
        try:
            ts = datetime.fromisoformat(ts_str)
            if now - ts < timedelta(hours=24):
                count += 1
        except (ValueError, TypeError):
            continue
    return count