from __future__ import annotations

from nonebot.plugin import PluginMetadata

from ...registry import Plugin

__plugin_meta__ = PluginMetadata(
    name="Membership Renewal",
    description="群会员续费/有效性管理，支持一键码、到期提醒与自动退群",
    usage="ww生成续费码 / ww续费<xx天|月|年>-<续费码> / ww到期",
    type="application",
)

# Ensure plugin-level permission entry exists
P = Plugin(enabled=True, level="all", scene="all")

# Import and register commands by side-effect
from . import commands as _commands  # noqa: F401

# Optional: set up web console if enabled in config
try:
    from .web_console import setup_web_console as _setup
    _setup()
except Exception:
    pass


