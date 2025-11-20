"""AI 工具注册与工具库

- 统一的工具注册装饰器 `@register_tool`
- 列出/启用工具，以及执行工具
- 可选加载 MCP(Model Context Protocol) 的动态工具
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, Optional, List

from nonebot.log import logger

# 可选的 MCP 集成
try:
    from ..mcp import mcp_manager  # type: ignore
except Exception:  # pragma: no cover
    mcp_manager = None  # type: ignore

# 全局工具注册表: name -> { schema..., handler }
_tool_registry: Dict[str, Dict[str, Any]] = {}


def register_tool(name: str, description: str, parameters: Optional[Dict[str, Any]] = None):
    """注册工具的装饰器

    Args:
        name: 工具名称
        description: 工具描述
        parameters: 工具参数（OpenAI JSON Schema 形式）

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
    """获取工具的 Schema（OpenAI 形式）"""

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


def get_enabled_tools(tool_names: List[str]) -> List[Dict[str, Any]]:
    """获取启用的工具 schema 列表（OpenAI 形式）
    - 同时合并 MCP 动态工具（若 mcp_manager 可用）
    """

    schemas: List[Dict[str, Any]] = []
    for name in tool_names:
        schema = get_tool_schema(name)
        if schema:
            schemas.append(schema)

    try:
        if mcp_manager is not None:
            mcp_schemas = mcp_manager.get_tool_schemas_for_names(tool_names)
            if mcp_schemas:
                schemas.extend(mcp_schemas)
    except Exception:
        pass
    return schemas


def list_tools() -> List[str]:
    """列出所有已注册的工具名称（含 MCP 动态工具，若可用）"""

    names: List[str] = list(_tool_registry.keys())
    try:
        if mcp_manager is not None:
            names.extend(mcp_manager.list_tool_names())
    except Exception:
        pass
    try:
        names = sorted(set(names))
    except Exception:
        pass
    return names


async def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """执行工具调用

    Args:
        name: 工具名称
        args: 工具参数

    Returns:
        执行结果（字符串）
    """

    # MCP 工具命名规范: mcp:<server>:<tool>
    if name.startswith("mcp:"):
        try:
            if mcp_manager is None:
                return "MCP 未启用或不可用"
            return await mcp_manager.execute_tool(name, args)
        except Exception as e:
            logger.error(f"[AI Chat] MCP 工具执行失败 {name}: {e}")
            return f"MCP 工具执行失败: {str(e)}"

    handler = get_tool_handler(name)
    if not handler:
        return f"错误：工具 {name} 不存在"

    try:
        result = await handler(**args)
        logger.info(f"[AI Chat] 工具调用成功: {name}({args}) -> {result}")
        return str(result)
    except Exception as e:
        error_msg = f"工具执行失败: {str(e)}"
        logger.error(f"[AI Chat] {error_msg}")
        return error_msg


# ==================== 基础内置工具 ====================


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

    # TODO: 可替换为真实天气 API
    weather_data = {
        "北京": "晴，25℃",
        "上海": "多云，28℃",
        "广州": "雷阵雨，30℃",
        "深圳": "晴，32℃",
    }

    weather = weather_data.get(city, f"晴，{25 + (abs(hash(city)) % 10)}℃")
    return f"{city} 天气：{weather}"


# ==================== 引入其它工具模块（例如联网） ====================
try:  # 侧效导入以完成注册
    from . import web as _web  # noqa: F401
except Exception as e:
    logger.debug(f"[AI Chat] 未加载联网工具: {e}")

__all__ = [
    "register_tool",
    "get_tool_handler",
    "get_tool_schema",
    "get_enabled_tools",
    "list_tools",
    "execute_tool",
]