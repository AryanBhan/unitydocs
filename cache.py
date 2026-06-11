"""
In-memory cache with 1-hour TTL.
Cache keys are scoped by session_id — each user session is fully isolated.
Two users on the same Databricks workspace never share cache entries.
Cleared on server restart — intentional for session-level caching.
"""

import time
from typing import Any, Optional

TTL_SECONDS = 3600  # 1 hour


class CacheEntry:
    def __init__(self, value: Any):
        self.value = value
        self.created_at = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > TTL_SECONDS

    def age_seconds(self) -> int:
        return int(time.time() - self.created_at)


class InMemoryCache:
    def __init__(self):
        self._store: dict[str, CacheEntry] = {}

    def _key(self, *parts: str) -> str:
        return ":".join(str(p) for p in parts)

    def get(self, *key_parts: str) -> Optional[Any]:
        key = self._key(*key_parts)
        entry = self._store.get(key)
        if entry is None or entry.is_expired():
            if entry:
                del self._store[key]
            return None
        return entry.value

    def set(self, *key_parts: str, value: Any) -> None:
        key = self._key(*key_parts)
        self._store[key] = CacheEntry(value)

    def delete(self, *key_parts: str) -> bool:
        key = self._key(*key_parts)
        if key in self._store:
            del self._store[key]
            return True
        return False

    def delete_session(self, session_id: str) -> int:
        """Wipe all cache entries belonging to a session. Returns count deleted."""
        prefix = f"{session_id}:"
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]
        return len(keys_to_delete)

    def info(self, *key_parts: str) -> Optional[dict]:
        key = self._key(*key_parts)
        entry = self._store.get(key)
        if entry is None or entry.is_expired():
            return None
        return {
            "cached": True,
            "age_seconds": entry.age_seconds(),
            "expires_in_seconds": TTL_SECONDS - entry.age_seconds()
        }


# Single shared instance used across the app
cache = InMemoryCache()