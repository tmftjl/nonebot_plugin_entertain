"""类 Redis 的统一内存缓存与锁工具 (All-in-One)

- 核心：单进程内的线程安全 Key-Value 存储
- 功能：支持 String/List/Set/Hash/Counter 等数据结构
- 锁机制：内置类似 Redis 的分布式锁实现 (set nx)，支持阻塞获取与自动续期
- 维护：后台线程自动清理过期键 (Janitor)
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union


@dataclass
class _Entry:
    value: Any
    expire_at: Optional[float]  # epoch seconds; None means no expiry


class RedisLikeCache:
    """
    线程安全的类 Redis 内存缓存（单进程内）。
    集成缓存操作、数据结构操作与锁机制。
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

        # 启动后台清理线程
        if cleanup_interval and cleanup_interval > 0:
            self._janitor = threading.Thread(
                target=self._janitor_loop,
                args=(cleanup_interval,),
                name="RedisLikeCacheJanitor",
                daemon=True,
            )
            self._janitor.start()

    # --------------- Internal Helpers ---------------
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
        """后台定期清理任务"""
        while not self._stop_event.wait(interval):
            now = self._now()
            with self._lock:
                expired = [
                    k for k, e in self._store.items() if e.expire_at is not None and now >= e.expire_at
                ]
                for k in expired:
                    self._store.pop(k, None)

    def close(self) -> None:
        """关闭后台清理线程"""
        self._stop_event.set()
        if self._janitor and self._janitor.is_alive():
            self._janitor.join(timeout=1.0)

    # --------------- Basic KV ---------------
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
        - nx: only set if key does not exist (用于锁)
        - xx: only set if key already exists
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
            # 尝试保留原有的 TTL
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
        """Simple keys implementation supporting prefix/suffix/contains wildcards (*)."""
        with self._lock:
            all_keys = [k for k in list(self._store.keys()) if self._get_entry(k) is not None]
        
        if not pattern or pattern == "*":
            return all_keys
        
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

    # --------------- Expiration ---------------
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
        with self._lock:
            e = self._get_entry(key)
            if e is None: return -2
            if e.expire_at is None: return -1
            return int(round(max(0.0, e.expire_at - self._now())))

    def pttl(self, key: str) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return -2
            if e.expire_at is None: return -1
            return int(round(max(0.0, (e.expire_at - self._now()) * 1000)))

    # --------------- Locking (Unified) ---------------
    
    def try_lock(self, key: str, token: str, ex: float = 10.0) -> bool:
        """尝试非阻塞获取锁。底层使用 SET key token EX ex NX。"""
        return self.set(key, token, ex=ex, nx=True)

    def unlock(self, key: str, token: str) -> bool:
        """安全释放锁：仅当 token 匹配时删除 key。"""
        with self._lock:
            val = self.get(key)
            if val == token:
                self.delete(key)
                return True
            return False

    def extend_lock(self, key: str, token: str, ex: float) -> bool:
        """锁续期：仅当 token 匹配时更新过期时间。"""
        with self._lock:
            val = self.get(key)
            if val == token:
                return self.expire(key, ex)
            return False

    class _LockContext:
        """锁的上下文管理器"""
        def __init__(
            self, 
            cache_ref: "RedisLikeCache", 
            key: str, 
            ex: float,
            block: bool,
            timeout: Optional[float],
            retry_interval: float
        ):
            self._cache = cache_ref
            self._key = key
            self._ex = ex
            self._block = block
            self._timeout = timeout
            self._retry_interval = retry_interval
            self._token = uuid.uuid4().hex

        def __enter__(self) -> str:
            deadline = None
            if self._block and self._timeout is not None:
                deadline = time.time() + self._timeout

            while True:
                if self._cache.try_lock(self._key, self._token, ex=self._ex):
                    return self._token
                
                if not self._block:
                    raise TimeoutError(f"Could not acquire lock for key: {self._key}")
                
                if deadline is not None and time.time() >= deadline:
                    raise TimeoutError(f"Acquire lock timeout for key: {self._key}")
                
                time.sleep(self._retry_interval)

        def __exit__(self, exc_type, exc, tb):
            self._cache.unlock(self._key, self._token)

    def lock(
        self, 
        key: str, 
        ex: float = 10.0, 
        block: bool = True, 
        timeout: Optional[float] = None,
        retry_interval: float = 0.05
    ) -> _LockContext:
        """
        获取锁的上下文管理器。
        
        Usage:
            with cache.lock("my_resource", ex=5) as token:
                # Critical section
                pass
        """
        return self._LockContext(self, key, ex, block, timeout, retry_interval)

    # --------------- Counters ---------------
    def incr(self, key: str, amount: int = 1) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None:
                new_val = int(amount)
                self._store[key] = _Entry(value=new_val, expire_at=None)
                return new_val
            try:
                cur = int(e.value)
            except Exception as exc:
                raise TypeError("value is not an integer") from exc
            cur += int(amount)
            e.value = cur
            return cur

    def decr(self, key: str, amount: int = 1) -> int:
        return self.incr(key, -int(amount))

    # --------------- Lists ---------------
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
                e.value.insert(0, v) # type: ignore
            return len(e.value)

    def rpush(self, key: str, *values: Any) -> int:
        with self._lock:
            e = self._ensure_list(key)
            e.value.extend(values) # type: ignore
            return len(e.value)

    def lpop(self, key: str) -> Any:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return None
            self._require_type(key, e.value, (list,))
            if not e.value: return None
            return e.value.pop(0)

    def rpop(self, key: str) -> Any:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return None
            self._require_type(key, e.value, (list,))
            if not e.value: return None
            return e.value.pop()

    def llen(self, key: str) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return 0
            self._require_type(key, e.value, (list,))
            return len(e.value)

    def lrange(self, key: str, start: int, stop: int) -> List[Any]:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return []
            self._require_type(key, e.value, (list,))
            if stop == -1:
                s = e.value[start:]
            else:
                s = e.value[start : stop + 1]
            return list(s)

    # --------------- Sets ---------------
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
            e.value.update(members) # type: ignore
            return len(e.value) - before

    def srem(self, key: str, *members: Any) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return 0
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
            if e is None: return False
            self._require_type(key, e.value, (set,))
            return member in e.value

    def smembers(self, key: str) -> set:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return set()
            self._require_type(key, e.value, (set,))
            return set(e.value)

    def scard(self, key: str) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return 0
            self._require_type(key, e.value, (set,))
            return len(e.value)

    # --------------- Hashes ---------------
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
            e.value[field] = value # type: ignore
            return added

    def hget(self, key: str, field: str, default: Any = None) -> Any:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return default
            self._require_type(key, e.value, (dict,))
            return e.value.get(field, default)

    def hgetall(self, key: str) -> Dict[str, Any]:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return {}
            self._require_type(key, e.value, (dict,))
            return dict(e.value)

    def hdel(self, key: str, *fields: str) -> int:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return 0
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
            if e is None: return 0
            self._require_type(key, e.value, (dict,))
            return len(e.value)

    def hkeys(self, key: str) -> List[str]:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return []
            self._require_type(key, e.value, (dict,))
            return list(e.value.keys())

    def hvals(self, key: str) -> List[Any]:
        with self._lock:
            e = self._get_entry(key)
            if e is None: return []
            self._require_type(key, e.value, (dict,))
            return list(e.value.values())

    # --------------- Admin ---------------
    def flushall(self) -> None:
        with self._lock:
            self._store.clear()


# 模块级单例 (Global Instance)
cache = RedisLikeCache()

__all__ = ["RedisLikeCache", "cache"]