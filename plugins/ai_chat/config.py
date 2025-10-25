"""AI 对话配置管理

本模块负责：
- 通过框架统一配置管理注册 `config/ai_chat/config.json`
- 提供 Pydantic 配置对象用于代码内便捷访问
- 负责 `config/ai_chat/personas.json` 的人格配置读写

注意：所有文件均使用 UTF-8 保存，避免中文乱码。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, List

from nonebot.log import logger
from pydantic import BaseModel, Field

from ...core.api import (
    register_plugin_config,
    register_plugin_schema,
    register_reload_callback,
)
from ...core.framework.utils import config_dir


# ==================== Pydantic 配置对象 ====================


class APIConfig(BaseModel):
    """AI 服务商配置（以 name 作为唯一标识，可切换）"""

    name: str = Field(description="唯一名称，用于切换标识")
    base_url: str = Field(default="https://api.openai.com/v1", description="API 基础 URL")
    api_key: str = Field(default="", description="API 密钥")
    model: str = Field(default="gpt-4o-mini", description="默认模型")
    timeout: int = Field(default=60, description="超时时间（秒）")


class CacheConfig(BaseModel):
    """缓存配置"""

    session_ttl: int = Field(default=300, description="会话缓存 TTL（秒）")
    history_ttl: int = Field(default=60, description="历史缓存 TTL（秒）")
    favorability_ttl: int = Field(default=120, description="好感度缓存 TTL（秒）")


class SessionConfig(BaseModel):
    """会话配置"""

    default_max_history: int = Field(default=20, description="默认最大历史记录条数")
    default_temperature: float = Field(default=0.7, description="默认温度")
    auto_create: bool = Field(default=True, description="自动创建会话")
    # 统一“轮数”限制（user+assistant 为一轮）：
    # - 发给模型的上下文按该轮数裁剪
    # - 持久化历史也按该轮数×2 条消息进行裁剪
    max_rounds: int = Field(default=8, description="最大上下文轮数（影响持久化与发送给模型的历史，一轮=用户+助手）")
    # 群聊“聊天室历史”（内存）最大行数
    chatroom_history_max_lines: int = Field(default=200, description="群聊聊天室历史（内存）最大行数")


class FavorabilityConfig(BaseModel):
    """好感度配置"""

    enabled: bool = Field(default=True, description="是否启用好感度")
    per_message_delta: int = Field(default=1, description="每条消息增加好感度")
    positive_delta: int = Field(default=5, description="正面情感增加好感度")
    negative_delta: int = Field(default=-3, description="负面情感减少好感度")


class ToolsConfig(BaseModel):
    """工具配置"""

    enabled: bool = Field(default=False, description="是否启用工具")
    max_iterations: int = Field(default=3, description="最大工具调用迭代次数")
    builtin_tools: list[str] = Field(
        default_factory=lambda: ["get_time", "get_weather"], description="内置工具"
    )


class MCPConfig(BaseModel):
    """MCP 配置（预留）"""

    enabled: bool = Field(default=False, description="是否启用 MCP")
    servers: list[Dict[str, Any]] = Field(default_factory=list, description="MCP 服务器列表")


class ResponseConfig(BaseModel):
    """回复配置"""

    max_length: int = Field(default=500, description="最大回复长度（tokens 或字符约束）")
    enable_at_reply: bool = Field(default=True, description="群聊中是否 @ 用户回复")


class AIChatConfig(BaseModel):
    """AI 对话总配置"""

    # api 改为数组，支持多服务商；增加 api_active 通过名称切换
    api: List[APIConfig] = Field(default_factory=list, description="AI 服务商配置列表")
    api_active: str = Field(default="default", description="当前启用的服务商名称")

    cache: CacheConfig = Field(default_factory=CacheConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    favorability: FavorabilityConfig = Field(default_factory=FavorabilityConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    response: ResponseConfig = Field(default_factory=ResponseConfig)


class PersonaConfig(BaseModel):
    """人格配置（仅保留人格信息）"""

    name: str = Field(description="人格名称")
    description: str = Field(description="人格描述")
    system_prompt: str = Field(description="系统提示语")


# ==================== 统一配置注册 ====================


DEFAULTS: Dict[str, Any] = {
    "api": [
        {
            "name": "default",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4o-mini",
            "timeout": 60,
        }
    ],
    "api_active": "default",
    "cache": {
        "session_ttl": 300,
        "history_ttl": 60,
        "favorability_ttl": 120,
    },
    "session": {
        "default_max_history": 20,
        "default_temperature": 0.7,
        "auto_create": True,
        "max_rounds": 8,
        "chatroom_history_max_lines": 200,
        "chatroom_enhance": {
            "active_reply": {
                "enable": False,
                "prompt_suffix": "Now, a new message is coming: `{message}`. Please react to it. Only output your response and do not output any other information.",
                "probability": 0.1
            }
        },
    },
    "favorability": {
        "enabled": True,
        "per_message_delta": 1,
        "positive_delta": 5,
        "negative_delta": -3,
    },
    "tools": {
        "enabled": False,
        "max_iterations": 3,
        "builtin_tools": ["get_time", "get_weather"],
    },
    "mcp": {
        "enabled": False,
        "servers": [],
    },
    "response": {
        "max_length": 500,
        "enable_at_reply": True,
    },
}

# 注册配置文件（config/ai_chat/config.json）
CFG = register_plugin_config("ai_chat", DEFAULTS)


# 可选：注册前端 JSON Schema（用于可视化编辑）
AI_CHAT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "AI 对话",
    "properties": {
        "api": {
            "type": "array",
            "title": "AI 服务商配置列表",
            "x-order": 1,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "title": "名称", "x-order": 1},
                    "base_url": {
                        "type": "string",
                        "title": "API 基址",
                        "default": DEFAULTS["api"][0]["base_url"],
                        "x-order": 2,
                    },
                    "api_key": {
                        "type": "string",
                        "title": "API 密钥",
                        "default": DEFAULTS["api"][0]["api_key"],
                        "x-order": 3,
                    },
                    "model": {
                        "type": "string",
                        "title": "默认模型",
                        "default": DEFAULTS["api"][0]["model"],
                        "x-order": 4,
                    },
                    "timeout": {
                        "type": "integer",
                        "title": "超时（秒）",
                        "minimum": 1,
                        "maximum": 300,
                        "default": DEFAULTS["api"][0]["timeout"],
                        "x-order": 5,
                    },
                },
                "required": ["name"],
            },
        },
        "api_active": {
            "type": "string",
            "title": "当前启用服务商名",
            "default": DEFAULTS["api_active"],
            "x-order": 2,
        },
        "cache": {
            "type": "object",
            "title": "缓存",
            "x-order": 3,
            "x-collapse": True,
            "properties": {
                "session_ttl": {
                    "type": "integer",
                    "title": "会话缓存 TTL（秒）",
                    "minimum": 0,
                    "maximum": 86400,
                    "default": DEFAULTS["cache"]["session_ttl"],
                    "x-order": 1,
                },
                "history_ttl": {
                    "type": "integer",
                    "title": "历史缓存 TTL（秒）",
                    "minimum": 0,
                    "maximum": 86400,
                    "default": DEFAULTS["cache"]["history_ttl"],
                    "x-order": 2,
                },
                "favorability_ttl": {
                    "type": "integer",
                    "title": "好感度缓存 TTL（秒）",
                    "minimum": 0,
                    "maximum": 86400,
                    "default": DEFAULTS["cache"]["favorability_ttl"],
                    "x-order": 3,
                },
            },
        },
        "session": {
            "type": "object",
            "title": "会话",
            "x-order": 4,
            "x-collapse": True,
            "properties": {
                "default_max_history": {
                    "type": "integer",
                    "title": "默认最大历史条数",
                    "minimum": 1,
                    "maximum": 200,
                    "default": DEFAULTS["session"]["default_max_history"],
                    "x-order": 1,
                },
                "default_temperature": {
                    "type": "number",
                    "title": "默认温度",
                    "minimum": 0,
                    "maximum": 2,
                    "default": DEFAULTS["session"]["default_temperature"],
                    "x-order": 2,
                },
                "auto_create": {
                    "type": "boolean",
                    "title": "自动创建会话",
                    "default": DEFAULTS["session"]["auto_create"],
                    "x-order": 3,
                },
                "max_rounds": {
                    "type": "integer",
                    "title": "最大上下文轮数",
                    "minimum": 1,
                    "maximum": 50,
                    "default": DEFAULTS["session"]["max_rounds"],
                    "x-order": 4,
                },
                "chatroom_history_max_lines": {
                    "type": "integer",
                    "title": "聊天室历史最大行数",
                    "minimum": 1,
                    "maximum": 5000,
                    "default": DEFAULTS["session"]["chatroom_history_max_lines"],
                    "x-order": 5,
                },
            },
        },
        "favorability": {
            "type": "object",
            "title": "好感度",
            "x-order": 5,
            "x-collapse": True,
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": "启用好感度",
                    "default": DEFAULTS["favorability"]["enabled"],
                    "x-order": 1,
                },
                "per_message_delta": {
                    "type": "integer",
                    "title": "每条消息增量",
                    "default": DEFAULTS["favorability"]["per_message_delta"],
                    "x-order": 2,
                },
                "positive_delta": {
                    "type": "integer",
                    "title": "正面情感增量",
                    "default": DEFAULTS["favorability"]["positive_delta"],
                    "x-order": 3,
                },
                "negative_delta": {
                    "type": "integer",
                    "title": "负面情感增量",
                    "default": DEFAULTS["favorability"]["negative_delta"],
                    "x-order": 4,
                },
            },
        },
        "tools": {
            "type": "object",
            "title": "工具",
            "x-order": 6,
            "x-collapse": True,
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": "启用工具",
                    "default": DEFAULTS["tools"]["enabled"],
                    "x-order": 1,
                },
                "max_iterations": {
                    "type": "integer",
                    "title": "最大工具迭代次数",
                    "minimum": 1,
                    "maximum": 10,
                    "default": DEFAULTS["tools"]["max_iterations"],
                    "x-order": 2,
                },
                "builtin_tools": {
                    "type": "array",
                    "title": "内置工具",
                    "items": {"type": "string"},
                    "default": DEFAULTS["tools"]["builtin_tools"],
                    "x-order": 3,
                },
            },
        },
        "response": {
            "type": "object",
            "title": "回复",
            "x-order": 7,
            "x-collapse": True,
            "properties": {
                "max_length": {
                    "type": "integer",
                    "title": "最大回复长度",
                    "minimum": 1,
                    "maximum": 4000,
                    "default": DEFAULTS["response"]["max_length"],
                    "x-order": 1,
                },
                "enable_at_reply": {
                    "type": "boolean",
                    "title": "群聊 @ 用户回复",
                    "default": DEFAULTS["response"]["enable_at_reply"],
                    "x-order": 2,
                },
            },
        },
    },
}

register_plugin_schema("ai_chat", AI_CHAT_SCHEMA)


# ==================== 读写与缓存 ====================


_config: Optional[AIChatConfig] = None
_personas: Dict[str, PersonaConfig] = {}


def get_config_dir() -> Path:
    """获取配置目录（config/ai_chat/）"""

    cfg_dir = config_dir("ai_chat")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def get_config_path() -> Path:
    """获取配置文件路径（config/ai_chat/config.json）"""

    # 实际文件由框架管理，这里仅用于日志提示
    return get_config_dir() / "config.json"


def get_personas_path() -> Path:
    """获取人格配置文件路径（config/ai_chat/personas.json）"""

    return get_config_dir() / "personas.json"


def load_config() -> AIChatConfig:
    """加载配置文件（统一配置管理）"""

    global _config
    try:
        data = CFG.load() or {}
        _config = AIChatConfig(**data)

        # 基础校验：api 名称唯一 + api_active 合法
        try:
            names: List[str] = []
            unique: List[APIConfig] = []
            for item in _config.api:
                if item.name in names:
                    logger.warning(f"[AI Chat] api 名称重复已忽略: {item.name}")
                    continue
                names.append(item.name)
                unique.append(item)
            if len(unique) != len(_config.api):
                _config.api = unique
            # 修正 api_active
            if _config.api and _config.api_active not in names:
                _config.api_active = _config.api[0].name
        except Exception:
            pass

        logger.info("[AI Chat] 配置加载成功")
    except Exception as e:
        logger.error(f"[AI Chat] 配置加载失败: {e}，使用默认配置")
        _config = AIChatConfig(**DEFAULTS)
    return _config


def save_config(config: AIChatConfig) -> None:
    """保存配置文件（统一配置管理）"""

    try:
        CFG.save(config.model_dump())
        logger.info("[AI Chat] 配置保存成功")
    except Exception as e:
        logger.error(f"[AI Chat] 配置保存失败: {e}")


def get_config() -> AIChatConfig:
    """获取全局配置（带缓存）"""

    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_active_api() -> APIConfig:
    """获取当前启用的 API 配置（按名称选择）。"""

    cfg = get_config()
    if not cfg.api:
        # 回退到默认
        defaults = DEFAULTS["api"][0]
        return APIConfig(
            name="default",
            base_url=defaults["base_url"],
            api_key=defaults["api_key"],
            model=defaults["model"],
            timeout=defaults["timeout"],
        )
    for item in cfg.api:
        if item.name == cfg.api_active:
            return item
    return cfg.api[0]


def load_personas() -> Dict[str, PersonaConfig]:
    """加载人格配置（JSON 文件）"""

    global _personas
    path = get_personas_path()

    # 文件不存在则写入默认人格
    if not path.exists():
        logger.info("[AI Chat] 人格配置文件不存在，创建默认人格")
        _personas = {
            "default": PersonaConfig(
                name="默认助手",
                description="一个友好的 AI 助手",
                system_prompt="你是一个友好、乐于助人的 AI 助手。你的回复简洁明了，富有同理心。",
            ),
            "tsundere": PersonaConfig(
                name="傲娇少女",
                description="傲娇性格的少女。",
                system_prompt="你是一个傲娇少女，说话带有傲娇口癖，经常说‘才不是’、‘哼’之类的话。虽然嘴上不承认，但内心很关心对方。",
            ),
            "professional": PersonaConfig(
                name="专业顾问",
                description="专业的技术顾问。",
                system_prompt="你是一个专业的技术顾问，擅长编程、系统架构等领域。回复准确、专业，提供实用建议。",
            ),
        }
        save_personas(_personas)
        return _personas

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _personas = {k: PersonaConfig(**v) for k, v in (raw or {}).items()}
        logger.info(f"[AI Chat] 人格配置加载成功，共 {len(_personas)} 个人格")
    except Exception as e:
        logger.error(f"[AI Chat] 人格配置加载失败: {e}，使用默认人格")
        _personas = {
            "default": PersonaConfig(
                name="默认助手",
                description="一个友好的 AI 助手",
                system_prompt="你是一个友好、乐于助人的 AI 助手。你的回复简洁明了，富有同理心。",
            )
        }
    return _personas


def save_personas(personas: Dict[str, PersonaConfig]) -> None:
    """保存人格配置（JSON 文件）"""

    path = get_personas_path()
    try:
        data = {k: v.model_dump() for k, v in personas.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("[AI Chat] 人格配置保存成功")
    except Exception as e:
        logger.error(f"[AI Chat] 人格配置保存失败: {e}")


def get_personas() -> Dict[str, PersonaConfig]:
    """获取全局人格配置（带缓存）"""

    global _personas
    if not _personas:
        _personas = load_personas()
    return _personas


def reload_all() -> None:
    """重载配置与人格（供外部热重载调用）"""

    global _config, _personas
    _config = load_config()
    _personas = load_personas()
    logger.info("[AI Chat] 所有配置已重载")


# 注册框架级重载回调：当统一配置被重载时刷新模块缓存
register_reload_callback("ai_chat", reload_all)
