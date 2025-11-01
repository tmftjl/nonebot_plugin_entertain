from __future__ import annotations
from ...core.constants import DEFAULT_HTTP_TIMEOUT


import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent

from ...core.api import Plugin
from .config import cfg_cached, cfg_api_urls


P = Plugin(name="entertain", display_name="娱乐")

_SICK = P.on_regex(
    r"^(?:#|/)?发病语录$",
    name="get",
    display_name="发病语录",
    priority=5,
    block=True,
)


@_SICK.handle()
async def _(matcher: Matcher, event: MessageEvent):
    urls = cfg_api_urls()
    url = str(urls.get("sick_quote_api"))

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
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
