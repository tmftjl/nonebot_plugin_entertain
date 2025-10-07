from __future__ import annotations

import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent

from ...registry import Plugin


P = Plugin()
_SICK = P.on_regex(
    r"^(?:#|/)?发病语录$",
    name="get",
    priority=13,
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

    yl = data.get("message") or data.get("msg") or "……"
    try:
        msg = Message(MessageSegment.at(event.user_id) + MessageSegment.text(f"\n{yl}"))
    except Exception:
        msg = Message(MessageSegment.text(f"# 发病语录\n> {yl}"))
    await matcher.finish(msg)

