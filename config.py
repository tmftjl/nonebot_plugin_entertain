from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Tuple

from .utils import config_dir


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
        """Load config without merging defaults, using in-memory cache."""
        self.ensure()
        self.ensure_loaded()
        return json.loads(json.dumps(self._cache or {}))

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

    


# ----- New unified permissions (single global file) -----


def _perm_entry_default(level: str = "all", scene: str = "all") -> Dict[str, Any]:
    return {
        "enabled": True,
        "level": level,
        "scene": scene,
        "whitelist": {"users": [], "groups": []},
        "blacklist": {"users": [], "groups": []},
    }


def _permissions_default() -> Dict[str, Any]:
    # Target schema (strict):
    # { "<plugin>": { "top": Entry, "commands": { name: Entry } }, ... }
    # No global-level fields.
    return {}


def permissions_path() -> Path:
    return config_dir() / "permissions.json"


def ensure_permissions_file() -> None:
    p = permissions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        try:
            p.write_text(json.dumps(_permissions_default(), ensure_ascii=False, indent=2), encoding="utf-8")
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
    return _permissions_default()


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
    data = load_permissions()
    p = data.setdefault(plugin, {})
    d = p.setdefault("top", _perm_entry_default())
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
    data = load_permissions()
    p = data.setdefault(plugin, {})
    cmds = p.setdefault("commands", {})
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


def aggregate_permissions() -> None:
    """Ensure permissions.json exists and migrate to strict per-plugin schema.

    Target schema:
    { "<plugin>": { "top": Entry, "commands": { name: Entry } }, ... }
    No global-level keys. Remove any legacy keys and the pseudo-plugin
    "nonebot_plugin_entertain" if present.
    """
    p = permissions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        ensure_permissions_file()
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        save_permissions(_permissions_default())
        return

    # Build new dict, dropping any global-level keys
    if not isinstance(data, dict):
        save_permissions(_permissions_default())
        return

    new_data: Dict[str, Any] = {}

    # Legacy with 'global'/'plugins'
    if "plugins" in data or "global" in data:
        try:
            pmap = data.get("plugins") or {}
            if isinstance(pmap, dict):
                for pn, node in pmap.items():
                    if not isinstance(node, dict):
                        continue
                    if pn == "nonebot_plugin_entertain":
                        continue
                    dst = new_data.setdefault(pn, {})
                    if isinstance(node.get("default"), dict):
                        dst["top"] = node.get("default")
                    cmds = node.get("commands") or {}
                    if isinstance(cmds, dict):
                        dst_cmds = dst.setdefault("commands", {})
                        for cn, centry in cmds.items():
                            if isinstance(centry, dict):
                                dst_cmds.setdefault(cn, centry)
        except Exception:
            new_data = {}
    else:
        # Current mixed schema: contains global keys and plugin maps at root
        for k, v in data.items():
            if k in {"enabled", "whitelist", "blacklist", "scene", "level"}:
                continue
            if k == "nonebot_plugin_entertain":
                continue
            if isinstance(v, dict):
                node = new_data.setdefault(k, {})
                top = v.get("top") if isinstance(v.get("top"), dict) else None
                cmds = v.get("commands") if isinstance(v.get("commands"), dict) else None
                if top:
                    node["top"] = top
                if cmds:
                    node["commands"] = cmds

    # Ensure every plugin node has required keys
    for pn, node in list(new_data.items()):
        if not isinstance(node, dict):
            new_data[pn] = {"top": _perm_entry_default(), "commands": {}}
            continue
        node.setdefault("top", _perm_entry_default())
        node.setdefault("commands", {})

    # Populate from current plugins' source to auto-generate entries
    try:
        base = Path(__file__).parent / "plugins"
        if base.exists():
            for pdir in base.iterdir():
                try:
                    if not pdir.is_dir():
                        continue
                    if not (pdir / "__init__.py").exists():
                        continue
                    plugin_name = pdir.name
                    node = new_data.setdefault(plugin_name, {"top": _perm_entry_default(), "commands": {}})
                    node.setdefault("top", _perm_entry_default())
                    cmds = node.setdefault("commands", {})

                    # scan files for P.on_regex(..., name="...") and permission_cmd("...")
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

                        # alias collection for upsert_command_defaults
                        up_names = {"upsert_command_defaults"}
                        for node in _ast.walk(tree):
                            if isinstance(node, _ast.ImportFrom):
                                try:
                                    for alias in node.names:
                                        if alias.name == "upsert_command_defaults" and alias.asname:
                                            up_names.add(alias.asname)
                                except Exception:
                                    pass

                        for node in _ast.walk(tree):
                            try:
                                if isinstance(node, _ast.Call):
                                    fn = node.func
                                    # P.on_regex(..., name="...")
                                    if isinstance(fn, _ast.Attribute) and isinstance(fn.value, _ast.Name) and fn.value.id == "P" and fn.attr == "on_regex":
                                        for kw in node.keywords or []:
                                            if kw.arg == "name" and isinstance(kw.value, _ast.Constant) and isinstance(kw.value.value, str):
                                                cmds.setdefault(str(kw.value.value), _perm_entry_default())
                                    # P.permission_cmd("...")
                                    if isinstance(fn, _ast.Attribute) and isinstance(fn.value, _ast.Name) and fn.value.id == "P" and fn.attr == "permission_cmd":
                                        if node.args and isinstance(node.args[0], _ast.Constant) and isinstance(node.args[0].value, str):
                                            cmds.setdefault(str(node.args[0].value), _perm_entry_default())
                                    # upsert_command_defaults or alias
                                    if isinstance(fn, _ast.Name) and fn.id in up_names:
                                        if len(node.args) >= 2 and all(isinstance(a, _ast.Constant) and isinstance(a.value, str) for a in node.args[:2]):
                                            pn = str(node.args[0].value)
                                            cn = str(node.args[1].value)
                                            if pn == plugin_name and cn:
                                                cmds.setdefault(cn, _perm_entry_default())
                            except Exception:
                                continue
                except Exception:
                    continue
    except Exception:
        pass

    save_permissions(new_data)


def _migrate_legacy_plugin_configs() -> None:
    """Migrate legacy flat config files to new per-plugin layout.

    - box: config/config.json -> config/box/config.json
    - taffy: config/taffy.json -> config/taffy/config.json
    """
    # box (very old flat file)
    try:
        legacy_box = config_dir() / "config.json"
        if legacy_box.exists():
            try:
                data = json.loads(legacy_box.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    dst = config_dir("box") / "config.json"
                    if not dst.exists():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            try:
                legacy_box.unlink()
            except Exception:
                pass
    except Exception:
        pass

    # taffy (very old flat file)
    try:
        legacy_taffy = config_dir() / "taffy.json"
        if legacy_taffy.exists():
            try:
                data = json.loads(legacy_taffy.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    dst = config_dir("taffy") / "config.json"
                    if not dst.exists():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            try:
                legacy_taffy.unlink()
            except Exception:
                pass
    except Exception:
        pass


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
    # Migrate any legacy config layout
    _migrate_legacy_plugin_configs()
    # Normalize permissions data shape if coming from older schema
    aggregate_permissions()

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
