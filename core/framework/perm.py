from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import json
from pathlib import Path
from enum import IntEnum, Enum

from nonebot.permission import Permission
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

from .config import (
    _permissions_default,
    save_permissions,
    ensure_permissions_file,
)
from .utils import config_dir
from .cache import KeyValueCache


# ----- Lightweight permissions store -----


class PermissionsStore:
    def __init__(self) -> None:
        self._path: Path = config_dir() / "permissions.json"
        self._data: Dict[str, Any] = {}
        self._loaded: bool = False

    def _reload(self) -> None:
        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                self._data = data
                self._loaded = True
        except Exception:
            # keep previous data on error
            pass

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._reload()

    def get(self) -> Dict[str, Any]:
        self.ensure_loaded()
        return self._data or {}

    def reload(self) -> None:
        self._reload()


permissions_store = PermissionsStore()
# Do not auto-expire; rely on explicit reload to invalidate
_eff_perm_cache = KeyValueCache(ttl=None)


# ----- Config loading (flat schema) -----


def _default_config() -> Dict[str, Any]:
    return _permissions_default()


def _deep_fill(user: Dict[str, Any] | None, defaults: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(user, dict):
        return json.loads(json.dumps(defaults or {}))
    if not isinstance(defaults, dict):
        return json.loads(json.dumps(user or {}))
    out: Dict[str, Any] = json.loads(json.dumps(user or {}))
    for k, dv in (defaults or {}).items():
        if k not in out:
            out[k] = json.loads(json.dumps(dv))
        else:
            if isinstance(out[k], dict) and isinstance(dv, dict):
                out[k] = _deep_fill(out[k], dv)
    return out


def _load_cfg() -> Dict[str, Any]:
    # Runtime path: strictly read from in-memory cache
    eff = _eff_perm_cache.get("effective")
    return eff or {}


# ----- Enums -----


class PermLevel(IntEnum):
    LOW = 0          # all (lowest; not default)
    MEMBER = 1       # member (default)
    ADMIN = 2        # admin
    OWNER = 3        # owner
    BOT_ADMIN = 4    # bot_admin
    SUPERUSER = 5    # superuser

    @staticmethod
    def from_str(s: Optional[str]) -> "PermLevel":
        k = str(s or "member").strip().lower()
        if k == "all":
            return PermLevel.LOW
        if k == "member":
            return PermLevel.MEMBER
        if k == "admin":
            return PermLevel.ADMIN
        if k == "owner":
            return PermLevel.OWNER
        if k == "bot_admin":
            return PermLevel.BOT_ADMIN
        if k == "superuser":
            return PermLevel.SUPERUSER
        return PermLevel.MEMBER


class PermScene(Enum):
    ALL = "all"
    GROUP = "group"
    PRIVATE = "private"

    @staticmethod
    def from_str(s: Optional[str]) -> "PermScene":
        k = str(s or "all").strip().lower()
        if k == "group":
            return PermScene.GROUP
        if k == "private":
            return PermScene.PRIVATE
        return PermScene.ALL


# ----- Helpers -----


def _uid(event) -> Optional[str]:
    return str(getattr(event, "user_id", "")) or None


def _gid(event) -> Optional[str]:
    return str(getattr(event, "group_id", "")) or None


def _is_superuser(uid: Optional[str]) -> bool:
    try:
        from nonebot import get_driver

        su = set(get_driver().config.superusers)  # type: ignore[attr-defined]
        return bool(uid and str(uid) in {str(x) for x in su})
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


def _get_bot_admin_ids() -> set[str]:
    # Read bot admin IDs from permissions.json (key: bot_admins)
    try:
        cfg = _load_cfg() or {}
        ids: list[str] = []
        v = (cfg or {}).get("bot_admins")
        if isinstance(v, (list, tuple, set)):
            ids.extend([str(x) for x in v if x is not None])
        top = cfg.get("top") if isinstance(cfg.get("top"), dict) else {}
        v2 = (top or {}).get("bot_admins")
        if isinstance(v2, (list, tuple, set)):
            ids.extend([str(x) for x in v2 if x is not None])
        return set(ids)
    except Exception:
        return set()


def _user_level_rank(event) -> PermLevel:
    # Compute actual level of current user for this event
    uid = _uid(event)
    if _is_superuser(uid):
        return PermLevel.SUPERUSER
    try:
        if uid and str(uid) in _get_bot_admin_ids():
            return PermLevel.BOT_ADMIN
    except Exception:
        pass
    if isinstance(event, GroupMessageEvent):
        if _has_group_role(event, "owner"):
            return PermLevel.OWNER
        if _has_group_role(event, "admin"):
            return PermLevel.ADMIN
        return PermLevel.MEMBER
    if isinstance(event, PrivateMessageEvent):
        return PermLevel.MEMBER
    return PermLevel.LOW


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
    wl = wl or {}
    bl = bl or {}
    # whitelist first: users/groups
    if _match_id_list(event, wl.get("users"), "user") or _match_id_list(event, wl.get("groups"), "group"):
        return True
    # blacklist blocks: users/groups
    if _match_id_list(event, bl.get("users"), "user") or _match_id_list(event, bl.get("groups"), "group"):
        return False
    return None


def _check_level(level: str, event) -> bool:
    # required level (enum, via string mapping)
    req = PermLevel.from_str(level)
    # in private chat, do not require group roles; degrade admin/owner to LOW
    if isinstance(event, PrivateMessageEvent) and req in {PermLevel.ADMIN, PermLevel.OWNER}:
        req = PermLevel.LOW
    try:
        user_rank = _user_level_rank(event)
        return user_rank >= req
    except Exception:
        return True


def _check_scene(scene, event) -> bool:
    # scene enum check (accept enum or string)
    if isinstance(scene, PermScene):
        s = scene
    else:
        s = PermScene.from_str(str(scene or "all"))
    if s == PermScene.ALL:
        return True
    if s == PermScene.GROUP:
        return isinstance(event, GroupMessageEvent)
    if s == PermScene.PRIVATE:
        return isinstance(event, PrivateMessageEvent)
    return True


def _checker_factory(feature: str, *, category: str = "sub"):
    # Permission checker factory for three layers: global / sub-plugin / command

    def _parse_layers(name: str) -> Tuple[Optional[str], Optional[str]]:
        plugin: Optional[str] = None
        cmd: Optional[str] = None
        try:
            parts = [p.strip() for p in str(name or "").split(":") if p.strip()]
        except Exception:
            parts = []
        if len(parts) >= 2:
            plugin, cmd = parts[0], parts[1]
        elif len(parts) == 1:
            plugin = parts[0]
        return plugin or None, cmd or None

    def _eval_layer(layer_cfg: Dict[str, Any] | None, event, *, layer_name: str) -> Optional[bool]:
        if not isinstance(layer_cfg, dict) or not layer_cfg:
            return None

        # 1) switch (enabled)
        if not bool(layer_cfg.get("enabled", True)):
            return False

        # 2) whitelist / blacklist
        force_f = _is_allowed_by_lists(event, layer_cfg.get("whitelist"), layer_cfg.get("blacklist"))
        if force_f is True:
            return True
        if force_f is False:
            return False

        # 3) scene (group / private)
        scene = str(layer_cfg.get("scene", "all"))
        if not _check_scene(scene, event):
            return False

        # 4) level (user role)
        level = str(layer_cfg.get("level", "member"))
        if not _check_level(level, event):
            return False
        return True

    async def _checker(bot, event) -> bool:
        cfg = _load_cfg()
        if not cfg:
            return True

        sub_name, cmd_name = _parse_layers(feature)

        if category == "sub":
            # structure: top -> sub_plugins.<plugin>.top -> commands
            g_top = cfg.get("top") if isinstance(cfg.get("top"), dict) else None
            g_res = _eval_layer(g_top, event, layer_name="global")
            if g_res is False:
                return False
            if sub_name:
                sp = (cfg.get("sub_plugins") or {}).get(sub_name) or {}
                if sp:
                    p_res = _eval_layer(sp.get("top"), event, layer_name="sub-plugin")
                    if p_res is False:
                        return False
                    if cmd_name:
                        c_cfg = (sp.get("commands") or {}).get(cmd_name)
                        c_res = _eval_layer(c_cfg, event, layer_name="command")
                        if c_res is False:
                            return False
            return True
        else:
            # non-sub categories (e.g., system) are not controlled here
            return True

    return _checker


def permission_for(feature: str, *, category: str = "sub") -> Permission:
    return Permission(_checker_factory(feature, category=category))


def permission_for_plugin(plugin: str, *, category: str = "sub") -> Permission:
    return Permission(_checker_factory(f"{plugin}", category=category))


def permission_for_cmd(plugin: str, command: str, *, category: str = "sub") -> Permission:
    return Permission(_checker_factory(f"{plugin}:{command}", category=category))


def reload_permissions() -> None:
    # Lightweight reload from disk into cache
    try:
        permissions_store.reload()
        current = permissions_store.get()
        if not isinstance(current, dict):
            current = {}
    except Exception:
        current = {}
    _eff_perm_cache.set("effective", current)


def prime_permissions_cache() -> None:
    # One-shot init: ensure file exists, merge defaults, persist, warm cache
    try:
        ensure_permissions_file()
    except Exception:
        pass

    try:
        current = permissions_store.get()
        if not isinstance(current, dict):
            current = {}
    except Exception:
        current = {}

    try:
        defaults = _default_config()
    except Exception:
        defaults = {}

    try:
        merged = _deep_fill(current, defaults)
    except Exception:
        merged = current or {}

    # Persist and update cache
    try:
        save_permissions(merged)
        permissions_store.reload()
    except Exception:
        pass
    _eff_perm_cache.set("effective", merged)

