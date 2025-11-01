from __future__ import annotations

# 说明：本文件为权限与插件配置的统一管理模块
# 要求：
# - 仅使用 UTF-8 编码
# - 注释为中文
# - 移除 system 相关内容（仅管理子插件权限）

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Tuple

from .utils import config_dir


# ========== 工具函数（字典合并） ==========

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k in set(a.keys()) | set(b.keys()):
            av = a.get(k)
            bv = b.get(k)
            if isinstance(av, dict) and isinstance(bv, dict):
                out[k] = _merge(av, bv)
            elif k in b:
                out[k] = bv
            else:
                out[k] = av
        return out

    a = json.loads(json.dumps(base)) if isinstance(base, dict) else {}
    b = json.loads(json.dumps(override)) if isinstance(override, dict) else {}
    return _merge(a, b)


# ========== 单文件配置代理 ==========

@dataclass
class ConfigProxy:
    plugin: str
    filename: str
    defaults: Dict[str, Any]
    validator: Optional[Callable[[Dict[str, Any]], None]] = None
    _cache: Dict[str, Any] = None  # type: ignore[assignment]
    _mtime: float = 0.0
    _loaded: bool = False

    @property
    def path(self) -> Path:
        return config_dir(self.plugin) / self.filename

    def ensure(self) -> None:
        p = self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            try:
                p.write_text(json.dumps(self.defaults, ensure_ascii=False, indent=2), encoding="utf-8")
                self._cache = json.loads(json.dumps(self.defaults))
                try:
                    self._mtime = p.stat().st_mtime
                except Exception:
                    self._mtime = 0.0
                self._loaded = True
            except Exception:
                pass
        else:
            # 若存在且内容为空对象，则写入默认值
            try:
                content = p.read_text(encoding="utf-8")
                data = json.loads(content)
                if isinstance(data, dict) and len(data) == 0:
                    p.write_text(json.dumps(self.defaults, ensure_ascii=False, indent=2), encoding="utf-8")
                    self._cache = json.loads(json.dumps(self.defaults))
                    try:
                        self._mtime = p.stat().st_mtime
                    except Exception:
                        self._mtime = 0.0
                    self._loaded = True
            except Exception:
                pass

    def _reload(self) -> None:
        try:
            text = self.path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                if self.validator is not None:
                    try:
                        self.validator(data)
                    except Exception:
                        self._cache = json.loads(json.dumps(self.defaults))
                        self._loaded = True
                        return
                self._cache = data
                try:
                    self._mtime = self.path.stat().st_mtime
                except Exception:
                    self._mtime = 0.0
                self._loaded = True
                return
        except Exception:
            pass
        # 失败回退到默认
        self._cache = json.loads(json.dumps(self.defaults))
        self._loaded = True

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._reload()
            return
        try:
            m = self.path.stat().st_mtime
        except Exception:
            m = 0.0
        if m != self._mtime:
            self._reload()

    def load(self) -> Dict[str, Any]:
        """加载配置：用默认值补齐缺失键（内存缓存）。"""
        self.ensure()
        self.ensure_loaded()
        merged = _deep_merge(self.defaults or {}, self._cache or {})
        # 文件缺键时将补齐后的结果回写
        try:
            if json.dumps(merged, sort_keys=True, ensure_ascii=False) != json.dumps(self._cache or {}, sort_keys=True, ensure_ascii=False):
                self.save(merged)
        except Exception:
            self._cache = json.loads(json.dumps(merged))
        return json.loads(json.dumps(merged))

    def save(self, cfg: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            self._cache = json.loads(json.dumps(cfg))
            try:
                self._mtime = self.path.stat().st_mtime
            except Exception:
                self._mtime = 0.0
            self._loaded = True
        except Exception:
            pass

    def reload_and_validate(self) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """从磁盘重载并校验，返回 (ok, cfg, 错误信息)。"""
        self.ensure()
        try:
            raw_text = self.path.read_text(encoding="utf-8")
            raw = json.loads(raw_text)
            if not isinstance(raw, dict):
                return False, json.loads(json.dumps(self.defaults)), "配置不是对象类型"
            if self.validator is not None:
                try:
                    self.validator(raw)
                except Exception as e:
                    return False, raw, f"校验失败: {e}"
            # 更新缓存
            self._cache = raw
            try:
                self._mtime = self.path.stat().st_mtime
            except Exception:
                self._mtime = 0.0
            self._loaded = True
            return True, raw, None
        except Exception as e:
            return False, json.loads(json.dumps(self.defaults)), f"重载失败: {e}"


# ========== 命名空间配置代理（共享文件下的子对象） ==========

@dataclass
class NamespacedConfigProxy:
    plugin: str
    namespace: str
    filename: str = "config.json"
    defaults: Dict[str, Any] = None  # type: ignore[assignment]
    _file_proxy: ConfigProxy = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._file_proxy = register_plugin_config(self.plugin, {})

    def _load_whole(self) -> Dict[str, Any]:
        return self._file_proxy.load() or {}

    def load(self) -> Dict[str, Any]:
        all_cfg = self._load_whole()
        sec = all_cfg.get(self.namespace) or {}
        eff = _deep_merge(self.defaults or {}, sec if isinstance(sec, dict) else {})
        # 将补齐结果回写到同一文件
        if json.dumps(eff, sort_keys=True, ensure_ascii=False) != json.dumps(sec or {}, sort_keys=True, ensure_ascii=False):
            all_cfg[self.namespace] = eff
            self._file_proxy.save(all_cfg)
        return json.loads(json.dumps(eff))

    def save(self, section_cfg: Dict[str, Any]) -> None:
        all_cfg = self._load_whole()
        all_cfg[self.namespace] = json.loads(json.dumps(section_cfg or {}))
        self._file_proxy.save(all_cfg)


# ========== 权限（permissions.json） ==========


def _perm_entry_default(level: str = "member", scene: str = "all") -> Dict[str, Any]:
    return {
        "enabled": True,
        "level": level,
        "scene": scene,
        "whitelist": {"users": [], "groups": []},
        "blacklist": {"users": [], "groups": []},
    }


def _scan_plugins_for_permissions() -> Dict[str, Any]:
    """扫描子插件以生成 permissions.json 初始结构（不包含 system）。"""
    result: Dict[str, Any] = {"top": _perm_entry_default(), "sub_plugins": {}}
    try:
        proj_root = Path(__file__).resolve().parents[2]
        base = proj_root / "plugins"
        sub_map = result.setdefault("sub_plugins", {})

        def _scan_one(pdir: Path, sub_name: str) -> None:
            try:
                if not pdir.is_dir() or not (pdir / "__init__.py").exists():
                    return
                node = sub_map.setdefault(sub_name, {"top": _perm_entry_default(), "commands": {}})
                node.setdefault("top", _perm_entry_default())
                cmds = node.setdefault("commands", {})

                import ast as _ast
                for f in pdir.rglob("*.py"):
                    try:
                        text = f.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        continue
                    try:
                        tree = _ast.parse(text.lstrip("\ufeff"))
                    except Exception:
                        continue

                    for node_ in _ast.walk(tree):
                        try:
                            if isinstance(node_, _ast.Call):
                                fn = node_.func
                                # P.on_regex(..., name="...")
                                if isinstance(fn, _ast.Attribute) and isinstance(fn.value, _ast.Name) and fn.value.id == "P" and fn.attr == "on_regex":
                                    for kw in node_.keywords or []:
                                        if kw.arg == "name" and isinstance(kw.value, _ast.Constant) and isinstance(kw.value.value, str):
                                            cmds.setdefault(str(kw.value.value), _perm_entry_default())
                                # P.permission_cmd("...")
                                if isinstance(fn, _ast.Attribute) and isinstance(fn.value, _ast.Name) and fn.value.id == "P" and fn.attr == "permission_cmd":
                                    if node_.args and isinstance(node_.args[0], _ast.Constant) and isinstance(node_.args[0].value, str):
                                        cmds.setdefault(str(node_.args[0].value), _perm_entry_default())
                        except Exception:
                            continue
            except Exception:
                return

        if base.exists():
            for pdir in base.iterdir():
                _scan_one(pdir, pdir.name)
    except Exception:
        pass
    return result


def _permissions_default() -> Dict[str, Any]:
    return _scan_plugins_for_permissions()


def permissions_path() -> Path:
    return config_dir() / "permissions.json"


def ensure_permissions_file() -> None:
    p = permissions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        try:
            defaults = _permissions_default()
        except Exception:
            defaults = {}
        try:
            init_data = defaults if isinstance(defaults, dict) and defaults else {}
            p.write_text(json.dumps(init_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def load_permissions() -> Dict[str, Any]:
    ensure_permissions_file()
    try:
        data = json.loads(permissions_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_permissions(data: Dict[str, Any]) -> None:
    p = permissions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _normalize_id_list(v: Any) -> list[str]:
    try:
        if not isinstance(v, (list, tuple, set)):
            return []
        return sorted({str(x) for x in v if x is not None})
    except Exception:
        return []


def _normalize_entry_shape(entry: Any) -> Dict[str, Any]:
    base = _perm_entry_default()
    out: Dict[str, Any] = {}
    try:
        e = entry if isinstance(entry, dict) else {}
        out["enabled"] = bool(e.get("enabled", base["enabled"]))
        out["level"] = str(e.get("level", base["level"]))
        out["scene"] = str(e.get("scene", base["scene"]))
        wl = e.get("whitelist") if isinstance(e.get("whitelist"), dict) else {}
        bl = e.get("blacklist") if isinstance(e.get("blacklist"), dict) else {}
        out["whitelist"] = {
            "users": _normalize_id_list((wl or {}).get("users")),
            "groups": _normalize_id_list((wl or {}).get("groups")),
        }
        out["blacklist"] = {
            "users": _normalize_id_list((bl or {}).get("users")),
            "groups": _normalize_id_list((bl or {}).get("groups")),
        }
    except Exception:
        return base
    return out

def _as_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, (list, tuple, set)):
        raise TypeError("应为列表类型")
    return [str(x) for x in v]


def upsert_plugin_defaults(
    plugin: str,
    *,
    enabled: Optional[bool] = None,
    level: Optional[str] = None,
    scene: Optional[str] = None,
    wl_users: Optional[list[str]] = None,
    wl_groups: Optional[list[str]] = None,
    bl_users: Optional[list[str]] = None,
    bl_groups: Optional[list[str]] = None,
) -> None:
    """为子插件写入顶层默认项（仅 sub_plugins）。"""
    data = load_permissions()
    root = data
    sub_map = root.setdefault("sub_plugins", {})
    sp = sub_map.setdefault(plugin, {})
    d = sp.setdefault("top", _perm_entry_default())
    if enabled is not None:
        d["enabled"] = bool(enabled)
    if level is not None:
        d["level"] = level
    if scene is not None:
        d["scene"] = scene
    if wl_users is not None:
        d.setdefault("whitelist", {}).update({"users": _as_str_list(wl_users)})
    if wl_groups is not None:
        d.setdefault("whitelist", {}).update({"groups": _as_str_list(wl_groups)})
    if bl_users is not None:
        d.setdefault("blacklist", {}).update({"users": _as_str_list(bl_users)})
    if bl_groups is not None:
        d.setdefault("blacklist", {}).update({"groups": _as_str_list(bl_groups)})
    save_permissions(root)


def upsert_command_defaults(
    plugin: str,
    command: str,
    *,
    enabled: Optional[bool] = None,
    level: Optional[str] = None,
    scene: Optional[str] = None,
    wl_users: Optional[list[str]] = None,
    wl_groups: Optional[list[str]] = None,
    bl_users: Optional[list[str]] = None,
    bl_groups: Optional[list[str]] = None,
) -> None:
    """为子插件的具体命令写入默认项（仅 sub_plugins）。"""
    data = load_permissions()
    root = data
    sub_map = root.setdefault("sub_plugins", {})
    sp = sub_map.setdefault(plugin, {})
    sp.setdefault("top", _perm_entry_default())
    cmds = sp.setdefault("commands", {})
    c = cmds.setdefault(command, _perm_entry_default())
    if enabled is not None:
        c["enabled"] = bool(enabled)
    if level is not None:
        c["level"] = level
    if scene is not None:
        c["scene"] = scene
    if wl_users is not None:
        c.setdefault("whitelist", {}).update({"users": _as_str_list(wl_users)})
    if wl_groups is not None:
        c.setdefault("whitelist", {}).update({"groups": _as_str_list(wl_groups)})
    if bl_users is not None:
        c.setdefault("blacklist", {}).update({"users": _as_str_list(bl_users)})
    if bl_groups is not None:
        c.setdefault("blacklist", {}).update({"groups": _as_str_list(bl_groups)})
    save_permissions(root)


def upsert_system_command_defaults(
    plugin: str,
    command: str,
    *,
    enabled: Optional[bool] = None,
    level: Optional[str] = None,
    scene: Optional[str] = None,
    wl_users: Optional[list[str]] = None,
    wl_groups: Optional[list[str]] = None,
    bl_users: Optional[list[str]] = None,
    bl_groups: Optional[list[str]] = None,
) -> None:
    """保留接口但不再生效：system 命令不接入外置权限。"""
    return


# ========== 配置注册与重载（供控制台与插件使用） ==========

_CONFIG_REGISTRY: Dict[tuple[str, str], ConfigProxy] = {}
_RELOAD_CALLBACKS: Dict[str, list[Callable[[], None]]] = {}
_SCHEMAS_PLUGIN: Dict[str, Dict[str, Any]] = {}
_SCHEMAS_NS: Dict[tuple[str, str], Dict[str, Any]] = {}


def register_reload_callback(plugin: str, callback: Callable[[], None]) -> None:
    """注册配置重载回调（当统一重载时会依次调用）。"""
    if plugin not in _RELOAD_CALLBACKS:
        _RELOAD_CALLBACKS[plugin] = []
    _RELOAD_CALLBACKS[plugin].append(callback)


class ConfigManager:
    """统一的配置管理器：负责启动时预热与集中重载。"""

    _instance: Optional["ConfigManager"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        pass

    def bootstrap(self) -> None:
        """启动时调用：预热必要的配置文件与权限文件。"""
        if self._initialized:
            return
        try:
            config_dir().mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            ensure_permissions_file()
        except Exception:
            pass
        for (plugin, filename), proxy in list(_CONFIG_REGISTRY.items()):
            try:
                proxy.ensure()
                proxy.ensure_loaded()
            except Exception:
                pass
        self._initialized = True

    def reload_all(self) -> Tuple[bool, Dict[str, Any]]:
        """重载所有已注册的配置并执行回调，返回结果摘要。"""
        results: Dict[str, Any] = {"plugins": {}}
        ok_all = True
        for (plugin, filename), proxy in list(_CONFIG_REGISTRY.items()):
            ok, cfg, err = proxy.reload_and_validate()
            prev = results["plugins"].get(plugin, {})
            results["plugins"][plugin] = {
                "ok": ok and prev.get("ok", True),
                "error": err or prev.get("error")
            }
            ok_all = ok_all and ok
        for plugin, callbacks in _RELOAD_CALLBACKS.items():
            for callback in callbacks:
                try:
                    callback()
                except Exception:
                    pass
        return ok_all, results


# ========== 对外接口 ==========


def register_plugin_schema(plugin: str, schema: Dict[str, Any]) -> None:
    _SCHEMAS_PLUGIN[plugin] = json.loads(json.dumps(schema or {}))


def register_namespaced_schema(plugin: str, namespace: str, schema: Dict[str, Any]) -> None:
    _SCHEMAS_NS[(plugin, namespace)] = json.loads(json.dumps(schema or {}))


def register_plugin_config(
    plugin: str,
    defaults: Dict[str, Any],
    *,
    filename: str = "config.json",
    validator: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> ConfigProxy:
    key = (plugin, filename)
    if key not in _CONFIG_REGISTRY:
        _CONFIG_REGISTRY[key] = ConfigProxy(plugin=plugin, filename=filename, defaults=defaults or {}, validator=validator)
    return _CONFIG_REGISTRY[key]


def register_namespaced_config(
    plugin: str,
    namespace: str,
    defaults: Dict[str, Any] = None,
    *,
    filename: str = "config.json",
) -> NamespacedConfigProxy:
    proxy = NamespacedConfigProxy(plugin=plugin, namespace=namespace, filename=filename, defaults=defaults or {})
    return proxy


def get_plugin_config(plugin: str, *, filename: str = "config.json", defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return register_plugin_config(plugin, defaults or {}, filename=filename).load()


def save_plugin_config(plugin: str, cfg: Dict[str, Any], *, filename: str = "config.json") -> None:
    register_plugin_config(plugin, {}, filename=filename).save(cfg or {})


def reload_plugin_config(
    plugin: str,
    *,
    filename: str = "config.json",
    validator: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    proxy = _CONFIG_REGISTRY.get((plugin, filename)) or register_plugin_config(plugin, {}, filename=filename, validator=validator)
    return proxy.reload_and_validate()


def bootstrap_configs() -> None:
    ConfigManager().bootstrap()


def reload_all_configs() -> Tuple[bool, Dict[str, Any]]:
    return ConfigManager().reload_all()

