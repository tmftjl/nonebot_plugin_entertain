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
from enum import IntEnum


# ----- 轻量级权限存储 -----


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
            # 发生异常时保留之前已加载的数据
            pass

    def ensure_loaded(self) -> None:
        # 仅在首次访问时加载；不根据 mtime 自动重载
        if not self._loaded:
            self._reload()

    def get(self) -> Dict[str, Any]:
        self.ensure_loaded()
        return self._data or {}

    def reload(self) -> None:
        self._reload()


permissions_store = PermissionsStore()
# 不自动过期；通过显式 reload 来使缓存失效
_eff_perm_cache = KeyValueCache(ttl=None)


# ----- 配置加载（扁平结构）-----


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
    # 运行期仅从内存缓存读取（在启动时已预热），避免在此进行文件系统访问或扫描
    eff = _eff_perm_cache.get("effective")
    return eff or {}


# ----- 工具函数 -----

class PermLevel(IntEnum):
    LOW = 0          # all（最低等级）
    MEMBER = 1       # member
    ADMIN = 2        # admin
    OWNER = 3        # owner
    BOT_ADMIN = 4    # bot_admin
    SUPERUSER = 5    # superuser

    @staticmethod
    def from_str(s: Optional[str]) -> "PermLevel":
        k = str(s or "all").strip().lower()
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
        # 默认最宽松
        return PermLevel.LOW

def _get_bot_admin_ids() -> set[str]:
    """从 permissions.json 顶层读取机器人管理列表（可选）。

    支持的键：bot_admins, bot_managers, bot管理, bot管理员
    形如：
    {
      "top": { ... },
      "bot_admins": ["123", "456"],
      ...
    }
    或放在 top 内：{"top": {"bot_admins": ["123"]}}
    """
    try:
        cfg = _load_cfg() or {}
        tops = []
        # 顶层并列键
        for k in ("bot_admins", "bot_managers", "bot管理", "bot管理员"):
            v = cfg.get(k)
            if isinstance(v, (list, tuple, set)):
                tops.extend([str(x) for x in v if x is not None])
        # top 节点中
        top = cfg.get("top") if isinstance(cfg.get("top"), dict) else {}
        for k in ("bot_admins", "bot_managers", "bot管理", "bot管理员"):
            v = (top or {}).get(k)
            if isinstance(v, (list, tuple, set)):
                tops.extend([str(x) for x in v if x is not None])
        return set(tops)
    except Exception:
        return set()

def _user_level_rank(event) -> PermLevel:
    """计算当前事件用户的实际等级（枚举，越大权限越高）。"""
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
    # 需求等级（枚举）
    req = PermLevel.from_str(level)
    # 私聊场景下，群相关（ADMIN/OWNER）不做限制，降级为 LOW
    if isinstance(event, PrivateMessageEvent) and req in {PermLevel.ADMIN, PermLevel.OWNER}:
        req = PermLevel.LOW
    # 实际用户等级 >= 需求等级 即通过
    try:
        user_rank = _user_level_rank(event)
        return user_rank >= req
    except Exception:
        # 回退为放行（避免权限系统异常导致全拒绝）
        return True


def _check_scene(scene: str, event) -> bool:
    s = (scene or "all").strip().lower()
    if s in ("all", "both", "any"):
        # all/both/any：群聊与私聊均可
        return True
    if s == "group":
        # group：仅群聊可用
        return isinstance(event, GroupMessageEvent)
    if s == "private":
        # private：仅私聊可用
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
    # 白名单优先：users（用户 ID 列表）/ groups（群号列表）
    if _match_id_list(event, wl.get("users"), "user") or _match_id_list(event, wl.get("groups"), "group"):
        return True
    # 黑名单拦截：users（用户 ID 列表）/ groups（群号列表）
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

        # 1) 开关（enabled）
        if not bool(layer_cfg.get("enabled", True)):
            return False

        # 2) 白名单 / 黑名单
        force_f = _is_allowed_by_lists(event, layer_cfg.get("whitelist"), layer_cfg.get("blacklist"))
        if force_f is True:
            return True
        if force_f is False:
            return False

        # 3) 使用场景（群聊/私聊）
        scene = str(layer_cfg.get("scene", "all"))
        if not _check_scene(scene, event):
            return False

        # 4) 权限等级（用户角色）
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
    # 这里的 plugin 指所选类别下的子插件名
    return Permission(_checker_factory(f"{plugin}", category=category))


def permission_for_cmd(plugin: str, command: str, *, category: str = "sub") -> Permission:
    # 这里的 plugin 指所选类别下的子插件名
    return Permission(_checker_factory(f"{plugin}:{command}", category=category))


def reload_permissions() -> None:
    # 轻量级重载：采用磁盘中的权限作为当前有效状态，无需重新扫描默认配置；保持缓存与存储一致
    try:
        permissions_store.reload()
        current = permissions_store.get()
        if not isinstance(current, dict):
            current = {}
    except Exception:
        current = {}
    _eff_perm_cache.set("effective", current)


def prime_permissions_cache() -> None:
    """启动期一次性初始化：

    - 确保权限文件存在
    - 扫描默认配置并与现有文件合并
    - 将合并结果持久化到磁盘
    - 预热内存缓存以加速运行期检查
    """
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

    # 持久化并更新缓存
    try:
        save_permissions(merged)
        permissions_store.reload()
    except Exception:
        pass
    _eff_perm_cache.set("effective", merged)
