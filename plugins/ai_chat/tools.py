"""AI 对话工具注册与调用

使用装饰器注册工具，支持 OpenAI Function Calling 格式。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from nonebot.log import logger


# 全局工具注册表：name -> { schema..., handler }
_tool_registry: Dict[str, Dict[str, Any]] = {}


def register_tool(name: str, description: str, parameters: Optional[Dict[str, Any]] = None):
    """工具注册装饰器

    Args:
        name: 工具名称
        description: 工具描述
        parameters: 参数定义（OpenAI JSON Schema 格式）

    Example:
        @register_tool(
            name="get_time",
            description="获取当前时间",
            parameters={}
        )
        async def tool_get_time() -> str:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    """

    def decorator(func: Callable):
        _tool_registry[name] = {
            "name": name,
            "description": description,
            "parameters": parameters or {"type": "object", "properties": {}},
            "handler": func,
        }
        logger.debug(f"[AI Chat] 工具已注册: {name}")
        return func

    return decorator


def get_tool_handler(name: str) -> Optional[Callable]:
    """获取工具处理函数"""

    tool = _tool_registry.get(name)
    if tool:
        return tool["handler"]
    return None


def get_tool_schema(name: str) -> Optional[Dict[str, Any]]:
    """获取工具 Schema（OpenAI 格式）"""

    tool = _tool_registry.get(name)
    if not tool:
        return None

    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["parameters"],
        },
    }


def get_enabled_tools(tool_names: list[str]) -> list[Dict[str, Any]]:
    """获取启用的工具列表（OpenAI 格式）"""

    schemas: list[Dict[str, Any]] = []
    for name in tool_names:
        schema = get_tool_schema(name)
        if schema:
            schemas.append(schema)
    return schemas


def list_tools() -> list[str]:
    """列出所有已注册的工具名称"""

    return list(_tool_registry.keys())


# ==================== 内置工具 ====================


@register_tool(
    name="get_time",
    description="获取当前日期和时间",
    parameters={"type": "object", "properties": {}},
)
async def tool_get_time() -> str:
    """获取当前时间"""

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@register_tool(
    name="get_weather",
    description="获取指定城市的天气信息（模拟）",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "城市名称"}},
        "required": ["city"],
    },
)
async def tool_get_weather(city: str) -> str:
    """获取天气（模拟）"""

    # TODO: 可接入真实天气 API
    weather_data = {
        "北京": "晴，25℃",
        "上海": "多云，28℃",
        "广州": "阵雨，30℃",
        "深圳": "晴，32℃",
    }

    weather = weather_data.get(city, f"晴，{25 + (abs(hash(city)) % 10)}℃")
    return f"{city}的天气：{weather}"


async def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """执行工具调用

    Args:
        name: 工具名称
        args: 工具参数

    Returns:
        工具执行结果（字符串）
    """

    handler = get_tool_handler(name)
    if not handler:
        return f"错误：工具 {name} 不存在"

    try:
        # 执行工具
        result = await handler(**args)
        logger.info(f"[AI Chat] 工具调用成功: {name}({args}) -> {result}")
        return str(result)
    except Exception as e:
        error_msg = f"工具执行失败: {str(e)}"
        logger.error(f"[AI Chat] {error_msg}")
        return error_msg

