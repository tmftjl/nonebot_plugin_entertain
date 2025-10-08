from __future__ import annotations

from typing import Any, Dict, Optional
import json
import time
from pathlib import Path

from nonebot.permission import Permission
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

from .config import _permissions_default
from .utils import config_dir


# ----- Embedded permissions store (merged from permissions_store.py) -----


class PermissionsStore:
    def __init__(self) -> None:
        self._path: Path = config_dir() / "permissions.json"
        self._data: Dict[str, Any] = {}
        self._mtime: float = 0.0
        self._loaded: bool = False
        self._last_check: float = 0.0

    def _reload(self) -> None:
        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                self._data = data
                self._mtime = self._path.stat().st_mtime
                self._loaded = True
        except Exception:
            # keep previous data on error
            pass

    def ensure_loaded(self) -> None:
        now = time.time()
        # throttle mtime checks to avoid too frequent stat calls
        if not self._loaded or (now - self._last_check) > 0.5:
            self._last_check = now
            try:
                m = self._path.stat().st_mtime
            except Exception:
                m = 0.0
            if (not self._loaded) or (m != self._mtime):
                self._reload()

    def get(self) -> Dict[str, Any]:
        self.ensure_loaded()
        return self._data or {}

    def reload(self) -> None:
        self._reload()


permissions_store = PermissionsStore()


# ----- Config loading -----
def _default_config() -> Dict[str, Any]:
    # New schema
    return _permissions_default()


def _load_cfg() -> Dict[str, Any]:
    try:
        cfg = permissions_store.get()
        if isinstance(cfg, dict) and cfg:
            return cfg
    except Exception:
        pass
    return _default_config()

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
    return True


def _check_scene(scene: str, event) -> bool:
    s = (scene or "all").strip().lower()
    if s in ("all", "both", "any"):
        return True
    if s == "group":
        return isinstance(event, GroupMessageEvent)
    if s == "private":
        return isinstance(event, PrivateMessageEvent)
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
    wl = wl or {}
    bl = bl or {}
    if _match_id_list(event, wl.get("users"), "user") or _match_id_list(event, wl.get("groups"), "group"):
        return True
    if _match_id_list(event, bl.get("users"), "user") or _match_id_list(event, bl.get("groups"), "group"):
        return False
    return None


def _checker_factory(feature: str):
    def _get_plugin_command(name: str) -> tuple[str, Optional[str]]:
        if ":" in name:
            p, c = name.split(":", 1)
            return p.strip(), (c.strip() or None)
        if "_" in name:
            p, c = name.split("_", 1)
            if p and c:
                return p.strip(), c.strip()
        return name.strip(), None

    def _eval_layer(layer_cfg: Dict[str, Any] | None, event) -> Optional[bool]:
        if not isinstance(layer_cfg, dict) or not layer_cfg:
            return None
        if not bool(layer_cfg.get("enabled", True)) and not _is_superuser(_uid(event)):
            return False
        force_f = _is_allowed_by_lists(event, layer_cfg.get("whitelist"), layer_cfg.get("blacklist"))
        if force_f is True:
            return True
        if force_f is False:
            return False
        if not _check_scene(str(layer_cfg.get("scene", "all")), event):
            return False
        if not _check_level(str(layer_cfg.get("level", "all")), event):
            return False
        return True

    async def _checker(bot, event) -> bool:  # type: ignore[override]
        cfg = _load_cfg()
        # Global layer (top-level fields in target schema)
        g_cfg = cfg
        g_enabled = bool(g_cfg.get("enabled", True))
        if not g_enabled and not _is_superuser(_uid(event)):
            return False
        force = _is_allowed_by_lists(event, g_cfg.get("whitelist"), g_cfg.get("blacklist"))
        if force is True:
            return True
        if force is False:
            return False
        if not _check_scene(str(g_cfg.get("scene", "all")), event):
            return False
        if not _check_level(str(g_cfg.get("level", "all")), event):
            return False

        # Plugin and command layers
        plugin_name, cmd_name = _get_plugin_command(feature)
        plug = cfg.get(plugin_name) or {}
        p_cfg = plug.get("top")
        p_res = _eval_layer(p_cfg, event)
        if p_res is False:
            return False
        c_cfg = None
        if cmd_name:
            c_cfg = (plug.get("commands") or {}).get(cmd_name)
        c_res = _eval_layer(c_cfg, event)
        if c_res is False:
            return False
        return any(x is True for x in (p_res, c_res)) or (p_res is None and c_res is None)

    return _checker


def permission_for(feature: str) -> Permission:
    return Permission(_checker_factory(feature))


def permission_for_plugin(plugin: str) -> Permission:
    return Permission(_checker_factory(plugin))


def permission_for_cmd(plugin: str, command: str) -> Permission:
    return Permission(_checker_factory(f"{plugin}:{command}"))


def reload_permissions() -> None:
    permissions_store.reload()
