"""类 Redis 的内存缓存与内存锁工具

- 提供线程安全、带 TTL 的内存缓存 RedisLikeCache
- 提供类 Redis 的内存锁 RedisLikeLockManager（支持过期、阻塞获取、令牌校验）
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
import uuid


@dataclass
class _Entry:
    value: Any
    expire_at: Optional[float]  # epoch seconds; None means no expiry


class RedisLikeCache:
    """
    线程安全的类 Redis 内存缓存（单进程内）。

    支持的操作（Redis 子集）：
    - 键值：set/get/mset/mget/getset
    - 键空间：delete/exists/keys
    - 过期：expire/pexpire/ttl/pttl/persist
    - 计数：incr/decr
    - 列表：lpush/rpush/lpop/rpop/llen/lrange
    - 集合：sadd/srem/sismember/smembers/scard
    - 哈希：hset/hget/hgetall/hdel/hlen/hkeys/hvals

    说明：
    - 过期针对整个 key（非字段级）。
    - 值为普通 Python 对象，list/set/dict 原样存储。
    - 使用进程内 RLock 保证操作原子性。
    - 可选后台线程定期清理过期键（同时也有惰性清理）。
    """

    def __init__(
        self,
        *,
        cleanup_interval: Optional[float] = 30.0,
    ) -> None:
        self._store: Dict[str, _Entry] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._janitor: Optional[threading.Thread] = None
        if cleanup_interval and cleanup_interval > 0:
            self._janitor = threading.Thread(
                target=self._janitor_loop,
                args=(cleanup_interval,),
                name="RedisLikeCacheJanitor",
                daemon=True,
            )
            self._janitor.start()

    # --------------- internal helpers ---------------
    def _now(self) -> float:
        return time.time()

    def _is_expired(self, entry: _Entry, now: Optional[float] = None) -> bool:
        if entry.expire_at is None:
            return False
        t = self._now() if now is None else now
        return t >= entry.expire_at

    def _get_entry(self, key: str) -> Optional[_Entry]:
        e = self._store.get(key)
        if e is None:
            return None
        if self._is_expired(e):
            # 惰性删除：读取时发现过期则清理
            self._store.pop(key, None)
            return None
        return e

    def _require_type(self, key: str, value: Any, expected_types: Tuple[type, ...]) -> None:
        if not isinstance(value, expected_types):
            raise TypeError(
                f"WRONGTYPE Operation against a key holding the wrong kind of value: {key}"
            )

    def _janitor_loop(self, interval: float) -> None:
        while not self._stop_event.wait(interval):
            now = self._now()
            with self._lock:
                expired = [
                    k for k, e in self._store.items() if e.expire_at is not None and now >= e.expire_at
                ]
                for k in expired:
                    self._store.pop(k, None)

    def close(self) -> None:
        self._stop_event.set()
        if self._janitor and self._janitor.is_alive():
            self._janitor.join(timeout=1.0)

    # --------------- basic kv ---------------
    def set(
        self,
        key: str,
        value: Any,
        *,
        ex: Optional[float] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        Set key to hold the value.
        - ex: seconds to expire
        - px: milliseconds to expire
        - nx: only set if key does not exist
        - xx: only set if key already exists
        Returns True if the value was set.
        """
        if nx and xx:
            return False
        ttl_seconds: Optional[float] = None
        if px is not None:
            ttl_seconds = max(0.0, px / 1000.0)
        elif ex is not None:
            ttl_seconds = max(0.0, float(ex))

        with self._lock:
            exists = self._get_entry(key) is not None
            if nx and exists:
                return False
            if xx and not exists:
                return False
            expire_at = None if ttl_seconds is None else (self._now() + ttl_seconds)
            self._store[key] = _Entry(value=value, expire_at=expire_at)
            return True

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            e = self._get_entry(key)
            return default if e is None else e.value

    def getset(self, key: str, value: Any) -> Any:
        with self._lock:
            old = self.get(key)
            # preserve TTL of existing entry, if any
            ttl = None
            e = self._store.get(key)
            if e is not None and not self._is_expired(e):
                if e.expire_at is not None:
                    ttl = max(0.0, e.expire_at - self._now())
            self.set(key, value, ex=ttl)
            return old

    def mset(self, mapping: Dict[str, Any]) -> None:
        with self._lock:
            for k, v in mapping.items():
                self._store[k] = _Entry(value=v, expire_at=None)

    def mget(self, keys: Iterable[str]) -> List[Any]:
        return [self.get(k) for k in keys]

    def delete(self, *keys: str) -> int:
        removed = 0
        with self._lock:
            for k in keys:
                if self._get_entry(k) is not None:
                    self._store.pop(k, None)
                    removed += 1
        return removed

    def exists(self, *keys: str) -> int:
        with self._lock:
            return sum(1 for k in keys if self._get_entry(k) is not None)

    def keys(self, pattern: Optional[str] = None) -> List[str]:
        # Only supports '*' (all) or suffix/prefix wildcards using simple contains match.
        with self._lock:
            all_keys = [k for k in list(self._store.keys()) if self._get_entry(k) is not None]
        if not pattern or pattern == "*":
            return all_keys
        # very naive pattern handling
        if pattern.startswith("*") and pattern.endswith("*"):
            mid = pattern.strip("*")
            return [k for k in all_keys if mid in k]
        if pattern.startswith("*"):
            suf = pattern[1:]
            return [k for k in all_keys if k.endswith(suf)]
        if pattern.endswith("*"):
            pre = pattern[:-1]
            return [k for k in all_keys if k.startswith(pre)]
        return [k for k in all_keys if k == pattern]

    # --------------- 过期控制 (expiration) ---------------
    def expire(self, key: str, seconds: float) -> bool:
        return self.pexpire(key, int(seconds * 1000))

    def pexpire(self, key: str, milliseconds: int) -> bool:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return False
            e.expire_at = self._now() + max(0.0, milliseconds / 1000.0)
            return True

    def persist(self, key: str) -> bool:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return False
            e.expire_at = None
            return True

    def ttl(self, key: str) -> int:
        # Redis semantics: -2 if key does not exist, -1 if no expire
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return -2
            if e.expire_at is None:
                return -1
            rem = int(round(max(0.0, e.expire_at - self._now())))
            return rem

    def pttl(self, key: str) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return -2
            if e.expire_at is None:
                return -1
            rem = int(round(max(0.0, (e.expire_at - self._now()) * 1000)))
            return rem

    # --------------- 计数器 (counters) ---------------
    def incr(self, key: str, amount: int = 1) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                new_val = int(amount)
                self._store[key] = _Entry(value=new_val, expire_at=None)
                return new_val
            if isinstance(e.value, (int,)):
                e.value += int(amount)
                return e.value
            # allow string that can be converted to int
            try:
                cur = int(e.value)
            except Exception as exc:  # noqa: BLE001
                raise TypeError("value is not an integer or out of range") from exc
            cur += int(amount)
            e.value = cur
            return cur

    def decr(self, key: str, amount: int = 1) -> int:
        return self.incr(key, -int(amount))

    # --------------- lists ---------------
    def _ensure_list(self, key: str) -> _Entry:
        e = self._get_entry(key)
        if e is None:
            e = _Entry(value=[], expire_at=None)
            self._store[key] = e
        self._require_type(key, e.value, (list,))
        return e

    def lpush(self, key: str, *values: Any) -> int:
        with self._lock:
            e = self._ensure_list(key)
            for v in values:
                e.value.insert(0, v)  # type: ignore[attr-defined]
            return len(e.value)

    def rpush(self, key: str, *values: Any) -> int:
        with self._lock:
            e = self._ensure_list(key)
            e.value.extend(values)  # type: ignore[attr-defined]
            return len(e.value)

    def lpop(self, key: str) -> Any:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return None
            self._require_type(key, e.value, (list,))
            if not e.value:
                return None
            return e.value.pop(0)

    def rpop(self, key: str) -> Any:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return None
            self._require_type(key, e.value, (list,))
            if not e.value:
                return None
            return e.value.pop()

    def llen(self, key: str) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return 0
            self._require_type(key, e.value, (list,))
            return len(e.value)

    def lrange(self, key: str, start: int, stop: int) -> List[Any]:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return []
            self._require_type(key, e.value, (list,))
            # Redis lrange is inclusive of stop
            if stop == -1:
                s = e.value[start:]
            else:
                s = e.value[start : stop + 1]
            return list(s)

    # --------------- sets ---------------
    def _ensure_set(self, key: str) -> _Entry:
        e = self._get_entry(key)
        if e is None:
            e = _Entry(value=set(), expire_at=None)
            self._store[key] = e
        self._require_type(key, e.value, (set,))
        return e

    def sadd(self, key: str, *members: Any) -> int:
        with self._lock:
            e = self._ensure_set(key)
            before = len(e.value)
            e.value.update(members)
            return len(e.value) - before

    def srem(self, key: str, *members: Any) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return 0
            self._require_type(key, e.value, (set,))
            removed = 0
            for m in members:
                if m in e.value:
                    e.value.remove(m)
                    removed += 1
            return removed

    def sismember(self, key: str, member: Any) -> bool:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return False
            self._require_type(key, e.value, (set,))
            return member in e.value

    def smembers(self, key: str) -> set:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return set()
            self._require_type(key, e.value, (set,))
            return set(e.value)

    def scard(self, key: str) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return 0
            self._require_type(key, e.value, (set,))
            return len(e.value)

    # --------------- hashes ---------------
    def _ensure_hash(self, key: str) -> _Entry:
        e = self._get_entry(key)
        if e is None:
            e = _Entry(value={}, expire_at=None)
            self._store[key] = e
        self._require_type(key, e.value, (dict,))
        return e

    def hset(self, key: str, field: str, value: Any) -> int:
        with self._lock:
            e = self._ensure_hash(key)
            added = 0 if field in e.value else 1
            e.value[field] = value
            return added

    def hget(self, key: str, field: str, default: Any = None) -> Any:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return default
            self._require_type(key, e.value, (dict,))
            return e.value.get(field, default)

    def hgetall(self, key: str) -> Dict[str, Any]:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return {}
            self._require_type(key, e.value, (dict,))
            return dict(e.value)

    def hdel(self, key: str, *fields: str) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return 0
            self._require_type(key, e.value, (dict,))
            removed = 0
            for f in fields:
                if f in e.value:
                    del e.value[f]
                    removed += 1
            return removed

    def hlen(self, key: str) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return 0
            self._require_type(key, e.value, (dict,))
            return len(e.value)

    def hkeys(self, key: str) -> List[str]:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return []
            self._require_type(key, e.value, (dict,))
            return list(e.value.keys())

    def hvals(self, key: str) -> List[Any]:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                return []
            self._require_type(key, e.value, (dict,))
            return list(e.value.values())

    # --------------- admin ---------------
    def flushall(self) -> None:
        with self._lock:
            self._store.clear()


