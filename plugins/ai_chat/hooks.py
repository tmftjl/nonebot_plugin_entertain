"""AI Chat 可扩展钩子（pre/post）
修改：统一使用 AiChat 数据类作为上下文传递，支持直接修改 AiChat 对象。
"""
from __future__ import annotations

from typing import Any, Callable, List
import inspect
from nonebot.log import logger

# 为了避免循环引用，这里只做类型引用的占位，运行时传入实际对象即可
# from .chat_manager import AiChat (不直接导入，避免循环引用)

PreHook = Callable[..., Any]
PostHook = Callable[..., Any]

_pre_ai_hooks: List[PreHook] = []
_post_ai_hooks: List[PostHook] = []


def register_pre_ai_hook(func: PreHook) -> PreHook:
    """注册调用 AI 之前的钩子。
    
    Hook 函数签名建议: async def my_hook(event, aichat: AiChat, **kwargs) -> AiChat | None
    """
    _pre_ai_hooks.append(func)
    return func


def register_post_ai_hook(func: PostHook) -> PostHook:
    """注册拿到 AI 结果后的钩子。
    
    Hook 函数签名建议: async def my_hook(event, aichat: AiChat, response: str, **kwargs) -> str | None
    """
    _post_ai_hooks.append(func)
    return func


async def _maybe_call(func: Callable, *args, **kwargs):
    try:
        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)
    except Exception:
        logger.exception("[AI Chat] 执行钩子出错")
        return None


async def run_pre_ai_hooks(event, aichat) -> Any:
    """
    依次执行所有 pre 钩子。
    钩子可以直接修改 aichat 对象的属性 (引用传递)，
    也可以返回一个新的 aichat 对象来覆盖。
    """
    current_aichat = aichat
    for h in _pre_ai_hooks:
        # 将 event 和 aichat 传给钩子，允许钩子读取 config, messages 等
        res = await _maybe_call(h, event, current_aichat)
        
        # 如果钩子返回了新的 AiChat 对象，则更新
        if res is not None and res.__class__.__name__ == 'AiChat':
            current_aichat = res
            
    return current_aichat


async def run_post_ai_hooks(event, aichat, response: str) -> str:
    """
    依次执行所有 post 钩子，允许串联修改 response。
    """
    out_response = response
    for h in _post_ai_hooks:
        res = await _maybe_call(h, event, aichat, out_response)
        if isinstance(res, str):
            out_response = res
    return out_response