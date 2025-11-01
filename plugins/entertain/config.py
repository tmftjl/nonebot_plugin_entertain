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
    "music": {
        "api_base": "https://api.vkeys.cn",
        "provider_default": "tencent",  # tencent | netease
        "search_num": 20,
        # QQ 音乐质量区间 [0,16]; 网易云区间[1,9]，超出将自动调整
        "quality": 4,
    },
    "box": {
        "only_admin": False,
        "box_blacklist": [],  # list[str]
        "increase_box": False,
        "auto_box_groups": [],  # list[str] group ids for auto-box
        "avatar_api_url": "https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640",
    },
    "reg_time": {
        "qq_reg_time_api_url": "https://api.s01s.cn/API/zcsj/",
        "qq_reg_time_api_key": "",  # 空字符串,需要用户自行配置
    },
    "api_urls": {
        "sick_quote_api": "https://oiapi.net/API/SickL/",
        "doro_api": "https://doro-api.hxxn.cc/get",
        "background_api": "http://127.0.0.1:1520/api/wuthering_waves/role_image/random",
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


def cfg_music() -> Dict[str, Any]:
    """返回 music 配置节，从模块级缓存读取。"""
    d = _CACHED.get("music")
    return d if isinstance(d, dict) else {}


# Consolidated plugin-level schema for entertain
ENTERTAIN_SCHEMA: Dict[str, Any] = {
    "": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "娱乐",
    "properties": {
        "box": {
            "type": "object",
            "title": "开箱",
            "description": "开箱相关设置",
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
                    "title": "入群自动开箱",
                    "description": "新成员进群时自动开箱",
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
                    "description": "QQ头像获取API模板,{user_id}会被替换为用户QQ",
                    "default": "https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640",
                    "x-order": 6,
                },
            },
        },
        "music": {
            "type": "object",
            "title": "点歌",
            "description": "落月API 点歌相关设置",
            "x-order": 2,
            "x-collapse": True,
            "properties": {
                "api_base": {
                    "type": "string",
                    "title": "API 基址",
                    "description": "落月API基础地址，默认为 https://api.vkeys.cn",
                    "default": "https://api.vkeys.cn",
                    "x-order": 1,
                },
                "provider_default": {
                    "type": "string",
                    "title": "默认平台",
                    "description": "未指定平台时使用的音乐平台",
                    "enum": ["tencent", "netease"],
                    "default": "tencent",
                    "x-order": 2,
                },
                "search_num": {
                    "type": "integer",
                    "title": "搜索返回数量",
                    "description": "每次搜索返回的歌曲条数(1-60)",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 60,
                    "x-order": 3,
                },
                "quality": {
                    "type": "integer",
                    "title": "音质",
                    "description": "QQ音乐区间[0,16]；网易云区间[1,9]，超出将自动调整",
                    "default": 4,
                    "minimum": 0,
                    "maximum": 16,
                    "x-order": 4,
                },
            },
        },
        "reg_time": {
            "type": "object",
            "title": "注册时间查询",
            "description": "设置第三方接口 URL 与 key",
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
    },
}

register_plugin_schema("entertain", ENTERTAIN_SCHEMA)
