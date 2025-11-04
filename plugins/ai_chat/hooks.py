"""AI Chat 可扩展钩子（pre/post）

提供在调用 AI 前后可扩展的钩子机制：
- 预处理钩子：可修改 messages/model/temperature/tools 等参数
- 后处理钩子：可修改最终 response

用法示例：
    from nonebot_plugin_entertain.plugins.ai_chat.hooks import (
        register_pre_ai_hook, register_post_ai_hook,
    )

    @register_pre_ai_hook
    async def my_pre(session, messages, model, temperature, tools, **ctx):
        # 可直接返回需要覆盖的字段
        return {"temperature": 0.2}

    @register_post_ai_hook
    async def my_post(session, messages, response, **ctx):
        return response + "\n-- from hook"
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
import inspect

from nonebot.log import logger


PreHook = Callable[..., Any]
PostHook = Callable[..., Any]

_pre_ai_hooks: List[PreHook] = []
_post_ai_hooks: List[PostHook] = []


def register_pre_ai_hook(func: PreHook) -> PreHook:
    """注册调用 AI 之前的钩子。

    入参约定：
    - session: ChatSession
    - messages: list[dict]
    - model: str | None
    - temperature: float | None
    - tools: list[dict] | None
    - 以及其他上下文通过 **ctx 传入

    返回：可为 None 或 dict，包含需要覆盖的键：messages/model/temperature/tools
    """
    try:
        _pre_ai_hooks.append(func)
    except Exception:
        logger.exception("[AI Chat] 注册 pre_ai_hook 失败")
    return func


def register_post_ai_hook(func: PostHook) -> PostHook:
    """注册拿到 AI 结果后的钩子。

    入参约定：
    - session: ChatSession
    - messages: list[dict]
    - response: str
    - 以及其他上下文通过 **ctx 传入

    返回：可为 None 或 str，新 response
    """
    try:
        _post_ai_hooks.append(func)
    except Exception:
        logger.exception("[AI Chat] 注册 post_ai_hook 失败")
    return func


async def _maybe_call(func: Callable, *args, **kwargs):
    try:
        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)
    except Exception:
        logger.exception("[AI Chat] 执行钩子出错")
        return None


async def run_pre_ai_hooks(
    *,
    session,
    messages: List[Dict[str, Any]],
    model: Optional[str],
    temperature: Optional[float],
    tools: Optional[List[Dict[str, Any]]],
    **ctx: Any,
) -> Dict[str, Any]:
    """依次执行所有 pre 钩子，聚合覆盖字段。"""
    overrides: Dict[str, Any] = {}
    for h in list(_pre_ai_hooks):
        res = await _maybe_call(h, session, messages, model, temperature, tools, **ctx)
        if isinstance(res, dict):
            overrides.update({k: v for k, v in res.items() if k in {"messages", "model", "temperature", "tools"}})
    return overrides


async def run_post_ai_hooks(
    *,
    session,
    messages: List[Dict[str, Any]],
    response: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    **ctx: Any,
) -> str:
    """依次执行所有 post 钩子，允许串联修改 response。"""
    out = response
    for h in list(_post_ai_hooks):
        res = await _maybe_call(h, session, messages, out, model=model, temperature=temperature, tools=tools, **ctx)
        if isinstance(res, str):
            out = res
    return out

