from __future__ import annotations

"""Shared HTTP client utilities.

Provides a single pooled `httpx.AsyncClient` with sane defaults and helpers
to perform requests with consistent timeouts across the project.
"""

import asyncio
from typing import Optional

import httpx

from .constants import DEFAULT_HTTP_TIMEOUT

_client: Optional[httpx.AsyncClient] = None
_lock = asyncio.Lock()


async def get_shared_async_client() -> httpx.AsyncClient:
    """Return a shared `httpx.AsyncClient` with connection pooling.

    The client is created lazily and reused across the application lifetime.
    """
    global _client
    if _client is not None:
        return _client
    async with _lock:
        if _client is None:
            _client = httpx.AsyncClient(
                timeout=DEFAULT_HTTP_TIMEOUT,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return _client


async def aclose_shared_client() -> None:
    """Close the shared client if it exists."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None


async def http_get(
    url: str,
    *,
    timeout: Optional[float] = None,
    retries: int = 1,
    **kwargs,
) -> httpx.Response:
    """GET with optional retries using the shared client.

    Retries on `httpx.RequestError` and `httpx.TimeoutException`.
    """
    client = await get_shared_async_client()
    last_exc: Optional[Exception] = None
    to = DEFAULT_HTTP_TIMEOUT if timeout is None else timeout
    for attempt in range(retries + 1):
        try:
            return await client.get(url, timeout=to, **kwargs)
        except (httpx.RequestError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt < retries:
                await asyncio.sleep(min(1.0 * (attempt + 1), 2.0))
                continue
            raise

