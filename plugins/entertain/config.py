from __future__ import annotations

from typing import Dict, Any

from ...core.api import (
    register_plugin_config,
    register_plugin_schema,
    register_reload_callback,
)


# ----- One unified config (single file) -----
# All commands in entertain share one CFG with nested sections
DEFAULTS: Dict[str, Any] = {
    "box": {
        "only_admin": False,
        "box_blacklist": [],  # list[str]
        "increase_box": False,
        "auto_box_groups": [],  # list[str] group ids for auto-box
        "avatar_api_url": "https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640",
        "avatar_fetch_timeout": 10,
    },
    "reg_time": {
        "qq_reg_time_api_url": "https://api.s01s.cn/API/zcsj/",
        "qq_reg_time_api_key": "",  # 空字符串,需要用户自行配置
        "qq_reg_time_timeout": 15,
    },
    "api_urls": {
        "sick_quote_api": "https://oiapi.net/API/SickL/",
        "doro_api": "https://doro-api.hxxn.cc/get",
        "background_api": "http://127.0.0.1:1520/api/wuthering_waves/role_image/random",
    },
    "api_timeouts": {
        "sick_quote_timeout": 15,
        "doro_api_timeout": 15,
        "image_download_timeout": 20,
        "background_image_timeout": 10,
    },
}

# Single CFG for the whole entertain plugin
CFG = register_plugin_config("entertain", DEFAULTS)

# Load once into memory; subsequent reads use this cache
_CACHED: Dict[str, Any] = CFG.load()


def reload_cache() -> None:
    """重新加载配置到模块级缓存，供框架重载配置时调用。"""
    global _CACHED
    _CACHED = CFG.load()


# 注册重载回调，确保框架重载配置时更新模块缓存
register_reload_callback("entertain", reload_cache)


def cfg_cached() -> Dict[str, Any]:
    """返回整个配置的缓存副本。"""
    return _CACHED


def cfg_box() -> Dict[str, Any]:
    """返回 box 配置节，从模块级缓存读取。"""
    d = _CACHED.get("box")
    return d if isinstance(d, dict) else {}


def cfg_reg_time() -> Dict[str, Any]:
    """返回 reg_time 配置节，从模块级缓存读取。"""
    d = _CACHED.get("reg_time")
    return d if isinstance(d, dict) else {}


def cfg_api_urls() -> Dict[str, Any]:
    """返回 api_urls 配置节，从模块级缓存读取。"""
    d = _CACHED.get("api_urls")
    return d if isinstance(d, dict) else {}


def cfg_api_timeouts() -> Dict[str, Any]:
    """返回 api_timeouts 配置节，从模块级缓存读取。"""
    d = _CACHED.get("api_timeouts")
    return d if isinstance(d, dict) else {}


# Consolidated plugin-level schema for entertain
ENTERTAIN_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "娱乐",
    "properties": {
        "box": {
            "type": "object",
            "title": "开盒",
            "description": "开盒",
            "x-order": 1,
            "x-collapse": True,  # 前端可以折叠显示
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
                    "title": "入群自动开盒",
                    "description": "新成员进群时自动开盒",
                    "default": False,
                    "x-order": 3,
                },
                "auto_box_groups": {
                    "type": "array",
                    "title": "自动盒子群",
                    "description": "启用自动盒子的群号列表（字符串）",
                    "items": {"type": "string"},
                    "default": [],
                    "x-order": 5,
                },
                "avatar_api_url": {
                    "type": "string",
                    "title": "头像API URL",
                    "description": "QQ头像获取API模板,{user_id}会被替换为用户QQ号",
                    "default": "https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640",
                    "x-order": 6,
                },
                "avatar_fetch_timeout": {
                    "type": "integer",
                    "title": "头像获取超时(秒)",
                    "description": "获取头像图片的超时时间",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 60,
                    "x-order": 7,
                },
            },
        },
        "reg_time": {
            "type": "object",
            "title": "注册时间查询",
            "description": "设置第三方接口 URL 和 key",
            "x-order": 2,
            "x-collapse": True,  # 前端可以折叠显示
            "properties": {
                "qq_reg_time_api_url": {
                    "type": "string",
                    "title": "API URL",
                    "description": "第三方注册时间查询 API 的地址",
                    "default": "https://api.s01s.cn/API/zcsj/",
                    "x-order": 1,
                },
                "qq_reg_time_api_key": {
                    "type": "string",
                    "title": "API Key",
                    "description": "第三方注册时间查询 API 的 key（必填）",
                    "default": "",
                    "x-order": 2,
                },
                "qq_reg_time_timeout": {
                    "type": "integer",
                    "title": "请求超时(秒)",
                    "description": "API 请求的超时时间",
                    "default": 15,
                    "minimum": 1,
                    "maximum": 60,
                    "x-order": 3,
                }
            },
        },
        "api_urls": {
            "type": "object",
            "title": "第三方API地址",
            "description": "各种功能使用的第三方API URL配置",
            "x-order": 3,
            "x-collapse": True,
            "properties": {
                "sick_quote_api": {
                    "type": "string",
                    "title": "发病语录API",
                    "description": "发病语录接口地址",
                    "default": "https://oiapi.net/API/SickL/",
                    "x-order": 1,
                },
                "doro_api": {
                    "type": "string",
                    "title": "doro结局API",
                    "description": "doro结局接口地址",
                    "default": "https://doro-api.hxxn.cc/get",
                    "x-order": 2,
                },
                "background_api": {
                    "type": "string",
                    "title": "背景图API",
                    "description": "随机背景图接口地址(本地或远程)",
                    "default": "http://127.0.0.1:1520/api/wuthering_waves/role_image/random",
                    "x-order": 3,
                },
            },
        },
        "api_timeouts": {
            "type": "object",
            "title": "API超时设置",
            "description": "各种API请求的超时时间配置(秒)",
            "x-order": 4,
            "x-collapse": True,
            "properties": {
                "sick_quote_timeout": {
                    "type": "integer",
                    "title": "发病语录超时",
                    "description": "发病语录API请求超时(秒)",
                    "default": 15,
                    "minimum": 1,
                    "maximum": 60,
                    "x-order": 1,
                },
                "doro_api_timeout": {
                    "type": "integer",
                    "title": "doro结局超时",
                    "description": "doro结局请求超时(秒)",
                    "default": 15,
                    "minimum": 1,
                    "maximum": 60,
                    "x-order": 2,
                },
                "image_download_timeout": {
                    "type": "integer",
                    "title": "图片下载超时",
                    "description": "通用图片下载超时(秒)",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 120,
                    "x-order": 3,
                },
                "background_image_timeout": {
                    "type": "integer",
                    "title": "背景图超时",
                    "description": "背景图API请求超时(秒)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 60,
                    "x-order": 4,
                },
            },
        },
    },
}

register_plugin_schema("entertain", ENTERTAIN_SCHEMA)
