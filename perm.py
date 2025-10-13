from __future__ import annotations

from typing import Any, Dict, Optional
import json
import time
from pathlib import Path

from nonebot.permission import Permission
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

from .config import _permissions_default, save_permissions, ensure_permissions_file
from .utils import config_dir
from nonebot.log import logger
from .kv_cache import KeyValueCache


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
_eff_perm_cache = KeyValueCache(ttl=0.5)


# ----- Config loading -----
def _default_config() -> Dict[str, Any]:
    # New schema
    return _permissions_default()


def _deep_fill(user: Dict[str, Any] | None, defaults: Dict[str, Any] | None) -> Dict[str, Any]:
    """Deep-fill user config with defaults without overwriting existing values.

    - When both sides are dicts, recurse and only add missing keys from defaults.
    - For other types or when user is missing, use user's value if present,
      otherwise take default.
    """
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
    # Ensure file presence
    try:
        ensure_permissions_file()
    except Exception:
        pass

    # Load project permissions (file); if missing/unreadable, treat as empty
    try:
        current = permissions_store.get()
        if not isinstance(current, dict):
            current = {}
    except Exception:
        current = {}

    # Build defaults from current plugins snapshot
    try:
        defaults = _default_config()
    except Exception:
        defaults = {}

    # Merge (fill missing only) and persist when changed
    def _loader() -> Dict[str, Any]:
        merged = _deep_fill(current, defaults)
        try:
            if json.dumps(merged, sort_keys=True, ensure_ascii=False) != json.dumps(current, sort_keys=True, ensure_ascii=False):
                save_permissions(merged)
                permissions_store.reload()
        except Exception:
            pass
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


def _checker_factory(feature: str):
    """
    权限检查器工厂函数，创建一个包含详细日志记录的异步检查函数。
    """
    def _get_plugin_command(name: str) -> tuple[str, Optional[str]]:
        """解析 feature 字符串，分离出插件名和命令名。"""
        if ":" in name:
            p, c = name.split(":", 1)
            return p.strip(), (c.strip() or None)
        if "_" in name:
            p, c = name.split("_", 1)
            if p and c:
                return p.strip(), c.strip()
        return name.strip(), None

    def _eval_layer(layer_cfg: Dict[str, Any] | None, event, *, layer_name: str) -> Optional[bool]:
        """
        评估单层权限配置 (插件层或命令层)。
        返回: True (明确允许), False (明确拒绝), None (未配置规则)。
        """
        # 新增: 为日志添加层级标识
        log_prefix = f"权限检查 [{layer_name}层]"

        if not isinstance(layer_cfg, dict) or not layer_cfg:
            logger.debug(f"{log_prefix} - 未找到配置，跳过。")
            return None

        # 1. 检查总开关 'enabled'
        if not bool(layer_cfg.get("enabled", True)):
            if _is_superuser(_uid(event)):
                logger.debug(f"{log_prefix} - 'enabled'为False，但用户是超级用户，忽略此规则。")
            else:
                logger.info(f"{log_prefix} - ❌ 拒绝: 配置中 'enabled' 为 False。")
                return False

        # 2. 检查白名单/黑名单
        force_f = _is_allowed_by_lists(event, layer_cfg.get("whitelist"), layer_cfg.get("blacklist"))
        if force_f is True:
            logger.info(f"{log_prefix} - ✅ 允许: 用户或群组在白名单中。")
            return True
        if force_f is False:
            logger.info(f"{log_prefix} - ❌ 拒绝: 用户或群组在黑名单中。")
            return False

        # 3. 检查场景 'scene'
        scene = str(layer_cfg.get("scene", "all"))
        if not _check_scene(scene, event):
            logger.info(f"{log_prefix} - ❌ 拒绝: 场景不匹配 (需要: '{scene}')。")
            return False

        # 4. 检查等级 'level'
        level = str(layer_cfg.get("level", "all"))
        if not _check_level(level, event):
            logger.info(f"{log_prefix} - ❌ 拒绝: 权限等级不足 (需要: '{level}')。")
            return False
        
        logger.debug(f"{log_prefix} - 通过所有检查 (enabled, 名单, scene, level)。")
        return True

    async def _checker(bot, event) -> bool:
        """
        最终的异步检查函数，整合插件和命令两个层级的权限判断。
        """
        logger.debug(f"--- 开始权限检查: feature='{feature}' ---")
        cfg = _load_cfg()

        # 全局兜底：当权限文件不存在或无任何默认项（有效配置为空）时，默认放行
        if not cfg:
            logger.info("--- 最终裁决: ✅ 允许 (原因: 权限文件/默认配置均为空，默认允许) ---")
            return True

        plugin_name, cmd_name = _get_plugin_command(feature)
        logger.debug(f"解析结果 -> 插件: '{plugin_name}', 命令: '{cmd_name}'")

        plug = cfg.get(plugin_name) or {}

        # 当该插件在配置中完全不存在（文件与默认均无该插件条目）时，默认放行
        if not plug:
            logger.info("--- 最终裁决: ✅ 允许 (原因: 插件无任何权限配置，默认允许) ---")
            return True

        # --- 第一层: 插件级检查 (top) ---
        p_cfg = plug.get("top")
        p_res = _eval_layer(p_cfg, event, layer_name="插件")
        logger.debug(f"插件层检查结果: {p_res}")

        if p_res is False:
            logger.info(f"--- 最终裁决: ❌ 拒绝 (原因: 插件层明确拒绝) ---")
            return False

        # --- 第二层: 命令级检查 (commands) ---
        c_res = None
        if cmd_name:
            c_cfg = (plug.get("commands") or {}).get(cmd_name)
            c_res = _eval_layer(c_cfg, event, layer_name="命令")
            logger.debug(f"命令层检查结果: {c_res}")
        
            if c_res is False:
                logger.info(f"--- 最终裁决: ❌ 拒绝 (原因: 命令层明确拒绝) ---")
                return False
        else:
            logger.debug("无命令名，跳过命令层检查。")

        # --- 新裁决逻辑：插件优先，命令其次（两层均需通过） ---
        # 仅对命令检查时：先看插件层，插件层通过后再看命令层；两层都通过才允许
        # 若无命令名（仅插件级权限）：仅当插件层通过时允许
        if p_res is not True:
            logger.info(f"--- 最终裁决: ❌ 拒绝 (原因: 插件层未通过: {p_res}) ---")
            return False
        if cmd_name:
            if c_res is True:
                logger.info("--- 最终裁决: ✅ 允许 (原因: 插件层与命令层均通过) ---")
                return True
            else:
                logger.info(f"--- 最终裁决: ❌ 拒绝 (原因: 命令层未通过: {c_res}) ---")
                return False
        else:
            logger.info("--- 最终裁决: ✅ 允许 (原因: 仅插件级检查且通过) ---")
            return True
    return _checker

def permission_for(feature: str) -> Permission:
    return Permission(_checker_factory(feature))


def permission_for_plugin(plugin: str) -> Permission:
    return Permission(_checker_factory(plugin))


def permission_for_cmd(plugin: str, command: str) -> Permission:
    return Permission(_checker_factory(f"{plugin}:{command}"))


def reload_permissions() -> None:
    permissions_store.reload()
