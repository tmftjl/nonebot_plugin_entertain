from __future__ import annotations

from nonebot.log import logger
# 挂载 Web 控制台（需要在系统配置中开启）
try:
    from ..console.server import setup_web_console as _setup

    _setup()
except Exception as e:
    logger.warning(f"membership Web 控制台挂载失败: {e}")
    pass

