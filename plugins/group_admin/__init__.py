from __future__ import annotations

"""群管插件入口

按功能拆分为多个模块，避免命令挤在一个文件：
- basic：退群/改群名片/改群名称/群列表/按序号群发
- mute：禁言/解禁/全体禁言
- admin_ops：设置/取消管理员、踢人/拉黑踢
- message_ops：撤回、设精华/取消精华
- banwords：违禁词开关、增删清、列表、动作与拦截
"""

from ...core.api import Plugin

# 建立插件级默认项（仅一次）；子模块中使用 Plugin() 即可注册命令
_P = Plugin(name="group_admin", display_name="群管", enabled=True, level="all", scene="all")

# 导入子模块以注册其命令和拦截器
from . import mute as _mute  # noqa: F401
from . import admin_ops as _admin_ops  # noqa: F401
from . import message_ops as _message_ops  # noqa: F401
from . import banwords as _banwords  # noqa: F401

