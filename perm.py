from __future__ import annotations

import json
from typing import Any, Dict, Optional

from nonebot import get_driver
from nonebot.permission import Permission
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

from .utils import config_dir


# ----- Config loading -----
_PERM_FILE = config_dir() / "permissions.json"


def _default_config() -> Dict[str, Any]:
    return {
        "enabled": True,  # global on/off for the whole entertain plugin
        "whitelist": {"users": [], "groups": []},
        "blacklist": {"users": [], "groups": []},
        # New structured controls
        "plugins": {
            # plugin-level defaults; scene applies to all commands if not overridden
            "reg_time": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "doro": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "sick": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "musicshare": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "fortune": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "box": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "welcome": {"enabled": True, "level": "admin", "scene": "group", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "taffy": {"enabled": True, "level": "superuser", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "panel": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            # DF plugin (ported)
            "df": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
        },
        "commands": {
            # per-command overrides under each plugin
            "welcome": {
                "show": {"enabled": True, "level": "admin", "scene": "group", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "set": {"enabled": True, "level": "admin", "scene": "group", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "enable": {"enabled": True, "level": "admin", "scene": "group", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "disable": {"enabled": True, "level": "admin", "scene": "group", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            },
            "taffy": {
                "query": {"enabled": True, "level": "superuser", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            },
            "panel": {
                "upload": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "list": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "refresh": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            },
            # df ported commands
            "df": {
                "pictures_api": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "pictures_face": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "pictures_list": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "poke": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "contact": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
                "reply": {"enabled": True, "level": "superuser", "scene": "private", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}}
            },
        },
        "features": {
            # defaults per feature; can be adjusted in permissions.json
            # scene: all | group | private
            "reg_time": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "doro": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "sick": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "musicshare": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "fortune": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "box": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            # welcome reading/help default admin-only; editing always admin unless configured
            "welcome": {"enabled": True, "level": "admin", "scene": "group", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "welcome_set": {"enabled": True, "level": "admin", "scene": "group", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "welcome_clear": {"enabled": True, "level": "admin", "scene": "group", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            # new ports from yunzai
            "taffy": {"enabled": True, "level": "superuser", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
            "panel": {"enabled": True, "level": "all", "scene": "all", "whitelist": {"users": [], "groups": []}, "blacklist": {"users": [], "groups": []}},
        },
    }


def _ensure_perm_file() -> None:
    cfg_dir = _PERM_FILE.parent
    cfg_dir.mkdir(parents=True, exist_ok=True)
    if not _PERM_FILE.exists():
        try:
            _PERM_FILE.write_text(json.dumps(_default_config(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def _load_cfg() -> Dict[str, Any]:
    _ensure_perm_file()
    try:
        data = json.loads(_PERM_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _default_config()


# ----- Helpers -----
def _uid(event) -> Optional[str]:
    return str(getattr(event, "user_id", "")) or None


def _gid(event) -> Optional[str]:
    return str(getattr(event, "group_id", "")) or None


def _is_superuser(user_id: Optional[str]) -> bool:
    try:
        su = getattr(get_driver().config, "superusers", set())
        return user_id is not None and str(user_id) in {str(x) for x in su}
    except Exception:
        return False


def _has_group_role(event, role: str) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    try:
        r = getattr(getattr(event, "sender", None), "role", None)
        return str(r) == role
    except Exception:
        return False


def _check_level(level: str, event) -> bool:
    user_id = _uid(event)
    level = (level or "all").strip().lower()
    if level in ("all", "member", "user"):
        return True
    if level in ("owner",):
        return _has_group_role(event, "owner") or _is_superuser(user_id)
    if level in ("admin", "group_admin", "admin_or_owner"):
        return _has_group_role(event, "admin") or _has_group_role(event, "owner") or _is_superuser(user_id)
    if level in ("superuser", "su"):
        return _is_superuser(user_id)
    # unknown -> treat as all
    return True


def _check_scene(scene: str, event) -> bool:
    """Check if event is allowed by scene constraint.

    scene values: "all" (default), "group", "private"
    """
    s = (scene or "all").strip().lower()
    if s in ("all", "both", "any"):
        return True
    if s == "group":
        return isinstance(event, GroupMessageEvent)
    if s == "private":
        return isinstance(event, PrivateMessageEvent)
    # unknown -> treat as allowed
    return True


def _match_id_list(event, id_list: Any, kind: str) -> bool:
    if not isinstance(id_list, (list, tuple, set)):
        return False
    if kind == "user":
        uid = _uid(event)
        return uid is not None and str(uid) in {str(x) for x in id_list}
    if kind == "group":
        gid = _gid(event)
        return gid is not None and str(gid) in {str(x) for x in id_list}
    return False


def _is_allowed_by_lists(event, wl: Dict[str, Any] | None, bl: Dict[str, Any] | None) -> Optional[bool]:
    """Return True/False if list forces a decision; None if inconclusive.

    Priority: whitelist > blacklist. If in whitelist, allow. If in blacklist, deny.
    """
    wl = wl or {}
    bl = bl or {}
    if _match_id_list(event, wl.get("users"), "user") or _match_id_list(event, wl.get("groups"), "group"):
        return True
    if _match_id_list(event, bl.get("users"), "user") or _match_id_list(event, bl.get("groups"), "group"):
        return False
    return None


def _checker_factory(feature: str):
    cfg = _load_cfg()

    def _get_plugin_command(name: str) -> tuple[str, Optional[str]]:
        # support explicit "plugin:command" first
        if ":" in name:
            p, c = name.split(":", 1)
            return p.strip(), (c.strip() or None)
        # then try underscore convention "plugin_command"
        if "_" in name:
            p, c = name.split("_", 1)
            if p and c:
                return p.strip(), c.strip()
        # default: plugin only
        return name.strip(), None

    def _eval_layer(layer_cfg: Dict[str, Any] | None, event) -> Optional[bool]:
        if not isinstance(layer_cfg, dict) or not layer_cfg:
            return None
        # Feature toggle
        f_enabled = bool(layer_cfg.get("enabled", True))
        if not f_enabled and not _is_superuser(_uid(event)):
            return False
        # Lists
        force_f = _is_allowed_by_lists(event, layer_cfg.get("whitelist"), layer_cfg.get("blacklist"))
        if force_f is True:
            return True
        if force_f is False:
            return False
        # Scene and level
        if not _check_scene(str(layer_cfg.get("scene", "all")), event):
            return False
        if not _check_level(str(layer_cfg.get("level", "all")), event):
            return False
        return True

    async def _checker(bot, event) -> bool:  # type: ignore[override]
        # Global toggle
        g_enabled = bool(cfg.get("enabled", True))
        if not g_enabled and not _is_superuser(_uid(event)):
            return False

        # Global allow/deny lists
        force = _is_allowed_by_lists(event, cfg.get("whitelist"), cfg.get("blacklist"))
        if force is True:
            return True
        if force is False:
            return False

        # Resolve plugin/command
        plugin_name, cmd_name = _get_plugin_command(feature)

        plugins_cfg = cfg.get("plugins") or {}
        commands_cfg = cfg.get("commands") or {}

        # Evaluate plugin layer if present
        p_cfg = plugins_cfg.get(plugin_name)
        p_res = _eval_layer(p_cfg, event)
        if p_res is False:
            return False

        # Evaluate command layer if present
        c_cfg = None
        pc_map = commands_cfg.get(plugin_name) if isinstance(commands_cfg, dict) else None
        if isinstance(pc_map, dict) and cmd_name:
            c_cfg = pc_map.get(cmd_name)
        # For some legacy names, map welcome->show
        if c_cfg is None and plugin_name == "welcome" and not cmd_name:
            if isinstance(pc_map, dict):
                c_cfg = pc_map.get("show")
        c_res = _eval_layer(c_cfg, event)
        if c_res is False:
            return False

        # Backward compatibility: evaluate feature-level if defined
        f_cfg = (cfg.get("features") or {}).get(feature)
        f_res = _eval_layer(f_cfg, event)
        if f_res is False:
            return False

        # If any layer explicitly allowed, allow; otherwise, if nothing forbids, allow by default
        return any(x is True for x in (p_res, c_res, f_res)) or (p_res is None and c_res is None and f_res is None)

    return _checker


def permission_for(feature: str) -> Permission:
    """Return a dynamic Permission bound to feature, honoring config/permissions.json.

    - Global enable/disable with superuser override
    - Global and per-feature white/black lists
    - Multi-level permission: all/member/admin/owner/superuser
    """
    return Permission(_checker_factory(feature))


def permission_for_plugin(plugin: str) -> Permission:
    """Permission that only checks plugin-level policy."""
    return Permission(_checker_factory(plugin))


def permission_for_cmd(plugin: str, command: str) -> Permission:
    """Permission that checks both plugin-level and a command-level policy.

    It uses a composite feature name "plugin:command" and falls back to plugin-only.
    """
    return Permission(_checker_factory(f"{plugin}:{command}"))


def reload_permissions() -> None:
    """No-op placeholder kept for API symmetry; config loads fresh on each check."""
    return None
