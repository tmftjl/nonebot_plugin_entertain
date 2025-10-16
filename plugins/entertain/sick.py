from __future__ import annotations

import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent

from ...core.api import Plugin
from .config import cfg_cached  # noqa: F401  # ensure unified config is initialized


P = Plugin(name="entertain", display_name="娱乐")

_SICK = P.on_regex(
    r"^(?:#|/)?发病语录$",
    name="get",
    priority=12,
    block=True,
)


@_SICK.handle()
async def _(matcher: Matcher, event: MessageEvent):
    url = "https://oiapi.net/API/SickL/"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(url)
            res.raise_for_status()
            data = res.json()
    except Exception:
        await matcher.finish("获取发病语录失败，请稍后重试")
        return

    yl = data.get("message") or data.get("msg") or ""
    try:
        msg = Message(MessageSegment.at(event.user_id) + MessageSegment.text(f"\n{yl}"))
    except Exception:
        msg = Message(MessageSegment.text(f"# 发病语录\n> {yl}"))
    # 改为 @ 回复：引用消息并@原发送者
    msg = Message(
        MessageSegment.at(event.user_id)
        + MessageSegment.text(f"\n{yl}")
    )
    await matcher.finish(msg)
