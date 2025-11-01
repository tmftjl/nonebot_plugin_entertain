from __future__ import annotations

import inspect
from typing import Any, Optional

from nonebot import on_regex
from nonebot import logger
from nonebot.matcher import Matcher
from nonebot.permission import Permission, SUPERUSER

from .config import (
    upsert_plugin_defaults,
    upsert_command_defaults,
)
from .perm import permission_for_cmd, permission_for_plugin, PermLevel, PermScene


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


def _validate_entry(*, enabled=None, level=None, scene=None, wl_users=None, wl_groups=None, bl_users=None, bl_groups=None) -> None:
    if enabled is not None and not isinstance(enabled, bool):
        raise TypeError("enabled must be bool")
    if level is not None and not isinstance(level, PermLevel):
        raise TypeError("level must be PermLevel")
    if scene is not None and not isinstance(scene, PermScene):
        raise TypeError("scene must be PermScene")

    def _check_list(v, name):
        if v is None:
            return
        if not isinstance(v, (list, tuple, set)):
            raise TypeError(f"{name} must be a list of ids")
    _check_list(wl_users, "wl_users")
    _check_list(wl_groups, "wl_groups")
    _check_list(bl_users, "bl_users")
    _check_list(bl_groups, "bl_groups")


_PLUGIN_DISPLAY_NAMES: dict[str, str] = {}
_COMMAND_DISPLAY_NAMES: dict[str, dict[str, str]] = {}  # plugin -> {command -> display_name}


def set_plugin_display_name(plugin: str, display_name: str) -> None:
    try:
        n = str(plugin).strip()
        d = str(display_name).strip()
        if n and d:
            _PLUGIN_DISPLAY_NAMES[n] = d
    except Exception:
        pass


def get_plugin_display_names() -> dict[str, str]:
    try:
        return dict(_PLUGIN_DISPLAY_NAMES)
    except Exception:
        return {}


def set_command_display_name(plugin: str, command: str, display_name: str) -> None:
    """Set Chinese display name for a command."""
    try:
        p = str(plugin).strip()
        c = str(command).strip()
        d = str(display_name).strip()
        if p and c and d:
            if p not in _COMMAND_DISPLAY_NAMES:
                _COMMAND_DISPLAY_NAMES[p] = {}
            _COMMAND_DISPLAY_NAMES[p][c] = d
    except Exception:
        pass


