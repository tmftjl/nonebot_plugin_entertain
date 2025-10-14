from __future__ import annotations

from nonebot.plugin import PluginMetadata
from nonebot.log import logger

from .framework.registry import Plugin

__plugin_meta__ = PluginMetadata(
    name="Membership",
    description="群会员续费/到期管理，支持续费码、提醒与到期自动退群",
    usage="ww生成续费码 <xx天|月|年> / ww续费 <xx天|月|年>-<随机码> / 控制台登录",
    type="application",
)

# Ensure permission baseline for built-in system commands (not affected by root top)
P = Plugin(name="core", category="system", enabled=True, level="all", scene="all")

# Import and register commands by side-effect
from .commands import *  # noqa: F401,F403

# Optional: set up web console if enabled in config
try:
    from .console.server import setup_web_console as _setup

    _setup()
except Exception:
    logger.debug("membership 控制台挂载失败，已跳过")
    pass
