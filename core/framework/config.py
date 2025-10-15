from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Tuple

from .utils import config_dir

# Framework identifier kept for identification only; not used as a root key
FRAMEWORK_NAME = "nonebot_plugin_entertain"


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

    def _reload(self) -> None:
        try:
            text = self.path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                self._cache = data
                try:
                    self._mtime = self.path.stat().st_mtime
                except Exception:
                    self._mtime = 0.0
                self._loaded = True
                return
        except Exception:
            pass
        # fallback
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
        """Load config and deep-fill missing keys from defaults (in-memory cache).

        Existing user values are preserved; only absent keys are filled from
        the registered defaults.
        """
        self.ensure()
        self.ensure_loaded()
        merged = _deep_merge(self.defaults or {}, self._cache or {})
        # Persist filled defaults when file lacks keys
        try:
            if json.dumps(merged, sort_keys=True, ensure_ascii=False) != json.dumps(self._cache or {}, sort_keys=True, ensure_ascii=False):
                self.save(merged)
        except Exception:
            # best effort; keep merged in memory
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


@dataclass
class NamespacedConfigProxy:
    """Config proxy working on a sub-dict namespace within a single JSON file.

    This allows multiple features to share one file (e.g. entertain/config.json)
    while keeping per-feature sections like { "reg_time": { ... } }.
    """
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
        # Persist back if defaults filled new keys
        if json.dumps(eff, sort_keys=True, ensure_ascii=False) != json.dumps(sec or {}, sort_keys=True, ensure_ascii=False):
            all_cfg[self.namespace] = eff
            self._file_proxy.save(all_cfg)
        return json.loads(json.dumps(eff))

    def save(self, section_cfg: Dict[str, Any]) -> None:
        all_cfg = self._load_whole()
        all_cfg[self.namespace] = json.loads(json.dumps(section_cfg or {}))
        self._file_proxy.save(all_cfg)

    def reload_and_validate(self) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Reload config from disk and optionally validate.

        Returns (ok, cfg, error_message). If no validator is set, ok is True
        when the JSON is a dict; otherwise the validator may raise and ok
        becomes False with the error captured.
        """
        self.ensure()
        try:
            raw_text = self.path.read_text(encoding="utf-8")
            raw = json.loads(raw_text)
            if not isinstance(raw, dict):
                return False, json.loads(json.dumps(self.defaults)), "config is not a JSON object"
            if self.validator is not None:
                try:
                    self.validator(raw)
                except Exception as e:
                    return False, raw, f"validation failed: {e}"
            # update cache
            self._cache = raw
            try:
                self._mtime = self.path.stat().st_mtime
            except Exception:
                self._mtime = 0.0
            self._loaded = True
            return True, raw, None
        except Exception as e:
            return False, json.loads(json.dumps(self.defaults)), f"reload failed: {e}"

    


# ----- New unified permissions (single global file, nested: framework -> sub_plugins -> commands) -----


def _perm_entry_default(level: str = "all", scene: str = "all") -> Dict[str, Any]:
    return {
        "enabled": True,
        "level": level,
        "scene": scene,
        "whitelist": {"users": [], "groups": []},
        "blacklist": {"users": [], "groups": []},
    }


def _scan_plugins_for_permissions() -> Dict[str, Any]:
    """扫描子插件与内置系统命令，生成 permissions.json 初始结构。

    目标结构：
    {
      "top": Entry,
      "sub_plugins": {
        "<sub_plugin>": { "top": Entry, "commands": { "name": Entry } }
      },
      "system": {
        "membership": { "commands": { "name": Entry } }
      }
    }

    仅在无文件时作为首次写入的默认内容。
    """
    result: Dict[str, Any] = {"top": _perm_entry_default(), "sub_plugins": {}, "system": {}}
    try:
        # project root (two levels up from core/framework)
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

                    # collect alias names for upsert_command_defaults
                    up_names = {"upsert_command_defaults"}
                    for node_ in _ast.walk(tree):
                        if isinstance(node_, _ast.ImportFrom):
                            try:
                                for alias in node_.names:
                                    if alias.name == "upsert_command_defaults" and alias.asname:
                                        up_names.add(alias.asname)
                            except Exception:
                                pass

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
                                # upsert_command_defaults or alias called with (plugin, command)
                                if isinstance(fn, _ast.Name) and fn.id in up_names:
                                    if len(node_.args) >= 2 and all(isinstance(a, _ast.Constant) and isinstance(a.value, str) for a in node_.args[:2]):
                                        pn = str(node_.args[0].value)
                                        cn = str(node_.args[1].value)
                                        if pn == sub_name and cn:
                                            cmds.setdefault(cn, _perm_entry_default())
                        except Exception:
                            continue
            except Exception:
                return

        # 1) 扫描外部子插件目录（plugins/）
        if base.exists():
            for pdir in base.iterdir():
                _scan_one(pdir, pdir.name)

        # 2) 扫描框架内置系统功能（如 membership），收集命令到 system（扁平 commands）
        def _scan_system_one(pdir: Path, name: str) -> None:
            try:
                if not pdir.is_dir() or not (pdir / "__init__.py").exists():
                    return
                sys_map = result.setdefault("system", {})
                cmds = sys_map.setdefault("commands", {})

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

                    up_names = {"upsert_system_command_defaults", "upsert_command_defaults"}
                    for node_ in _ast.walk(tree):
                        try:
                            if isinstance(node_, _ast.Call):
                                fn = node_.func
                                if isinstance(fn, _ast.Attribute) and isinstance(fn.value, _ast.Name) and fn.value.id == "P" and fn.attr == "on_regex":
                                    for kw in node_.keywords or []:
                                        if kw.arg == "name" and isinstance(kw.value, _ast.Constant) and isinstance(kw.value.value, str):
                                            cmds.setdefault(str(kw.value.value), _perm_entry_default())
                                if isinstance(fn, _ast.Attribute) and isinstance(fn.value, _ast.Name) and fn.value.id == "P" and fn.attr == "permission_cmd":
                                    if node_.args and isinstance(node_.args[0], _ast.Constant) and isinstance(node_.args[0].value, str):
                                        cmds.setdefault(str(node_.args[0].value), _perm_entry_default())
                                if isinstance(fn, _ast.Name) and fn.id in up_names:
                                    if len(node_.args) >= 2 and all(isinstance(a, _ast.Constant) and isinstance(a.value, str) for a in node_.args[:2]):
                                        pn = str(node_.args[0].value)
                                        cn = str(node_.args[1].value)
                                        if pn == name and cn:
                                            cmds.setdefault(cn, _perm_entry_default())
                        except Exception:
                            continue
            except Exception:
                return

        # Locate built-in system package root (this file is core/framework/config.py)
        core_pkg_dir = Path(__file__).resolve().parents[1]
        if (core_pkg_dir / "__init__.py").exists():
            _scan_system_one(core_pkg_dir, "core")
    except Exception:
        # return what we have gathered so far on any unexpected error
        pass
    return result


def _permissions_default() -> Dict[str, Any]:
    # Generate a flat permissions map on demand (ephemeral).
    # This is used as the in-memory default shape; the project file is initialized from it.
    return _scan_plugins_for_permissions()


def permissions_path() -> Path:
    return config_dir() / "permissions.json"


def ensure_permissions_file() -> None:
    p = permissions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        # Initialize with scanned defaults if available; otherwise empty means "allow all"
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
        # unique + stringify + stable order
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


def optimize_permissions() -> Tuple[bool, Dict[str, Any]]:
    """Sort and normalize permissions.json for readability and consistency.

    - Ensures keys: top, sub_plugins, system
    - Normalizes entry shapes and ID lists
    - Sorts plugin and command names alphabetically
    - Removes empty containers
    Returns (changed, new_data)
    """
    data = load_permissions()
    changed = False

    def _norm_sub_plugins(sp: Any) -> Dict[str, Any]:
        if not isinstance(sp, dict):
            return {}
        out: Dict[str, Any] = {}
        for name in sorted(sp.keys(), key=lambda x: str(x)):
            node = sp.get(name)
            if not isinstance(node, dict):
                continue
            top = _normalize_entry_shape(node.get("top")) if "top" in node else _perm_entry_default()
            cmds_src = node.get("commands") if isinstance(node.get("commands"), dict) else {}
            cmds: Dict[str, Any] = {}
            for cname in sorted(cmds_src.keys(), key=lambda x: str(x)):
                centry = _normalize_entry_shape(cmds_src.get(cname))
                cmds[cname] = centry
            # keep node only if has commands or meaningful top
            out[name] = {"top": top, "commands": cmds}
        return out

def _norm_system(sys_map: Any) -> Dict[str, Any]:
    """规范化 system 节点，支持两种结构：
    - 扁平：{"commands": {...}}
    - 分组：{"<name>": {"commands": {...}}}
    按需转换为扁平结构。
    """
    if not isinstance(sys_map, dict):
        return {}
    # 扁平结构
    if isinstance(sys_map.get("commands"), dict):
        cmds_src = sys_map.get("commands") or {}
        cmds: Dict[str, Any] = {}
        for cname in sorted(cmds_src.keys(), key=lambda x: str(x)):
            cmds[cname] = _normalize_entry_shape(cmds_src.get(cname))
        return {"commands": cmds}
    # 分组结构 -> 合并为扁平
    flat_cmds: Dict[str, Any] = {}
    for name in sorted(sys_map.keys(), key=lambda x: str(x)):
        node = sys_map.get(name)
        if not isinstance(node, dict):
            continue
        cmds_src = node.get("commands") if isinstance(node.get("commands"), dict) else {}
        for cname in sorted(cmds_src.keys(), key=lambda x: str(x)):
            flat_cmds[cname] = _normalize_entry_shape(cmds_src.get(cname))
    return {"commands": flat_cmds}

    new_root: Dict[str, Any] = {}
    new_root["top"] = _normalize_entry_shape((data or {}).get("top"))
    new_root["sub_plugins"] = _norm_sub_plugins((data or {}).get("sub_plugins"))
    new_root["system"] = _norm_system((data or {}).get("system"))

    try:
        if json.dumps(new_root, ensure_ascii=False, sort_keys=False) != json.dumps(data or {}, ensure_ascii=False, sort_keys=False):
            save_permissions(new_root)
            changed = True
    except Exception:
        pass
    return changed, new_root


def _as_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, (list, tuple, set)):
        raise TypeError("expect list for id list")
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
    """Upsert defaults for a sub-plugin (flat schema)."""
    data = load_permissions()
    root = data
    sub_map = root.setdefault("sub_plugins", {})
    sp = sub_map.setdefault(plugin, {})
    d = sp.setdefault("top", _perm_entry_default())
    # Set only provided keys; strict validation happens in registry
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


# removed legacy main_plugins top helpers


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
    """Upsert defaults for a specific command under a sub-plugin (flat schema)."""
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
    """为系统命令写入默认项（不受全局 top 影响），扁平到 system.commands。"""
    data = load_permissions()
    root = data
    sys_map = root.setdefault("system", {})
    cmds = sys_map.setdefault("commands", {})
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


# removed legacy main_plugins command helpers


_CONFIG_REGISTRY: Dict[tuple[str, str], ConfigProxy] = {}


def register_plugin_config(
    plugin: str,
    defaults: Optional[Dict[str, Any]] = None,
    *,
    filename: str = "config.json",
    validator: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> ConfigProxy:
    """Register per-plugin config file (no per-plugin permissions).

    - Writes defaults if file missing
    - No default-merge on load
    - Optional validator used by reload helper
    """
    cfg_proxy = ConfigProxy(plugin=plugin, filename=filename, defaults=defaults or {}, validator=validator)
    cfg_proxy.ensure()
    _CONFIG_REGISTRY[(plugin, filename)] = cfg_proxy
    return cfg_proxy


def register_namespaced_config(
    plugin: str,
    namespace: str,
    defaults: Optional[Dict[str, Any]] = None,
    *,
    filename: str = "config.json",
) -> NamespacedConfigProxy:
    # Ensure the underlying file exists, then work on a sub-dict
    file_proxy = ConfigProxy(plugin=plugin, filename=filename, defaults={}, validator=None)
    file_proxy.ensure()
    return NamespacedConfigProxy(plugin=plugin, namespace=namespace, filename=filename, defaults=defaults or {})


def get_plugin_config(plugin: str, *, filename: str = "config.json", defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return register_plugin_config(plugin, defaults or {}, filename=filename).load()


def save_plugin_config(plugin: str, cfg: Dict[str, Any], *, filename: str = "config.json") -> None:
    register_plugin_config(plugin, {}, filename=filename).save(cfg)


def reload_plugin_config(
    plugin: str,
    *,
    filename: str = "config.json",
    validator: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Reload one plugin's config and validate.

    Returns (ok, cfg, err). If validator provided, it is used to validate
    the config; otherwise only JSON-object shape is checked.
    """
    proxy = _CONFIG_REGISTRY.get((plugin, filename)) or register_plugin_config(plugin, {}, filename=filename, validator=validator)
    return proxy.reload_and_validate()