# --------------- 内存锁 (类似 Redis 分布式锁) ---------------
@dataclass
class _LockEntry:
    token: str
    expire_at: Optional[float]


class RedisLikeLockManager:
    """
    类 Redis 的内存锁管理器（单进程内）。

    - acquire: 获取锁，支持 ex/px（秒/毫秒），可阻塞等待与超时；成功返回 token，失败返回 None。
    - release: 释放锁（令牌校验，仅持有者可释放）。
    - extend: 续期（仅持有者可续期）。
    - is_locked / owner / pttl: 查询锁是否存在、持有者 token、剩余毫秒。
    - context: with 语法自动获取与释放。

    注意：该锁仅在当前进程有效，不具备跨进程/跨主机的分布式语义。
    """

    def __init__(self) -> None:
        self._locks: Dict[str, _LockEntry] = {}
        self._lock = threading.RLock()

    def _now(self) -> float:
        return time.time()

    def _try_acquire(self, key: str, token: str, ttl: float, now: Optional[float] = None) -> bool:
        t = self._now() if now is None else now
        with self._lock:
            entry = self._locks.get(key)
            if entry is None or (entry.expire_at is not None and t >= entry.expire_at):
                self._locks[key] = _LockEntry(token=token, expire_at=t + max(0.0, ttl))
                return True
            return False

    def acquire(
        self,
        key: str,
        *,
        token: Optional[str] = None,
        ex: Optional[float] = 10.0,
        px: Optional[int] = None,
        block: bool = False,
        timeout: Optional[float] = None,
        retry_interval: float = 0.05,
    ) -> Optional[str]:
        """
        获取锁：
        - token: 指定持有者令牌（默认随机 UUID）。
        - ex/px: 过期秒/毫秒（默认 10 秒），必须 > 0。
        - block: True 表示阻塞等待直到成功或超时。
        - timeout: 阻塞等待的最长时间（None 表示无限等待）。
        - retry_interval: 阻塞重试的间隔秒数。
        成功返回 token，失败返回 None。
        """
        tok = token or uuid.uuid4().hex
        ttl = (px / 1000.0) if px is not None else (ex if ex is not None else 10.0)
        if ttl is None or ttl <= 0:
            ttl = 10.0
        deadline = None if not block or timeout is None else (self._now() + timeout)
        while True:
            if self._try_acquire(key, tok, ttl):
                return tok
            if not block:
                return None
            if deadline is not None and self._now() >= deadline:
                return None
            time.sleep(max(0.0, retry_interval))

    def release(self, key: str, token: str) -> bool:
        """
        释放锁：仅当 token 匹配时才会删除该锁。
        返回 True 表示释放成功；返回 False 表示锁不存在/已过期/令牌不匹配。
        """
        with self._lock:
            entry = self._locks.get(key)
            if entry is None:
                return False
            if entry.expire_at is not None and self._now() >= entry.expire_at:
                self._locks.pop(key, None)
                return False
            if entry.token != token:
                return False
            self._locks.pop(key, None)
            return True

    def extend(self, key: str, token: str, *, ex: Optional[float] = None, px: Optional[int] = None) -> bool:
        """仅持有者可续期，成功返回 True。"""
        ttl = (px / 1000.0) if px is not None else (ex if ex is not None else None)
        if ttl is None or ttl <= 0:
            return False
        with self._lock:
            entry = self._locks.get(key)
            if entry is None:
                return False
            now = self._now()
            if entry.expire_at is not None and now >= entry.expire_at:
                self._locks.pop(key, None)
                return False
            if entry.token != token:
                return False
            entry.expire_at = now + ttl
            return True

    def is_locked(self, key: str) -> bool:
        with self._lock:
            entry = self._locks.get(key)
            if entry is None:
                return False
            if entry.expire_at is not None and self._now() >= entry.expire_at:
                self._locks.pop(key, None)
                return False
            return True

    def owner(self, key: str) -> Optional[str]:
        with self._lock:
            entry = self._locks.get(key)
            if entry is None:
                return None
            if entry.expire_at is not None and self._now() >= entry.expire_at:
                self._locks.pop(key, None)
                return None
            return entry.token

    def pttl(self, key: str) -> int:
        """返回剩余毫秒（-2 不存在，-1 无过期）。"""
        with self._lock:
            entry = self._locks.get(key)
            if entry is None:
                return -2
            if entry.expire_at is None:
                return -1
            remain = int(round(max(0.0, (entry.expire_at - self._now()) * 1000)))
            return remain

    class _LockContext:
        """with 语法帮助类：自动获取与释放。"""

        def __init__(self, mgr: "RedisLikeLockManager", key: str, kwargs: Dict[str, Any]) -> None:
            self._mgr = mgr
            self._key = key
            self._kwargs = kwargs
            self._token: Optional[str] = None

        def __enter__(self) -> str:
            tok = self._mgr.acquire(self._key, **self._kwargs)
            if not tok:
                raise TimeoutError(f"acquire lock failed: {self._key}")
            self._token = tok
            return tok

        def __exit__(self, exc_type, exc, tb) -> None:
            if self._token is not None:
                self._mgr.release(self._key, self._token)

    def context(self, key: str, **kwargs: Any) -> "RedisLikeLockManager._LockContext":
        return RedisLikeLockManager._LockContext(self, key, kwargs)


# 模块级单例（缓存）
# A module-level singleton that can be imported and used directly.
cache = RedisLikeCache()

# 模块级单例（内存锁）
locks = RedisLikeLockManager()

__all__ = [
    "RedisLikeCache",
    "RedisLikeLockManager",
    "cache",
    "locks",
]
