from __future__ import annotations

from nonebot import get_driver
from nonebot.log import logger

# Mount the web console on startup and close shared HTTP client on shutdown
driver = get_driver()


@driver.on_startup
async def _mount_web_console() -> None:
    try:
        from ..console.server import setup_web_console as _setup

        # Prime permissions cache so permission toggles apply on startup
        try:
            from .framework.perm import prime_permissions_cache  # type: ignore
            prime_permissions_cache()
        except Exception:
            pass

        _setup()
    except Exception as e:
        logger.warning(f"membership Web 控制台挂载失败: {e}")


@driver.on_shutdown
async def _close_http_client() -> None:
    """Close shared HTTP client on bot shutdown."""
    try:
        from .http import aclose_shared_client

        await aclose_shared_client()
    except Exception:
        pass

