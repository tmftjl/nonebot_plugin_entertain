from __future__ import annotations

import inspect
from typing import Any, Optional

from nonebot import on_regex
from nonebot import logger
from nonebot.matcher import Matcher

from .config import upsert_plugin_defaults, upsert_command_defaults
from .perm import permission_for_cmd, permission_for_plugin


def _infer_plugin_name() -> str:
    # Try to derive plugin name from call stack: prefer modules under
    # nonebot_plugin_entertain.plugins.<name>, falling back to file path scan.
    try:
        stack = inspect.stack()
    except Exception:
        stack = []

    # Scan several frames upward to find the plugin module context
    for depth in range(1, min(len(stack), 8)):
        try:
            frm = stack[depth]
            g = getattr(frm, "frame", None).f_globals if getattr(frm, "frame", None) else {}
            mod_name = str(g.get("__name__", ""))
            if ".plugins." in mod_name:
                suffix = mod_name.split(".plugins.", 1)[1]
                return suffix.split(".", 1)[0]
            # Fallback for this frame: try __file__ path-based inference
            mod_file = str(g.get("__file__", ""))
            if "plugins" in mod_file:
                parts = mod_file.replace("\\", "/").split("/")
                idx = len(parts) - 1 - parts[::-1].index("plugins")
                return parts[idx + 1]
        except Exception:
            continue

    return "unknown"


_LEVELS = {"all", "member", "admin", "owner", "superuser"}
_SCENES = {"all", "group", "private"}


def _validate_entry(*, enabled=None, level=None, scene=None, wl_users=None, wl_groups=None, bl_users=None, bl_groups=None) -> None:
    if enabled is not None and not isinstance(enabled, bool):
        raise TypeError("enabled must be bool")
    if level is not None and str(level) not in _LEVELS:
        raise ValueError(f"invalid level: {level}")
    if scene is not None and str(scene) not in _SCENES:
        raise ValueError(f"invalid scene: {scene}")
    def _check_list(v, name):
        if v is None:
            return
        if not isinstance(v, (list, tuple, set)):
            raise TypeError(f"{name} must be a list of ids")
    _check_list(wl_users, "wl_users")
    _check_list(wl_groups, "wl_groups")
    _check_list(bl_users, "bl_users")
    _check_list(bl_groups, "bl_groups")


class Plugin:
    """Lightweight wrapper to create matchers with unified permissions and defaults.

    - Auto-deduces plugin name from caller module path
    - Ensures plugin-level permissions skeleton exists
    - On creating a command, registers a default command permission entry
    - Binds matcher permission automatically (can be overridden)
    """

    def __init__(
        self,
        name: Optional[str] = None,
        *,
        enabled: Optional[bool] = None,
        level: Optional[str] = None,
        scene: Optional[str] = None,
        wl_users: Optional[list[str]] = None,
        wl_groups: Optional[list[str]] = None,
        bl_users: Optional[list[str]] = None,
        bl_groups: Optional[list[str]] = None,
    ) -> None:
        self.name = name or _infer_plugin_name()
        # No per-plugin config auto-creation here; plugins handle their own configs
        # Always create a plugin-level default entry; if fields provided, validate and set them
        if any(x is not None for x in (enabled, level, scene, wl_users, wl_groups, bl_users, bl_groups)):
            _validate_entry(enabled=enabled, level=level, scene=scene, wl_users=wl_users, wl_groups=wl_groups, bl_users=bl_users, bl_groups=bl_groups)
        upsert_plugin_defaults(
            self.name,
            enabled=enabled,
            level=level,
            scene=scene,
            wl_users=wl_users,
            wl_groups=wl_groups,
            bl_users=bl_users,
            bl_groups=bl_groups,
        )

    # ----- Permissions -----
    def permission(self):
        return permission_for_plugin(self.name)

    def permission_cmd(self, command: str):
        return permission_for_cmd(self.name, command)

    # ----- Builders -----
    def on_regex(
        self,
        pattern: str,
        *,
        name: str,
        enabled: Optional[bool] = None,
        level: Optional[str] = None,
        scene: Optional[str] = None,
        wl_users: Optional[list[str]] = None,
        wl_groups: Optional[list[str]] = None,
        bl_users: Optional[list[str]] = None,
        bl_groups: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> Matcher:
        # 你原来的权限和默认值设置逻辑... (这部分是正确的，保持不变)
        if any(x is not None for x in (enabled, level, scene, wl_users, wl_groups, bl_users, bl_groups)):
            _validate_entry(enabled=enabled, level=level, scene=scene, wl_users=wl_users, wl_groups=wl_groups, bl_users=bl_users, bl_groups=bl_groups)
        upsert_command_defaults(
            self.name,
            name,
            enabled=enabled,
            level=level,
            scene=scene,
            wl_users=wl_users,
            wl_groups=wl_groups,
            bl_users=bl_users,
            bl_groups=bl_groups,
        )
        if "permission" not in kwargs:
            kwargs["permission"] = self.permission_cmd(name)
        
        # 1. 先创建原始的 Matcher
        matcher = on_regex(pattern, **kwargs)

        # 2. 【核心】定义并添加用于运行时日志记录的 handler
        async def _log_command_entry():
            """这个 handler 会在命令被触发时执行"""
            logger.opt(colors=True).info(
                f"插件 <y>{self.name}</y> | 命令 <g>{name}</g> 已触发, 准备处理..."
            )

        # 3. 【核心】将这个日志 handler 添加到 matcher 中，让它最先执行
        matcher.append_handler(_log_command_entry)

        # 4. 返回添加了日志功能的 matcher
        return matcher