def bootstrap_configs() -> None:
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # Ensure global permissions file exists
    try:
        ensure_permissions_file()
    except Exception:
        pass
    # No legacy migrations; first-run file is generated and then respected

def reload_all_configs() -> Tuple[bool, Dict[str, Any]]:
    """Reload all registered plugin configs and permissions.

    Returns (ok, details) where details contains per-plugin results and permissions status.
    """
    results: Dict[str, Any] = {"plugins": {}}
    ok_all = True
    for (plugin, filename), proxy in list(_CONFIG_REGISTRY.items()):
        ok, _cfg, err = proxy.reload_and_validate()
        prev = results["plugins"].get(plugin, {})
        results["plugins"][plugin] = {"ok": ok and prev.get("ok", True), "error": err or prev.get("error")}
        ok_all = ok_all and ok
    try:
        from .perm import reload_permissions

        reload_permissions()
        p_ok = True
    except Exception:
        p_ok = False
    results["permissions"] = {"ok": p_ok}
    return (ok_all and p_ok), results


def get_all_plugin_configs() -> Dict[str, Any]:
    """获取所有已注册的插件配置（从内存缓存中读取）。

    返回格式：
    {
        "system": {...},
        "plugin_name": {...},
        ...
    }
    """
    result: Dict[str, Any] = {}
    for (plugin, filename), proxy in list(_CONFIG_REGISTRY.items()):
        try:
            # 使用load()从内存缓存读取
            cfg = proxy.load()
            result[plugin] = cfg
        except Exception:
            # 出错时返回空dict
            result[plugin] = {}
    return result


def save_all_plugin_configs(configs: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
    """保存多个插件的配置。

    Args:
        configs: 格式为 {"plugin_name": {config_dict}, ...}

    Returns:
        (success, errors) - success为True表示全部成功，errors包含失败的插件及错误信息
    """
    errors: Dict[str, str] = {}
    for plugin_name, cfg in configs.items():
        if not isinstance(cfg, dict):
            errors[plugin_name] = "配置必须是JSON对象"
            continue

        # 查找对应的proxy
        proxy = None
        for (p, fname), px in list(_CONFIG_REGISTRY.items()):
            if p == plugin_name and fname == "config.json":
                proxy = px
                break

        if proxy is None:
            # 尝试注册新的
            try:
                proxy = register_plugin_config(plugin_name, cfg)
            except Exception as e:
                errors[plugin_name] = f"注册失败: {e}"
                continue

        try:
            proxy.save(cfg)
        except Exception as e:
            errors[plugin_name] = f"保存失败: {e}"

    return (len(errors) == 0), errors
