"""类 Redis 的统一内存缓存与锁工具 (All-in-One) - 纯异步版

- 核心：单进程内的异步安全 Key-Value 存储
- 功能：支持 String/List/Set/Hash/Counter 等数据结构
- 锁机制：内置类 Redis 的异步锁实现 (set nx)，支持阻塞获取
- 维护：后台异步任务自动清理过期键 (Janitor)
"""
from __future__ import annotations

import asyncio
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
    异步安全的类 Redis 内存缓存（单进程内）。
    集成缓存操作、数据结构操作与锁机制。
    """

    def __init__(
        self,
        *,
        cleanup_interval: Optional[float] = 30.0,
    ) -> None:
        self._store: Dict[str, _Entry] = {}
        # 简化：标准 asyncio.Lock 足够，因为没有锁重入
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._janitor_task: Optional[asyncio.Task] = None
        self._cleanup_interval: Optional[float] = cleanup_interval
        # 优化：添加一个专用锁来防止 Janitor 启动时出现并发竞争
        self._janitor_start_lock = asyncio.Lock()

    # --------------- Internal Helpers ---------------
    def _now(self) -> float:
        return time.time()

    def _is_expired(self, entry: _Entry, now: Optional[float] = None) -> bool:
        if entry.expire_at is None:
            return False
        t = self._now() if now is None else now
        return t >= entry.expire_at

    def _get_entry(self, key: str) -> Optional[_Entry]:
        """
        内部辅助函数：获取条目，假定锁已被持有。
        包含惰性删除逻辑。
        """
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

    async def _ensure_janitor_started(self) -> None:
        """在有事件循环时启动后台清理任务（优化：防止并发竞争）。"""
        
        # 优化：快速路径检查，避免不必要的锁获取
        if self._janitor_task or not self._cleanup_interval or self._cleanup_interval <= 0:
            return
        
        # 优化：使用专用锁确保只有一个任务可以创建 Janitor
        async with self._janitor_start_lock:
            # 双重检查，防止等待锁期间其他任务已完成创建
            if self._janitor_task:
                return
            
            try:
                loop = asyncio.get_running_loop()
                self._janitor_task = loop.create_task(self._janitor_loop(self._cleanup_interval))
            except RuntimeError:
                # 尚未进入事件循环，延迟启动 (下次调用时会重试)
                pass

    async def _janitor_loop(self, interval: float) -> None:
        """异步后台定期清理任务"""
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(interval)
                now = self._now()
                async with self._lock:
                    expired = [
                        k
                        for k, e in self._store.items()
                        if e.expire_at is not None and now >= e.expire_at
                    ]
                    for k in expired:
                        self._store.pop(k, None)
        except asyncio.CancelledError:
            pass

    async def aclose(self) -> None:
        """关闭后台清理任务。"""
        self._stop_event.set()
        if self._janitor_task:
            self._janitor_task.cancel()
            try:
                await self._janitor_task
            except Exception:
                pass

    # --------------- Basic KV ---------------
    async def set(
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

        await self._ensure_janitor_started()
        async with self._lock:
            exists = self._get_entry(key) is not None
            if nx and exists:
                return False
            if xx and not exists:
                return False
            
            expire_at = None if ttl_seconds is None else (self._now() + ttl_seconds)
            self._store[key] = _Entry(value=value, expire_at=expire_at)
            return True

    async def get(self, key: str, default: Any = None) -> Any:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            return default if e is None else e.value

    async def getset(self, key: str, value: Any) -> Any:
        await self._ensure_janitor_started()
        async with self._lock:
            # 1. 获取旧值和旧的 TTL
            old_val = None
            ttl_seconds: Optional[float] = None
            old_entry = self._get_entry(key)
            
            if old_entry is not None:
                old_val = old_entry.value
                if old_entry.expire_at is not None:
                    ttl_seconds = max(0.0, old_entry.expire_at - self._now())
            
            # 2. 设置新值，并保留旧的 TTL
            expire_at = None if ttl_seconds is None else (self._now() + ttl_seconds)
            self._store[key] = _Entry(value=value, expire_at=expire_at)
            return old_val

    async def mset(self, mapping: Dict[str, Any]) -> None:
        await self._ensure_janitor_started()
        async with self._lock:
            for k, v in mapping.items():
                self._store[k] = _Entry(value=v, expire_at=None)

    async def mget(self, keys: Iterable[str]) -> List[Any]:
        await self._ensure_janitor_started()
        async with self._lock:
            res: List[Any] = []
            for k in keys:
                e = self._get_entry(k)
                res.append(None if e is None else e.value)
            return res

    async def delete(self, *keys: str) -> int:
        removed = 0
        await self._ensure_janitor_started()
        async with self._lock:
            for k in keys:
                # 使用 _get_entry 来正确处理已过期的键
                if self._get_entry(k) is not None:
                    self._store.pop(k, None)
                    removed += 1
                # 也处理一下 _get_entry 可能没清理的（比如刚过期）
                elif k in self._store:
                     self._store.pop(k, None)
                     removed += 1
            return removed

    async def exists(self, *keys: str) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            return sum(1 for k in keys if self._get_entry(k) is not None)

    async def keys(self, pattern: Optional[str] = None) -> List[str]:
        """Simple keys implementation supporting prefix/suffix/contains wildcards (*)."""
        await self._ensure_janitor_started()
        async with self._lock:
            all_keys = [k for k in list(self._store.keys()) if self._get_entry(k) is not None]
        
        if not pattern or pattern == "*":
            return all_keys
        
        # 简化通配符匹配
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
    async def expire(self, key: str, seconds: float) -> bool:
        return await self.pexpire(key, int(seconds * 1000))

    async def pexpire(self, key: str, milliseconds: int) -> bool:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None:
                return False
            e.expire_at = self._now() + max(0.0, milliseconds / 1000.0)
            return True

    async def persist(self, key: str) -> bool:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None:
                return False
            e.expire_at = None
            return True

    async def ttl(self, key: str) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return -2 # 键不存在或已过期
            if e.expire_at is None: return -1 # 键存在但无过期
            return int(round(max(0.0, e.expire_at - self._now())))

    async def pttl(self, key: str) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return -2
            if e.expire_at is None: return -1
            return int(round(max(0.0, (e.expire_at - self._now()) * 1000)))

    # --------------- Locking (Unified) ---------------
    
    async def try_lock(self, key: str, token: str, ex: float = 10.0) -> bool:
        """尝试非阻塞获取锁。底层使用 SET key token EX ex NX。"""
        return await self.set(key, token, ex=ex, nx=True)

    async def unlock(self, key: str, token: str) -> bool:
        """安全释放锁：仅当 token 匹配时删除 key。"""
        async with self._lock:
            # 必须用 _get_entry 检查，以尊重锁的过期
            e = self._get_entry(key)
            cur = None if e is None else e.value
            if cur == token:
                self._store.pop(key, None)
                return True
            return False

    async def extend_lock(self, key: str, token: str, ex: float) -> bool:
        """锁续期：仅当 token 匹配时更新过期时间。"""
        async with self._lock:
            e = self._get_entry(key)
            cur = None if e is None else e.value
            if cur == token:
                e.expire_at = self._now() + max(0.0, float(ex))
                return True
            return False

    class _AsyncLockContext:
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

        async def __aenter__(self) -> str:
            deadline = None
            if self._block and self._timeout is not None:
                deadline = time.time() + self._timeout

            while True:
                got = await self._cache.try_lock(self._key, self._token, ex=self._ex)
                if got:
                    return self._token
                
                if not self._block:
                    raise TimeoutError(f"Could not acquire lock for key: {self._key}")
                
                if deadline is not None and time.time() >= deadline:
                    raise TimeoutError(f"Acquire lock timeout for key: {self._key}")
                
                await asyncio.sleep(self._retry_interval)

        async def __aexit__(self, exc_type, exc, tb):
            try:
                await self._cache.unlock(self._key, self._token)
            except Exception:
                pass

    def lock(
        self, 
        key: str, 
        ex: float = 10.0, 
        block: bool = True, 
        timeout: Optional[float] = None,
        retry_interval: float = 0.05
    ) -> _AsyncLockContext:
        """
        获取锁的上下文管理器 (async with)。
        
        Usage:
            async with cache.lock("my_resource", ex=5) as token:
                # Critical section
                pass
        """
        return self._AsyncLockContext(self, key, ex, block, timeout, retry_interval)

    # --------------- Counters ---------------
    async def incr(self, key: str, amount: int = 1) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
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

    async def decr(self, key: str, amount: int = 1) -> int:
        return await self.incr(key, -int(amount))

    # --------------- Lists (Internal Helpers) ---------------
    def _ensure_list(self, key: str) -> _Entry:
        """内部辅助，假定锁已被持有"""
        e = self._get_entry(key)
        if e is None:
            e = _Entry(value=[], expire_at=None)
            self._store[key] = e
        self._require_type(key, e.value, (list,))
        return e

    # --------------- Lists (Public API) ---------------
    async def lpush(self, key: str, *values: Any) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._ensure_list(key)
            e.value.reverse() # 保持插入顺序
            e.value.extend(values)
            e.value.reverse()
            # for v in values:
            #     e.value.insert(0, v) # type: ignore
            return len(e.value)

    async def rpush(self, key: str, *values: Any) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._ensure_list(key)
            e.value.extend(values) # type: ignore
            return len(e.value)

    async def lpop(self, key: str) -> Any:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return None
            self._require_type(key, e.value, (list,))
            if not e.value: return None
            return e.value.pop(0)

    async def rpop(self, key: str) -> Any:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return None
            self._require_type(key, e.value, (list,))
            if not e.value: return None
            return e.value.pop()

    async def llen(self, key: str) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return 0
            self._require_type(key, e.value, (list,))
            return len(e.value)

    async def lrange(self, key: str, start: int, stop: int) -> List[Any]:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return []
            self._require_type(key, e.value, (list,))
            if stop == -1:
                s = e.value[start:]
            else:
                s = e.value[start : stop + 1]
            return list(s)

    # --------------- Sets (Internal Helpers) ---------------
    def _ensure_set(self, key: str) -> _Entry:
        """内部辅助，假定锁已被持有"""
        e = self._get_entry(key)
        if e is None:
            e = _Entry(value=set(), expire_at=None)
            self._store[key] = e
        self._require_type(key, e.value, (set,))
        return e

    # --------------- Sets (Public API) ---------------
    async def sadd(self, key: str, *members: Any) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._ensure_set(key)
            before = len(e.value)
            e.value.update(members) # type: ignore
            return len(e.value) - before

    async def srem(self, key: str, *members: Any) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return 0
            self._require_type(key, e.value, (set,))
            removed = 0
            for m in members:
                if m in e.value:
                    e.value.remove(m)
                    removed += 1
            return removed

    async def sismember(self, key: str, member: Any) -> bool:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return False
            self._require_type(key, e.value, (set,))
            return member in e.value

    async def smembers(self, key: str) -> set:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return set()
            self._require_type(key, e.value, (set,))
            return set(e.value)

    async def scard(self, key: str) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return 0
            self._require_type(key, e.value, (set,))
            return len(e.value)

    # --------------- Hashes (Internal Helpers) ---------------
    def _ensure_hash(self, key: str) -> _Entry:
        """内部辅助，假定锁已被持有"""
        e = self._get_entry(key)
        if e is None:
            e = _Entry(value={}, expire_at=None)
            self._store[key] = e
        self._require_type(key, e.value, (dict,))
        return e

    # --------------- Hashes (Public API) ---------------
    async def hset(self, key: str, field: str, value: Any) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._ensure_hash(key)
            added = 0 if field in e.value else 1
            e.value[field] = value # type: ignore
            return added

    async def hget(self, key: str, field: str, default: Any = None) -> Any:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return default
            self._require_type(key, e.value, (dict,))
            return e.value.get(field, default)

    async def hgetall(self, key: str) -> Dict[str, Any]:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return {}
            self._require_type(key, e.value, (dict,))
            return dict(e.value)

    async def hdel(self, key: str, *fields: str) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return 0
            self._require_type(key, e.value, (dict,))
            removed = 0
            for f in fields:
                if f in e.value:
                    del e.value[f]
                    removed += 1
            return removed

    async def hlen(self, key: str) -> int:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return 0
            self._require_type(key, e.value, (dict,))
            return len(e.value)

    async def hkeys(self, key: str) -> List[str]:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return []
            self._require_type(key, e.value, (dict,))
            return list(e.value.keys())

    async def hvals(self, key: str) -> List[Any]:
        await self._ensure_janitor_started()
        async with self._lock:
            e = self._get_entry(key)
            if e is None: return []
            self._require_type(key, e.value, (dict,))
            return list(e.value.values())

    # --------------- Admin ---------------
    async def flushall(self) -> None:
        await self._ensure_janitor_started()
        async with self._lock:
            self._store.clear()


# 模块级单例 (Global Instance)
cache = RedisLikeCache()

__all__ = ["RedisLikeCache", "cache"]