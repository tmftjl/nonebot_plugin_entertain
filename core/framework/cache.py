from __future__ import annotations

import time
from threading import RLock
from typing import Any, Callable, Dict, Optional, Tuple


class KeyValueCache:
    """A simple thread-safe key-value cache with optional TTL per entry.

    Use get(key, loader) to read or compute and store when missing or expired.
    Use set or set_with_ttl to update.
    Use invalidate to drop one key or all.
    """

    def __init__(self, ttl: Optional[float] = None) -> None:
        self._ttl = ttl
        self._store: Dict[str, Tuple[float, Any, Optional[float]]] = {}
        self._lock = RLock()

    def _expired(self, inserted_at: float, entry_ttl: Optional[float]) -> bool:
        ttl = self._ttl if entry_ttl is None else entry_ttl
        if ttl is None or ttl <= 0:
            return False
        return (time.time() - inserted_at) > ttl

    def get(self, key: str, loader: Optional[Callable[[], Any]] = None) -> Any:
        now = time.time()
        with self._lock:
            if key in self._store:
                ts, val, ent_ttl = self._store[key]
                if not self._expired(ts, ent_ttl):
                    return val
                # expired, drop
                self._store.pop(key, None)

        if loader is None:
            return None
        val = loader()
        with self._lock:
            self._store[key] = (now, val, None)
        return val

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.time(), value, None)

    def set_with_ttl(self, key: str, value: Any, ttl: Optional[float]) -> None:
        with self._lock:
            self._store[key] = (time.time(), value, ttl)

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)