def get_command_display_names() -> dict[str, dict[str, str]]:
    """Get all command display names (Chinese)."""
    try:
        return {k: dict(v) for k, v in _COMMAND_DISPLAY_NAMES.items()}
    except Exception:
        return {}


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
        category: str = "sub",  # "sub" external plugins (plugins/); "system" built-ins (not controlled)
        display_name: Optional[str] = None,
        enabled: Optional[bool] = None,
        level: Optional[PermLevel] = None,
        scene: Optional[PermScene] = None,
        wl_users: Optional[list[str]] = None,
        wl_groups: Optional[list[str]] = None,
        bl_users: Optional[list[str]] = None,
        bl_groups: Optional[list[str]] = None,
    ) -> None:
        self.name = name or _infer_plugin_name()
        self.category = category if category in ("sub", "system") else "sub"
        self._cmd_levels: dict[str, Optional[PermLevel]] = {}
        # record display name if provided
        try:
            if display_name:
                set_plugin_display_name(self.name, str(display_name))
        except Exception:
            pass
        # Create a plugin-level default entry; if fields provided, validate and set them
        if any(x is not None for x in (enabled, level, scene, wl_users, wl_groups, bl_users, bl_groups)):
            _validate_entry(enabled=enabled, level=level, scene=scene, wl_users=wl_users, wl_groups=wl_groups, bl_users=bl_users, bl_groups=bl_groups)
        if self.category == "sub":
            def _lvl_str(v):
                if v is None:
                    return None
                if isinstance(v, PermLevel):
                    return {
                        PermLevel.LOW: "all",
                        PermLevel.MEMBER: "member",
                        PermLevel.ADMIN: "admin",
                        PermLevel.OWNER: "owner",
                        PermLevel.BOT_ADMIN: "bot_admin",
                        PermLevel.SUPERUSER: "superuser",
                    }[v]
                return str(v).lower()
            def _scene_str(v):
                if v is None:
                    return None
                if isinstance(v, PermScene):
                    return {
                        PermScene.ALL: "all",
                        PermScene.GROUP: "group",
                        PermScene.PRIVATE: "private",
                    }[v]
                return str(v).lower()
            upsert_plugin_defaults(
                self.name,
                enabled=enabled,
                level=_lvl_str(level),
                scene=_scene_str(scene),
                wl_users=wl_users,
                wl_groups=wl_groups,
                bl_users=bl_users,
                bl_groups=bl_groups,
            )
        else:
            # system commands: do not write to external permissions
            pass

    # ----- Permissions -----
    def permission(self):
        return permission_for_plugin(self.name, category=self.category)

    def permission_cmd(self, command: str):
        # System commands are not controlled; only SUPERUSER respected if declared
        if self.category == "system":
            lvl = self._cmd_levels.get(command)
            if lvl == PermLevel.SUPERUSER:
                return SUPERUSER
            return Permission()
        return permission_for_cmd(self.name, command, category=self.category)

    # ----- Builders -----
    def on_regex(
        self,
        pattern: str,
        *,
        name: str,
        display_name: Optional[str] = None,
        enabled: Optional[bool] = None,
        level: Optional[PermLevel] = None,
        scene: Optional[PermScene] = None,
        wl_users: Optional[list[str]] = None,
        wl_groups: Optional[list[str]] = None,
        bl_users: Optional[list[str]] = None,
        bl_groups: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> Matcher:
        # record Chinese display name
        if display_name:
            set_command_display_name(self.name, name, display_name)

        # Upsert a command default entry; validate only when explicit fields provided
        if any(x is not None for x in (enabled, level, scene, wl_users, wl_groups, bl_users, bl_groups)):
            _validate_entry(enabled=enabled, level=level, scene=scene, wl_users=wl_users, wl_groups=wl_groups, bl_users=bl_users, bl_groups=bl_groups)
        if self.category == "sub":
            def _lvl_str(v):
                if v is None:
                    return None
                if isinstance(v, PermLevel):
                    return {
                        PermLevel.LOW: "all",
                        PermLevel.MEMBER: "member",
                        PermLevel.ADMIN: "admin",
                        PermLevel.OWNER: "owner",
                        PermLevel.BOT_ADMIN: "bot_admin",
                        PermLevel.SUPERUSER: "superuser",
                    }[v]
                return str(v).lower()
            def _scene_str(v):
                if v is None:
                    return None
                if isinstance(v, PermScene):
                    return {
                        PermScene.ALL: "all",
                        PermScene.GROUP: "group",
                        PermScene.PRIVATE: "private",
                    }[v]
                return str(v).lower()
            upsert_command_defaults(
                self.name,
                name,
                enabled=enabled,
                level=_lvl_str(level),
                scene=_scene_str(scene),
                wl_users=wl_users,
                wl_groups=wl_groups,
                bl_users=bl_users,
                bl_groups=bl_groups,
            )
            if "permission" not in kwargs:
                kwargs["permission"] = self.permission_cmd(name)
        else:
            # System commands: do not write to external permissions.
            self._cmd_levels[name] = level
            if "permission" not in kwargs and level == PermLevel.SUPERUSER:
                kwargs["permission"] = SUPERUSER

        # 1) create matcher
        matcher = on_regex(pattern, **kwargs)

        # 2) add a simple log handler to trace command entry
        async def _log_command_entry():
            logger.opt(colors=True).info(
                f"plugin <y>{self.name}</y> | command <g>{name}</g> triggered, processing..."
            )
        matcher.append_handler(_log_command_entry)

        return matcher

