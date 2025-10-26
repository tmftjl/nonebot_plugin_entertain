"""AI 对话配置管理（去掉无用和多余嵌套，简化结构）

职责：
- 注册并管理 `config/ai_chat/config.json`
- 提供 Pydantic 配置对象供代码内部访问
- 管理 `config/ai_chat/personas.json` 的人格配置
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

class SessionConfig(BaseModel):
    """会话配置"""

    # 当前启用的服务商名称（从根迁移至 session 下）
    api_active: str = Field(default="default", description="当前启用服务商名")
    default_temperature: float = Field(default=0.7, description="默认温度")
    # 统一“轮数”限制（user+assistant 为一轮）
    max_rounds: int = Field(default=8, description="最大上下文轮数（一轮=用户+助手）")
    # 群聊“聊天室记忆”（内存）最大行数
    chatroom_history_max_lines: int = Field(default=200, description="群聊聊天室记忆（内存）最大行数")
    # 主动回复（去掉 chatroom_enhance 的多余嵌套，直接扁平化配置）
    active_reply_enable: bool = Field(default=False, description="群聊内是否开启‘主动回复’实验功能")
    active_reply_probability: float = Field(default=0.1, description="主动回复触发概率（0~1）")
    active_reply_prompt_suffix: str = Field(
        default=(
            "Now, a new message is coming: `{message}`. Please react to it. "
            "Only output your response and do not output any other information."
        ),
        description="主动回复时附加在提示后的后缀提示（可用 {message}/{prompt} 占位）",
    )


class ToolsConfig(BaseModel):
    """工具配置"""

    enabled: bool = Field(default=False, description="是否启用工具")
    max_iterations: int = Field(default=3, description="最多工具调用迭代次数")
    builtin_tools: list[str] = Field(
        default_factory=lambda: ["get_time", "get_weather"], description="内置工具"
    )


"""
删除无用配置：
- 删除 MCP（预留）
- 删除 response（未使用的‘回复’相关配置）
- 删除 session.default_max_history（未使用）
"""


class AIChatConfig(BaseModel):
    """AI 对话总配置"""

    # api 从数组改为字典样式：{ 名称: APIConfig }
    api: Dict[str, APIConfig] = Field(default_factory=dict, description="AI 服务商配置（字典：名称->配置）")
    session: SessionConfig = Field(default_factory=SessionConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)


class PersonaConfig(BaseModel):
    """人格配置"""

    name: str = Field(description="人格名称")
    description: str = Field(description="人格描述")
    system_prompt: str = Field(description="系统提示")


# ==================== 统一配置注册 ====================


DEFAULTS: Dict[str, Any] = {
    "api": {
        "default": {
            "name": "default",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4o-mini",
            "timeout": 60,
        }
    },
    "session": {
        "api_active": "default",
        "default_temperature": 0.7,
        "max_rounds": 8,
        "chatroom_history_max_lines": 200,
        # 扁平化主动回复配置（替代原来的 chatroom_enhance.active_reply.*）
        "active_reply_enable": False,
        "active_reply_prompt_suffix": (
            "Now, a new message is coming: `{message}`. Please react to it. "
            "Only output your response and do not output any other information."
        ),
        "active_reply_probability": 0.1,
    },
    "tools": {
        "enabled": False,
        "max_iterations": 3,
        "builtin_tools": ["get_time", "get_weather"],
    },
}

# 注册配置文件（config/ai_chat/config.json）
CFG = register_plugin_config("ai_chat", DEFAULTS)


# 注册前端 JSON Schema（用于可视化编辑）
AI_CHAT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "AI 对话",
    "properties": {
        "api": {
            "type": "object",
            "title": "AI 服务商（字典：名称->配置）",
            "x-order": 1,
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "title": "名称（可省略）", "x-order": 1},
                    "base_url": {
                        "type": "string",
                        "title": "API 地址",
                        "default": DEFAULTS["api"]["default"]["base_url"],
                        "x-order": 2,
                    },
                    "api_key": {
                        "type": "string",
                        "title": "API 密钥",
                        "default": DEFAULTS["api"]["default"]["api_key"],
                        "x-order": 3,
                    },
                    "model": {
                        "type": "string",
                        "title": "默认模型",
                        "default": DEFAULTS["api"]["default"]["model"],
                        "x-order": 4,
                    },
                    "timeout": {
                        "type": "integer",
                        "title": "超时（秒）",
                        "minimum": 1,
                        "maximum": 300,
                        "default": DEFAULTS["api"]["default"]["timeout"],
                        "x-order": 5,
                    },
                },
            },
        },
        "session": {
            "type": "object",
            "title": "会话",
            "x-order": 4,
            "x-collapse": True,
            "properties": {
                "api_active": {
                    "type": "string",
                    "title": "当前启用服务商名",
                    "default": DEFAULTS["session"]["api_active"],
                    "x-order": 2,
                },
                "default_temperature": {
                    "type": "number",
                    "title": "默认温度",
                    "minimum": 0,
                    "maximum": 2,
                    "default": DEFAULTS["session"]["default_temperature"],
                    "x-order": 1,
                },
                "max_rounds": {
                    "type": "integer",
                    "title": "最大上下文轮数",
                    "minimum": 1,
                    "maximum": 50,
                    "default": DEFAULTS["session"]["max_rounds"],
                    "x-order": 3,
                },
                "chatroom_history_max_lines": {
                    "type": "integer",
                    "title": "聊天室记忆最大行数",
                    "minimum": 1,
                    "maximum": 5000,
                    "default": DEFAULTS["session"]["chatroom_history_max_lines"],
                    "x-order": 4,
                },
                "active_reply_enable": {
                    "type": "boolean",
                    "title": "群聊启用主动回复（实验）",
                    "default": DEFAULTS["session"]["active_reply_enable"],
                    "x-order": 5,
                },
                "active_reply_probability": {
                    "type": "number",
                    "title": "主动回复触发概率（0~1）",
                    "minimum": 0,
                    "maximum": 1,
                    "default": DEFAULTS["session"]["active_reply_probability"],
                    "x-order": 6,
                },
                "active_reply_prompt_suffix": {
                    "type": "string",
                    "title": "主动回复提示后缀",
                    "default": DEFAULTS["session"]["active_reply_prompt_suffix"],
                    "x-order": 7,
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
                    "title": "最多工具迭代次数",
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
    },
}

register_plugin_schema("ai_chat", AI_CHAT_SCHEMA)


# ==================== 读写与缓存 ====================


_config: Optional[AIChatConfig] = None
_personas: Dict[str, PersonaConfig] = {}


def get_config_dir() -> Path:
    cfg_dir = config_dir("ai_chat")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def get_personas_path() -> Path:
    return get_config_dir() / "personas.json"


def load_config() -> AIChatConfig:
    global _config
    try:
        data = CFG.load() or {}

        # 兼容旧版：将 api 数组转换为字典样式
        api_raw = data.get("api")
        if isinstance(api_raw, list):
            api_dict: Dict[str, Dict[str, Any]] = {}
            for it in api_raw:
                if not isinstance(it, dict):
                    continue
                name = it.get("name") or it.get("id") or "default"
                api_dict[name] = {
                    "name": name,
                    "base_url": it.get("base_url") or DEFAULTS["api"]["default"]["base_url"],
                    "api_key": it.get("api_key") or DEFAULTS["api"]["default"]["api_key"],
                    "model": it.get("model") or DEFAULTS["api"]["default"]["model"],
                    "timeout": it.get("timeout") or DEFAULTS["api"]["default"]["timeout"],
                }
            data["api"] = api_dict

        # 兼容旧版：将根级 api_active 迁移到 session.api_active
        if "api_active" in data:
            sess0 = data.get("session") or {}
            if "api_active" not in sess0:
                sess0["api_active"] = data.get("api_active")
            data["session"] = sess0
            try:
                del data["api_active"]
            except Exception:
                pass

        # 兼容旧版：扁平化 chatroom_enhance.active_reply.*
        sess = data.get("session") or {}
        if isinstance(sess.get("chatroom_enhance"), dict):
            ar = (sess.get("chatroom_enhance") or {}).get("active_reply") or {}
            if isinstance(ar, dict):
                if "active_reply_enable" not in sess:
                    sess["active_reply_enable"] = bool(ar.get("enable", False))
                if "active_reply_prompt_suffix" not in sess and ar.get("prompt_suffix") is not None:
                    sess["active_reply_prompt_suffix"] = ar.get("prompt_suffix")
                if "active_reply_probability" not in sess and ar.get("probability") is not None:
                    try:
                        sess["active_reply_probability"] = float(ar.get("probability"))
                    except Exception:
                        pass
            # 删除旧结构
            try:
                del sess["chatroom_enhance"]
            except Exception:
                pass
            data["session"] = sess

        _config = AIChatConfig(**data)

        # 基础校验：api_active 合法，并补齐每个 API 的 name
        try:
            names: List[str] = []
            for n, v in list(_config.api.items()):
                if isinstance(v, APIConfig):
                    if not v.name:
                        v.name = n
                names.append(n)
            # 修正到 session.api_active
            if _config.api and _config.session.api_active not in names:
                _config.session.api_active = names[0]
        except Exception:
            pass

        logger.info("[AI Chat] 配置加载成功")
    except Exception as e:
        logger.error(f"[AI Chat] 配置加载失败: {e}，使用默认配置")
        _config = AIChatConfig(**DEFAULTS)
    return _config


def save_config(config: AIChatConfig) -> None:
    try:
        CFG.save(config.model_dump())
        logger.info("[AI Chat] 配置保存成功")
    except Exception as e:
        logger.error(f"[AI Chat] 配置保存失败: {e}")


def get_config() -> AIChatConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_active_api() -> APIConfig:
    cfg = get_config()
    if not cfg.api:
        defaults = DEFAULTS["api"]["default"]
        return APIConfig(
            name="default",
            base_url=defaults["base_url"],
            api_key=defaults["api_key"],
            model=defaults["model"],
            timeout=defaults["timeout"],
        )
    # 命中当前启用
    active_name = getattr(cfg.session, "api_active", None) or "default"
    if active_name in cfg.api:
        api = cfg.api[active_name]
        if isinstance(api, APIConfig):
            return api
        return APIConfig(**{**api, "name": active_name})
    # 取第一个
    first_name = next(iter(cfg.api.keys()))
    api = cfg.api[first_name]
    if isinstance(api, APIConfig):
        return api
    return APIConfig(**{**api, "name": first_name})


def load_personas() -> Dict[str, PersonaConfig]:
    global _personas
    path = get_personas_path()

    if not path.exists():
        logger.info("[AI Chat] 人格配置文件不存在，创建默认人格")
        _personas = {
            "default": PersonaConfig(
                name="默认助手",
                description="一个友好的 AI 助手",
                system_prompt="你是一个友好、耐心且乐于助人的 AI 助手。回答简洁清晰，有同理心。",
            ),
            "tsundere": PersonaConfig(
                name="傲娇少女",
                description="傲娇属性的人格",
                system_prompt="你是一个有些傲娇的人格，说话常带有‘才不是’‘哼’之类的口癖，外冷内热。",
            ),
            "professional": PersonaConfig(
                name="专业问答",
                description="专业的技术问答",
                system_prompt="你是一个专业的技术问答助手，擅长编程、系统架构等。回答准确、专业，提供实用建议。",
            ),
        }
        save_personas(_personas)
        return _personas

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _personas = {k: PersonaConfig(**v) for k, v in (raw or {}).items()}
        logger.info(f"[AI Chat] 人格配置加载成功，共 {_personas and len(_personas) or 0} 个")
    except Exception as e:
        logger.error(f"[AI Chat] 人格配置加载失败: {e}，使用默认人格")
        _personas = {
            "default": PersonaConfig(
                name="默认助手",
                description="一个友好的 AI 助手",
                system_prompt="你是一个友好、耐心且乐于助人的 AI 助手。回答简洁清晰，有同理心。",
            )
        }
    return _personas


def save_personas(personas: Dict[str, PersonaConfig]) -> None:
    path = get_personas_path()
    try:
        data = {k: v.model_dump() for k, v in personas.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("[AI Chat] 人格配置保存成功")
    except Exception as e:
        logger.error(f"[AI Chat] 人格配置保存失败: {e}")


def get_personas() -> Dict[str, PersonaConfig]:
    global _personas
    if not _personas:
        _personas = load_personas()
    return _personas


def reload_all() -> None:
    global _config, _personas
    _config = load_config()
    _personas = load_personas()
    logger.info("[AI Chat] 所有配置已重新加载")


# 注册框架层重载回调：当统一配置被重载时刷新模块缓存
register_reload_callback("ai_chat", reload_all)
