from __future__ import annotations

from typing import Any, Dict

from ...core.api import register_plugin_config, register_plugin_schema


# One unified config for the whole `useful` plugin
DEFAULTS: Dict[str, Any] = {
    "taffy": {
        "api_url": "http://127.0.0.1:8899/stats/api",
        "username": "",
        "password": "",
        "timeout": 20,
    },
}


CFG = register_plugin_config("useful", DEFAULTS)

# Load once and keep in-memory for reads
_CACHED: Dict[str, Any] = CFG.load()


def cfg_cached() -> Dict[str, Any]:
    return _CACHED


def cfg_taffy() -> Dict[str, Any]:
    d = _CACHED.get("taffy")
    return d if isinstance(d, dict) else {}


# ----- Unified schema (single object with nested properties) -----
TAFFY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "title": "Taffy 统计",
    "properties": {
        "api_url": {
            "type": "string",
            "title": "API 地址",
            "description": "Taffy 统计服务的基础接口地址",
            "default": "http://127.0.0.1:8899/stats/api",
            "x-order": 1,
        },
        "username": {
            "type": "string",
            "title": "用户名",
            "description": "如服务开启了 BasicAuth，请填写用户名",
            "default": "",
            "x-order": 2,
        },
        "password": {
            "type": "string",
            "title": "密码",
            "description": "如服务开启了 BasicAuth，请填写密码（前端不回显旧值）",
            "default": "",
            "x-secret": True,
            "x-widget": "password",
            "x-order": 3,
        },
        "timeout": {
            "type": "integer",
            "title": "请求超时(秒)",
            "description": "HTTP 请求超时时间",
            "default": 20,
            "minimum": 1,
            "x-order": 4,
        },
    },
}

USEFUL_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "有用的",
    "properties": {
        "taffy": TAFFY_SCHEMA,
    },
}

try:
    register_plugin_schema("useful", USEFUL_SCHEMA)
except Exception:
    pass
