from ...config import get_config\n"""AI 瀵硅瘽宸ュ叿娉ㄥ唽涓庤皟鐢?

浣跨敤瑁呴グ鍣ㄦ敞鍐屽伐鍏凤紝鏀寔 OpenAI Function Calling 鏍煎紡銆?
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from nonebot.log import logger
try:
    # Optional provider (used by multimodal tools)
    from ..providers.openai_service import OpenAIService
except Exception:  # pragma: no cover
    OpenAIService = None  # type: ignore


# 鍏ㄥ眬宸ュ叿娉ㄥ唽琛細name -> { schema..., handler }
_tool_registry: Dict[str, Dict[str, Any]] = {}


def register_tool(name: str, description: str, parameters: Optional[Dict[str, Any]] = None):
    """宸ュ叿娉ㄥ唽瑁呴グ鍣?

    Args:
        name: 宸ュ叿鍚嶇О
        description: 宸ュ叿鎻忚堪
        parameters: 鍙傛暟瀹氫箟锛圤penAI JSON Schema 鏍煎紡锛?

    Example:
        @register_tool(
            name="get_time",
            description="鑾峰彇褰撳墠鏃堕棿",
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
        logger.debug(f"[AI Chat] 宸ュ叿宸叉敞鍐? {name}")
        return func

    return decorator


def get_tool_handler(name: str) -> Optional[Callable]:
    """鑾峰彇宸ュ叿澶勭悊鍑芥暟"""

    tool = _tool_registry.get(name)
    if tool:
        return tool["handler"]
    return None


def get_tool_schema(name: str) -> Optional[Dict[str, Any]]:
    """鑾峰彇宸ュ叿 Schema锛圤penAI 鏍煎紡锛?""

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
    """鑾峰彇鍚敤鐨勫伐鍏峰垪琛紙OpenAI 鏍煎紡锛?""

    schemas: list[Dict[str, Any]] = []
    for name in tool_names:
        schema = get_tool_schema(name)
        if schema:
            schemas.append(schema)
    return schemas


def list_tools() -> list[str]:
    """鍒楀嚭鎵€鏈夊凡娉ㄥ唽鐨勫伐鍏峰悕绉?""

    return list(_tool_registry.keys())


# ==================== 鍐呯疆宸ュ叿 ====================


@register_tool(
    name="get_time",
    description="鑾峰彇褰撳墠鏃ユ湡鍜屾椂闂?,
    parameters={"type": "object", "properties": {}},
)
async def tool_get_time() -> str:
    """鑾峰彇褰撳墠鏃堕棿"""

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@register_tool(
    name="get_weather",
    description="鑾峰彇鎸囧畾鍩庡競鐨勫ぉ姘斾俊鎭紙妯℃嫙锛?,
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "鍩庡競鍚嶇О"}},
        "required": ["city"],
    },
)
async def tool_get_weather(city: str) -> str:
    """鑾峰彇澶╂皵锛堟ā鎷燂級"""

    # TODO: 鍙帴鍏ョ湡瀹炲ぉ姘?API
    weather_data = {
        "鍖椾含": "鏅达紝25鈩?,
        "涓婃捣": "澶氫簯锛?8鈩?,
        "骞垮窞": "闃甸洦锛?0鈩?,
        "娣卞湷": "鏅达紝32鈩?,
    }

    weather = weather_data.get(city, f"鏅达紝{25 + (abs(hash(city)) % 10)}鈩?)
    return f"{city}鐨勫ぉ姘旓細{weather}"


async def execute_tool(name: str, args: Dict[str, Any]) -> str:
    """鎵ц宸ュ叿璋冪敤

    Args:
        name: 宸ュ叿鍚嶇О
        args: 宸ュ叿鍙傛暟

    Returns:
        宸ュ叿鎵ц缁撴灉锛堝瓧绗︿覆锛?
    """

    handler = get_tool_handler(name)
    if not handler:
        return f"閿欒锛氬伐鍏?{name} 涓嶅瓨鍦?

    try:
        # 鎵ц宸ュ叿
        result = await handler(**args)
        logger.info(f"[AI Chat] 宸ュ叿璋冪敤鎴愬姛: {name}({args}) -> {result}")
        return str(result)
    except Exception as e:
        error_msg = f"宸ュ叿鎵ц澶辫触: {str(e)}"
        logger.error(f"[AI Chat] {error_msg}")
        return error_msg


# ==================== Multimodal built-ins ====================


@register_tool(
    name="image_generate",
    description="浣跨敤鏂囩敓鍥炬ā鍨嬫牴鎹彁绀鸿瘝鐢熸垚鍥剧墖锛岃繑鍥炰竴涓垨澶氫釜鍥剧墖 URL锛堟垨 data URL锛?,
    parameters={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "鍥剧墖鎻忚堪"},
            "n": {"type": "integer", "description": "鐢熸垚鏁伴噺", "minimum": 1, "maximum": 4},
            "size": {"type": "string", "description": "鍒嗚鲸鐜囷紝濡?512x512 / 1024x1024"},
        },
        "required": ["prompt"],
    },
)
async def tool_image_generate(prompt: str, n: int = 1, size: str = "1024x1024") -> str:
    if OpenAIService is None:
        return "{\"error\":\"provider_unavailable\"}"
    try:
        service = OpenAIService()
        images = await service.generate_images(prompt=prompt, n=n, size=size)
        import json as _json
        return _json.dumps({"images": images}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[AI Chat] image_generate failed: {e}")
        return "{\"error\":\"image_generate_failed\"}"


@register_tool(
    name="tts_speak",
    description="灏嗘枃鏈浆鎹负璇煶骞惰繑鍥炴湰鍦版枃浠惰矾寰勶紙mp3锛?,
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "瑕佸悎鎴愮殑鏂囨湰"},
            "voice": {"type": "string", "description": "闊宠壊锛屽 alloy"},
            "format": {"type": "string", "description": "闊抽鏍煎紡锛岄粯璁?mp3"},
        },
        "required": ["text"],
    },
)
async def tool_tts_speak(text: str, voice: str = "alloy", format: str = "mp3") -> str:
    """TTS 工具：受配置项控制，支持自定义默认音色/格式。

    - 若未启用 TTS：返回提示 JSON，不抛错。
    - 仅内置 openai 提供者；自定义可扩展。
    """
    try:
        cfg = get_config()
        if not getattr(cfg, "tts", None) or not cfg.tts.enabled:
            return "{\"error\":\"tts_disabled\"}"
        provider = (cfg.tts.provider or "openai").lower()
        if not voice:
            voice = cfg.tts.default_voice or "alloy"
        if not format:
            format = cfg.tts.default_format or "mp3"
        if provider != "openai" or OpenAIService is None:
            return "{\"error\":\"provider_not_supported\"}"

        service = OpenAIService()
        path = await service.text_to_speech(text=text, voice=voice, fmt=format)
        if not path:
            return "{\"error\":\"tts_failed\"}"
        import json as _json
        return _json.dumps({"audio": path}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[AI Chat] tts_speak failed: {e}")
        return "{\"error\":\"tts_failed\"}"


