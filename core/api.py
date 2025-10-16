from __future__ import annotations

# Public API surface for plugin authors

from .framework.registry import Plugin as Plugin
from .framework.perm import (
    permission_for,
    permission_for_cmd,
    permission_for_plugin,
    reload_permissions,
)
from .framework.config import (
    register_plugin_config,
    register_namespaced_config,
    register_plugin_schema,
    register_namespaced_schema,
    get_plugin_config,
    save_plugin_config,
    reload_plugin_config,
    bootstrap_configs,
    reload_all_configs,
    load_permissions,
    save_permissions,
    optimize_permissions,
    permissions_path,
    ensure_permissions_file,
    upsert_plugin_defaults,
    upsert_command_defaults,
    upsert_system_command_defaults,
)
from .framework.utils import (
    data_dir,
    resource_dir,
    config_dir,
    plugin_data_dir,
    plugin_resource_dir,
)
from .framework.cache import KeyValueCache as KeyValueCache

__all__ = [
    # class
    "Plugin",
    "KeyValueCache",
    # permission helpers
    "permission_for",
    "permission_for_cmd",
    "permission_for_plugin",
    "reload_permissions",
    # config helpers
    "register_plugin_config",
    "register_namespaced_config",
    "register_plugin_schema",
    "register_namespaced_schema",
    "get_plugin_config",
    "save_plugin_config",
    "reload_plugin_config",
    "bootstrap_configs",
    "reload_all_configs",
    "load_permissions",
    "save_permissions",
    "optimize_permissions",
    "permissions_path",
    "ensure_permissions_file",
    "upsert_plugin_defaults",
    "upsert_command_defaults",
    "upsert_system_command_defaults",
    # dirs
    "data_dir",
    "resource_dir",
    "config_dir",
    "plugin_data_dir",
    "plugin_resource_dir",
]
