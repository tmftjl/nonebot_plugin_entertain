from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

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

    @property
    def path(self) -> Path:
        return config_dir(self.plugin) / self.filename

    def ensure(self) -> None:
        p = self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            try:
                p.write_text(json.dumps(self.defaults, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

    def load(self) -> Dict[str, Any]:
        self.ensure()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return _deep_merge(self.defaults, data)
        except Exception:
            pass
        return json.loads(json.dumps(self.defaults))

    def save(self, cfg: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    


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
    # New target schema:
    # { enabled, whitelist, blacklist, <plugin>: { top: Entry, commands: { name: Entry } }, ... }
    return {
        "enabled": True,
        "whitelist": {"users": [], "groups": []},
        "blacklist": {"users": [], "groups": []},
    }


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


def register_plugin_config(
    plugin: str,
    defaults: Optional[Dict[str, Any]] = None,
    *,
    filename: str = "config.json",
) -> ConfigProxy:
    """Register per-plugin config file (no per-plugin permissions)."""
    cfg_proxy = ConfigProxy(plugin=plugin, filename=filename, defaults=defaults or {})
    cfg_proxy.ensure()
    return cfg_proxy


def get_plugin_config(plugin: str, *, filename: str = "config.json", defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return register_plugin_config(plugin, defaults or {}, filename=filename).load()


def save_plugin_config(plugin: str, cfg: Dict[str, Any], *, filename: str = "config.json") -> None:
    register_plugin_config(plugin, {}, filename=filename).save(cfg)


def aggregate_permissions() -> None:
    """Ensure permissions.json exists and migrate from any legacy schema.

    Target schema (current):
    {
      "enabled": bool,
      "whitelist": {users, groups},
      "blacklist": {users, groups},
      "<plugin>": { "top": Entry, "commands": { name: Entry } },
      ...
    }
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

    # If already in target shape (has enabled/whitelist/blacklist, no 'global' key), keep
    if isinstance(data, dict) and "global" not in data and "enabled" in data:
        save_permissions(data)
        return

    # Try migrate from schema with 'global'/'plugins'
    try:
        new_data = _permissions_default()
        if isinstance(data, dict):
            # migrate global
            g = data.get("global") or {}
            if isinstance(g.get("enabled"), bool):
                new_data["enabled"] = g.get("enabled")
            if isinstance(g.get("whitelist"), dict):
                new_data["whitelist"] = g.get("whitelist")
            if isinstance(g.get("blacklist"), dict):
                new_data["blacklist"] = g.get("blacklist")
            # migrate nested plugins
            pmap = data.get("plugins") or {}
            if isinstance(pmap, dict):
                for pn, node in pmap.items():
                    if not isinstance(node, dict):
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
        save_permissions(new_data)
    except Exception:
        save_permissions(_permissions_default())


def bootstrap_configs() -> None:
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        # Lazy import to avoid cycles
        from .perm import ensure_permissions_bootstrap  # type: ignore

        ensure_permissions_bootstrap()
    except Exception:
        pass
    aggregate_permissions()
