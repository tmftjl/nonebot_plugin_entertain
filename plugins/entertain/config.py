from __future__ import annotations

from typing import Dict, Any

from ...core.api import (
    register_plugin_config,
    register_plugin_schema,
)


# ----- One unified config (single file) -----
# All commands in entertain share one CFG with nested sections
DEFAULTS: Dict[str, Any] = {
    "box": {
        "only_admin": False,
        "box_blacklist": [],  # list[str]
        "increase_box": False,
        "decrease_box": False,
        "auto_box_groups": [],  # list[str] group ids for auto-box
    },
    "reg_time": {"qq_reg_time_api_key": None},
}

# Single CFG for the whole entertain plugin
CFG = register_plugin_config("entertain", DEFAULTS)

# Load once into memory; subsequent reads use this cache
_CACHED: Dict[str, Any] = CFG.load()


def cfg_cached() -> Dict[str, Any]:
    return _CACHED


def cfg_box() -> Dict[str, Any]:
    d = _CACHED.get("box")
    return d if isinstance(d, dict) else {}


def cfg_reg_time() -> Dict[str, Any]:
    d = _CACHED.get("reg_time")
    return d if isinstance(d, dict) else {}

REG_TIME_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "title": "注册时间查询",
    "description": "设置第三方接口 key；留空则使用内置 key（不保证长期可用）",
    "properties": {
        "qq_reg_time_api_key": {
            "type": ["string", "null"],
            "title": "API Key",
            "description": "第三方注册时间查询 API 的 key",
            "default": None,
            "x-order": 1,
        }
    },
}


# Consolidated plugin-level schema for entertain
ENTERTAIN_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "娱乐",
    "properties": {
        "box": {
            "type": "object",
            "title": "盒子回复",
            "description": "开启后在加群/退群等事件中自动生成图片或文本回复",
            "properties": {
                "only_admin": {
                    "type": "boolean",
                    "title": "仅管理员可用",
                    "description": "限制只有管理员才能触发盒子相关功能",
                    "default": False,
                    "x-order": 1,
                },
                "box_blacklist": {
                    "type": "array",
                    "title": "黑名单",
                    "description": "不触发盒子回复的QQ号列表",
                    "items": {"type": "string"},
                    "default": [],
                    "x-order": 2,
                },
                "increase_box": {
                    "type": "boolean",
                    "title": "入群欢迎",
                    "description": "新成员进群时发送欢迎盒",
                    "default": False,
                    "x-order": 3,
                },
                "decrease_box": {
                    "type": "boolean",
                    "title": "退群提示",
                    "description": "成员退群时发送提示盒",
                    "default": False,
                    "x-order": 4,
                },
                "auto_box_groups": {
                    "type": "array",
                    "title": "自动盒子群",
                    "description": "启用自动盒子的群号列表（字符串）",
                    "items": {"type": "string"},
                    "default": [],
                    "x-order": 5,
                },
            },
        },
        "reg_time": {
            "type": "object",
            "title": "注册时间查询",
            "description": "设置第三方接口 key；留空则使用内置 key（不保证长期可用）",
            "properties": {
                "qq_reg_time_api_key": {
                    "type": ["string", "null"],
                    "title": "API Key",
                    "description": "第三方注册时间查询 API 的 key",
                    "default": None,
                    "x-order": 1,
                }
            },
        },
    },
}

register_plugin_schema("entertain", ENTERTAIN_SCHEMA)
