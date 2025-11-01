from __future__ import annotations

from typing import Any, Dict

from ...core.api import register_plugin_config, register_plugin_schema, register_reload_callback


# One unified config for the whole `useful` plugin
DEFAULTS: Dict[str, Any] = {
    "taffy": {
        "api_url": "http://127.0.0.1:8899/stats/api",
        "username": "",
        "password": "",\r\n    },
}


CFG = register_plugin_config("useful", DEFAULTS)

# Load once and keep in-memory for reads
_CACHED: Dict[str, Any] = CFG.load()


def reload_cache() -> None:
    """閲嶆柊鍔犺浇閰嶇疆鍒版ā鍧楃骇缂撳瓨锛屼緵妗嗘灦閲嶈浇閰嶇疆鏃惰皟鐢ㄣ€?""
    global _CACHED
    _CACHED = CFG.load()


# 娉ㄥ唽閲嶈浇鍥炶皟锛岀‘淇濇鏋堕噸杞介厤缃椂鏇存柊妯″潡缂撳瓨
register_reload_callback("useful", reload_cache)


def cfg_cached() -> Dict[str, Any]:
    """杩斿洖鏁翠釜閰嶇疆鐨勭紦瀛樺壇鏈€?""
    return _CACHED


def cfg_taffy() -> Dict[str, Any]:
    """杩斿洖 taffy 閰嶇疆鑺傦紝浠庢ā鍧楃骇缂撳瓨璇诲彇銆?""
    d = _CACHED.get("taffy")
    return d if isinstance(d, dict) else {}


# ----- Unified schema (single object with nested properties) -----
TAFFY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "title": "Taffy 缁熻",
    "properties": {
        "api_url": {
            "type": "string",
            "title": "API 鍦板潃",
            "description": "Taffy 缁熻鏈嶅姟鐨勫熀纭€鎺ュ彛鍦板潃",
            "default": "http://127.0.0.1:8899/stats/api",
            "x-order": 1,
        },
        "username": {
            "type": "string",
            "title": "鐢ㄦ埛鍚?,
            "description": "濡傛湇鍔″紑鍚簡 BasicAuth锛岃濉啓鐢ㄦ埛鍚?,
            "default": "",
            "x-order": 2,
        },
        "password": {
            "type": "string",
            "title": "瀵嗙爜",
            "description": "濡傛湇鍔″紑鍚簡 BasicAuth锛岃濉啓瀵嗙爜锛堝墠绔笉鍥炴樉鏃у€硷級",
            "default": "",
            "x-secret": True,
            "x-widget": "password",
            "x-order": 3,
        }\r\n
USEFUL_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "鏈夌敤鐨?,
    "properties": {
        "taffy": TAFFY_SCHEMA,
    },
}

try:
    register_plugin_schema("useful", USEFUL_SCHEMA)
except Exception:
    pass

