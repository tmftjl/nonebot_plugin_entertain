from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import json
import time
from pathlib import Path

from nonebot.permission import Permission
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

from .config import (
    _permissions_default,
    save_permissions,
    ensure_permissions_file,
)
from .utils import config_dir
from nonebot.log import logger
from .cache import KeyValueCache


# ----- Lightweight permissions store -----


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
        # Only load once; no automatic reload by mtime.
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
        return json.loads(json.dumps(user))
    out: Dict[str, Any] = json.loads(json.dumps(user))
    for k, dv in (defaults or {}).items():
        if k not in out:
            out[k] = json.loads(json.dumps(dv))
        else:
            if isinstance(out[k], dict) and isinstance(dv, dict):
                out[k] = _deep_fill(out[k], dv)
    return out


def _load_cfg() -> Dict[str, Any]:
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

    def _loader() -> Dict[str, Any]:
        nonlocal current, defaults
        try:
            merged = _deep_fill(current if isinstance(current, dict) else {}, defaults if isinstance(defaults, dict) else {})
            if json.dumps(merged, sort_keys=True, ensure_ascii=False) != json.dumps(current if isinstance(current, dict) else {}, sort_keys=True, ensure_ascii=False):
                # Persist filled defaults, but do not auto-reload runtime state
                save_permissions(merged)
        except Exception:
            merged = current if isinstance(current, dict) else {}
        return merged

    eff = _eff_perm_cache.get("effective", loader=_loader)
    return eff or {}


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


def _checker_factory(feature: str, *, category: str = "sub"):
    """
    权限检查器工厂函数：支持全局 / 子插件 / 命令 三层。

    feature 取值：
    - "plugin:cmd"（命令级）
    - "plugin"（子插件级）
    - "" 或其它（仅检查全局）
    """

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

        # 1) enable switch
        if not bool(layer_cfg.get("enabled", True)):
            return False

        # 2) whitelist / blacklist
        force_f = _is_allowed_by_lists(event, layer_cfg.get("whitelist"), layer_cfg.get("blacklist"))
        if force_f is True:
            return True
        if force_f is False:
            return False

        # 3) scene
        scene = str(layer_cfg.get("scene", "all"))
        if not _check_scene(scene, event):
            return False

        # 4) level
        level = str(layer_cfg.get("level", "all"))
        if not _check_level(level, event):
            return False
        return True

    async def _checker(bot, event) -> bool:
        cfg = _load_cfg()
        if not cfg:
            return True

        sub_name, cmd_name = _parse_layers(feature)

        if category == "sub":
            # 结构：top -> sub_plugins.<plugin>.top -> commands
            g_top = cfg.get("top") if isinstance(cfg.get("top"), dict) else None
            g_res = _eval_layer(g_top, event, layer_name="全局")
            if g_res is False:
                return False
            if sub_name:
                sp = (cfg.get("sub_plugins") or {}).get(sub_name) or {}
                if sp:
                    p_res = _eval_layer(sp.get("top"), event, layer_name="子插件")
                    if p_res is False:
                        return False
                    if cmd_name:
                        c_cfg = (sp.get("commands") or {}).get(cmd_name)
                        c_res = _eval_layer(c_cfg, event, layer_name="命令")
                        if c_res is False:
                            return False
            return True
        elif category == "system":
            # 扁平结构：system.commands（不受 top 影响）
            if cmd_name:
                sys_map = (cfg.get("system") or {})
                c_cfg = (sys_map.get("commands") or {}).get(cmd_name)
                c_res = _eval_layer(c_cfg, event, layer_name="命令")
                if c_res is False:
                    return False
            return True
        else:
            # 未知类别，默认放行
            return True

    return _checker


def permission_for(feature: str, *, category: str = "sub") -> Permission:
    return Permission(_checker_factory(feature, category=category))


def permission_for_plugin(plugin: str, *, category: str = "sub") -> Permission:
    # plugin here is the plugin name under chosen category
    return Permission(_checker_factory(f"{plugin}", category=category))


def permission_for_cmd(plugin: str, command: str, *, category: str = "sub") -> Permission:
    # plugin here is the plugin name under chosen category
    return Permission(_checker_factory(f"{plugin}:{command}", category=category))


def reload_permissions() -> None:
    # Reload on-disk permissions and invalidate derived cache for immediate effect
    permissions_store.reload()
    try:
        _eff_perm_cache.invalidate("effective")
    except Exception:
        # best-effort; cache will expire shortly by TTL
        pass
