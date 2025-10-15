from __future__ import annotations

from nonebot.plugin import PluginMetadata
from nonebot.log import logger

from .framework.registry import Plugin

# 插件元信息（中文，UTF-8）
__plugin_meta__ = PluginMetadata(
    name="会员与控制台",
    description="群会员到期提醒/自动退群，续费码生成与兑换，简易 Web 控制台",
    usage="命令：控制台登录 / ww生成续费<数字><天|月|年> / ww续费<数字><天|月|年>-<随机码> / ww到期",
    type="application",
)

# 系统命令，不受全局 top 影响
P = Plugin(name="core", category="system", enabled=True, level="all", scene="all")

# 注册系统命令
from .commands.membership.membership import *  # noqa: F401,F403

# 挂载 Web 控制台（需要在系统配置中开启）
try:
    from ..console.server import setup_web_console as _setup

    _setup()
except Exception as e:
    logger.warning(f"membership Web 控制台挂载失败: {e}")
    pass

