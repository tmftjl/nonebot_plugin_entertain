from __future__ import annotations

# 说明：本文件负责“权限检查器”的实现与缓存管理
# - 仅使用 UTF-8 编码；所有注释均为中文
# - 权限结构：全局(top) → 子插件(sub_plugins.<插件>.top) → 命令(commands.<命令>)
# - 检查顺序：开关(enabled) → 白/黑名单 → 场景(群/私) → 角色等级

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


# ----- 轻量级权限存储（内存缓存 + JSON 文件） -----


class PermissionsStore:
    def __init__(self) -> None:
        # 权限文件保存路径：config/permissions.json
        self._path: Path = config_dir() / "permissions.json"
        self._data: Dict[str, Any] = {}
        self._loaded: bool = False

    def _reload(self) -> None:
        # 从磁盘读取并更新内存缓存；失败时保留旧数据
        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                self._data = data
                self._loaded = True
        except Exception:
            # 读取失败时忽略，保留已有数据
            pass

    def ensure_loaded(self) -> None:
        # 首次访问时加载一次
        if not self._loaded:
            self._reload()

    def get(self) -> Dict[str, Any]:
        # 获取当前权限数据（内存缓存）
        self.ensure_loaded()
        return self._data or {}

    def reload(self) -> None:
        # 主动触发从磁盘重载
        self._reload()


permissions_store = PermissionsStore()
# 不设置自动过期；依赖显式重载来失效缓存
_eff_perm_cache = KeyValueCache(ttl=None)


# ----- 读取与合并默认配置（展平后的结构） -----


def _default_config() -> Dict[str, Any]:
    # 生成默认的权限结构（扫描子插件与命令）
    return _permissions_default()


def _deep_fill(user: Dict[str, Any] | None, defaults: Dict[str, Any] | None) -> Dict[str, Any]:
    # 用默认值递归补齐缺失键（避免直接引用导致的修改）
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
    # 运行时仅从内存缓存读取（由重载函数负责更新）
    eff = _eff_perm_cache.get("effective")
    return eff or {}


# ----- 枚举：权限等级与场景 -----


class PermLevel(IntEnum):
    LOW = 0          # 所有人（最低，不作为默认值）
    MEMBER = 1       # 群员（默认）
    ADMIN = 2        # 群管理
    OWNER = 3        # 群主
    BOT_ADMIN = 4    # 机器人管理员（在 permissions.json 中配置）
    SUPERUSER = 5    # NoneBot 超级用户

    @staticmethod
    def from_str(s: Optional[str]) -> "PermLevel":
        # 将字符串映射为内部等级枚举
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
    ALL = "all"        # 群聊 / 私聊均可
    GROUP = "group"     # 仅群聊
    PRIVATE = "private"  # 仅私聊

    @staticmethod
    def from_str(s: Optional[str]) -> "PermScene":
        # 将字符串映射为内部场景枚举
        k = str(s or "all").strip().lower()
        if k == "group":
            return PermScene.GROUP
        if k == "private":
            return PermScene.PRIVATE
        return PermScene.ALL


# ----- 辅助函数：事件与用户/群信息提取 -----


def _uid(event) -> Optional[str]:
    # 提取用户 ID（字符串）
    return str(getattr(event, "user_id", "")) or None


def _gid(event) -> Optional[str]:
    # 提取群 ID（字符串）
    return str(getattr(event, "group_id", "")) or None


def _is_superuser(uid: Optional[str]) -> bool:
    # 判断是否为 NoneBot 超级用户
    try:
        from nonebot import get_driver

        su = set(get_driver().config.superusers)  # type: ignore[attr-defined]
        return bool(uid and str(uid) in {str(x) for x in su})
    except Exception:
        return False


def _has_group_role(event, role: str) -> bool:
    # 判断群消息事件中，发送者是否具有指定群内角色
    if not isinstance(event, GroupMessageEvent):
        return False
    try:
        r = getattr(getattr(event, "sender", None), "role", None)
        return str(r) == role
    except Exception:
        return False


def _get_bot_admin_ids() -> set[str]:
    # 从 permissions.json 中读取机器人管理员 ID（全局/顶层）
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
    # 计算当前事件对应用户的实际权限等级
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
    # 在白/黑名单中匹配用户或群 ID
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
    # 先白名单（命中则放行），再黑名单（命中则拦截），都未命中返回 None
    wl = wl or {}
    bl = bl or {}
    # 白名单：users/groups
    if _match_id_list(event, wl.get("users"), "user") or _match_id_list(event, wl.get("groups"), "group"):
        return True
    # 黑名单：users/groups
    if _match_id_list(event, bl.get("users"), "user") or _match_id_list(event, bl.get("groups"), "group"):
        return False
    return None


