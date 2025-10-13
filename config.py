from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Tuple

from .utils import config_dir

# Framework identifier used for nested permissions
# This package name is the framework name by design
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
    """Scan bundled sub-plugins to build a nested permissions map.

    Structure:
    {
      FRAMEWORK_NAME: {
        "top": Entry,
        "sub_plugins": {
          "<sub_plugin>": {
            "top": Entry,
            "commands": { "name": Entry }
          }
        }
      }
    }

    This is used only to bootstrap a sensible initial permissions.json when
    none exists. It does NOT mutate any existing user configuration.
    """
    result: Dict[str, Any] = {}
    try:
        base = Path(__file__).parent / "plugins"
        if not base.exists():
            return result
        # Initialize framework root
        fw = result.setdefault(FRAMEWORK_NAME, {"top": _perm_entry_default(), "sub_plugins": {}})
        sub_map = fw.setdefault("sub_plugins", {})

        for pdir in base.iterdir():
            try:
                if not pdir.is_dir() or not (pdir / "__init__.py").exists():
                    continue
                sub_name = pdir.name
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
                continue
    except Exception:
        # return what we have gathered so far on any unexpected error
        pass
    return result


def _permissions_default() -> Dict[str, Any]:
    # Generate a nested permissions map on demand (ephemeral) for the framework.
    # This is used as the in-memory default shape; the project file should not
    # be auto-populated from this by default.
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
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # On error or non-dict, return empty; merging with defaults and persistence
    # will be handled by permission layer.
    return {}


def save_permissions(data: Dict[str, Any]) -> None:
    p = permissions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


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
    """Upsert defaults for a sub-plugin under the framework namespace.

    Note: `plugin` here refers to the sub-plugin name inside the framework.
    """
    data = load_permissions()
    fw = data.setdefault(FRAMEWORK_NAME, {})
    sub_map = fw.setdefault("sub_plugins", {})
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
    save_permissions(data)


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
    """Upsert defaults for a specific command under a sub-plugin in the framework.

    Note: `plugin` here refers to the sub-plugin name inside the framework.
    """
    data = load_permissions()
    fw = data.setdefault(FRAMEWORK_NAME, {})
    sub_map = fw.setdefault("sub_plugins", {})
    sp = sub_map.setdefault(plugin, {})
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
    save_permissions(data)


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
