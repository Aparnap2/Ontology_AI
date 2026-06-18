"""Persistent state store — Redis backend with in-memory fallback."""
import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_redis_client = None


def _get_redis():
    """Get Redis client (lazy init). Returns None if Redis unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        _redis_client = redis.from_url(url, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        logger.info("Connected to Redis at %s", url)
        return _redis_client
    except Exception as e:
        logger.warning("Redis unavailable, using in-memory fallback: %s", e)
        _redis_client = None
        return None


def reset_redis_client() -> None:
    """Reset the Redis client singleton (for testing)."""
    global _redis_client
    _redis_client = None


class StateStore:
    """Key-value store with TTL support. Redis if available, else in-memory."""

    def __init__(self, prefix: str = "sg"):
        self._prefix = prefix
        self._memory: dict[str, tuple[Any, float]] = {}

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def get(self, key: str) -> Optional[Any]:
        r = _get_redis()
        if r:
            try:
                val = r.get(self._key(key))
                return json.loads(val) if val else None
            except Exception:
                pass
        # Fallback: in-memory with TTL check
        entry = self._memory.get(key)
        if entry and entry[1] > time.time():
            return entry[0]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        r = _get_redis()
        if r:
            try:
                r.set(self._key(key), json.dumps(value), ex=ttl)
                return
            except Exception:
                pass
        # Fallback: in-memory
        expiry = time.time() + (ttl or 3600)
        self._memory[key] = (value, expiry)

    def increment(self, key: str, ttl: Optional[int] = None) -> int:
        r = _get_redis()
        if r:
            try:
                k = self._key(key)
                val = r.incr(k)
                if ttl and val == 1:
                    r.expire(k, ttl)
                return val
            except Exception:
                pass
        # Fallback: in-memory
        current = self.get(key) or 0
        new_val = current + 1
        self.set(key, new_val, ttl)
        return new_val

    def delete(self, key: str) -> None:
        r = _get_redis()
        if r:
            try:
                r.delete(self._key(key))
            except Exception:
                pass
        self._memory.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def clear_prefix(self) -> None:
        """Clear all keys with this prefix (for testing)."""
        r = _get_redis()
        if r:
            try:
                pattern = self._key("*")
                keys = r.keys(pattern)
                if keys:
                    r.delete(*keys)
            except Exception:
                pass
        self._memory.clear()