def _check_level(level: str, event) -> bool:
    # 角色等级校验；私聊中不要求群内角色（admin/owner 视作最低）
    req = PermLevel.from_str(level)
    if isinstance(event, PrivateMessageEvent) and req in {PermLevel.ADMIN, PermLevel.OWNER}:
        req = PermLevel.LOW
    try:
        user_rank = _user_level_rank(event)
        return user_rank >= req
    except Exception:
        return True


def _check_scene(scene, event) -> bool:
    # 场景校验（接受枚举或字符串）
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
    # 构造权限检查器：依次检查 全局 / 子插件 / 命令 三层

    def _parse_layers(name: str) -> Tuple[Optional[str], Optional[str]]:
        # 解析传入的标识：形如 "plugin:command" 或 "plugin"
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
        # 评估单层配置：若返回 False 则直接拦截；True 表示通过；None 表示未命中配置
        if not isinstance(layer_cfg, dict) or not layer_cfg:
            return None

        # 1) 开关（enabled）
        if not bool(layer_cfg.get("enabled", True)):
            return False

        # 2) 白/黑名单
        force_f = _is_allowed_by_lists(event, layer_cfg.get("whitelist"), layer_cfg.get("blacklist"))
        if force_f is True:
            return True
        if force_f is False:
            return False

        # 3) 场景（群/私）
        scene = str(layer_cfg.get("scene", "all"))
        if not _check_scene(scene, event):
            return False

        # 4) 角色等级
        level = str(layer_cfg.get("level", "member"))
        if not _check_level(level, event):
            return False
        return True

    async def _checker(bot, event) -> bool:
        # 核心检查流程：全局 → 插件总开关 → 命令开关/规则
        cfg = _load_cfg()
        if not cfg:
            # 未加载到配置时，默认放行（避免误杀）
            return True

        sub_name, cmd_name = _parse_layers(feature)

        if category == "sub":
            # 结构：top → sub_plugins.<plugin>.top → sub_plugins.<plugin>.commands.<command>
            g_top = cfg.get("top") if isinstance(cfg.get("top"), dict) else None
            g_res = _eval_layer(g_top, event, layer_name="global")
            if g_res is False:
                return False

            if sub_name:
                sp_map = cfg.get("sub_plugins") if isinstance(cfg.get("sub_plugins"), dict) else {}
                sp = sp_map.get(sub_name) if isinstance(sp_map.get(sub_name), dict) else {}

                # 修正：务必检查“插件的总开关”（top），即使节点为空也不跳过
                p_res = _eval_layer((sp or {}).get("top"), event, layer_name="sub-plugin")
                if p_res is False:
                    return False

                if cmd_name:
                    c_cfg = ((sp or {}).get("commands") or {}).get(cmd_name)
                    c_res = _eval_layer(c_cfg, event, layer_name="command")
                    if c_res is False:
                        return False
            return True
        else:
            # 非 sub 类别（例如 system）不在此受控
            return True

    return _checker


def permission_for(feature: str, *, category: str = "sub") -> Permission:
    # 返回通用的权限对象（feature 可为 "plugin" 或 "plugin:command"）
    return Permission(_checker_factory(feature, category=category))


def permission_for_plugin(plugin: str, *, category: str = "sub") -> Permission:
    # 返回“插件级别”的权限对象（受“插件总开关”控制）
    return Permission(_checker_factory(f"{plugin}", category=category))


def permission_for_cmd(plugin: str, command: str, *, category: str = "sub") -> Permission:
    # 返回“命令级别”的权限对象（受全局/插件/命令三层控制）
    return Permission(_checker_factory(f"{plugin}:{command}", category=category))


def reload_permissions() -> None:
    # 轻量重载：从磁盘更新内存缓存（控制台保存后调用）
    try:
        permissions_store.reload()
        current = permissions_store.get()
        if not isinstance(current, dict):
            current = {}
    except Exception:
        current = {}
    _eff_perm_cache.set("effective", current)


def prime_permissions_cache() -> None:
    # 启动时预热：确保文件存在 → 读取当前 → 与默认结构补齐 → 写回 → 缓存生效
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

    # 持久化并刷新缓存
    try:
        save_permissions(merged)
        permissions_store.reload()
    except Exception:
        pass
    _eff_perm_cache.set("effective", merged)

