from __future__ import annotations

from nonebot.plugin import PluginMetadata
from nonebot.log import logger

from .framework.registry import Plugin

# 插件元信息（中文，UTF-8）
__plugin_meta__ = PluginMetadata(
    name="Membership",
    description="群会员开通/到期管理：支持生成续费码、群内续费、到期提醒与自动退群",
    usage="命令：控制台登录 / ww生成续费<数字><天|月|年> / ww续费<数字><天|月|年>-<随机码> / ww到期",
    type="application",
)

# 内置系统命令的权限基线（不受根级 top 影响）
P = Plugin(name="core", category="system", enabled=True, level="all", scene="all")

# 通过导入注册命令
from .commands.membership.membership import *  # noqa: F401,F403

# 挂载 Web 控制台（根据配置启用）
try:
    from .console.server import setup_web_console as _setup

    _setup()
except Exception:
    logger.debug("membership 控制台挂载失败，已跳过")
    pass

