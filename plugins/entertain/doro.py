from __future__ import annotations
from ...core.constants import DEFAULT_HTTP_TIMEOUT
import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent
from ...core.api import Plugin
from ...core.http import get_shared_async_client
from .config import cfg_cached, cfg_api_urls


P = Plugin(name="entertain", display_name="娱乐")

_DORO = P.on_regex(
    r"^#?(?:抽取|来个)?(?:随机)?doro卡$",
    name="draw",
    display_name="doro卡",
    priority=5,
    block=True,
)


@_DORO.handle()
async def _(matcher: Matcher, event: MessageEvent):
    urls = cfg_api_urls()
    url = str(urls.get("doro_api"))
    client = await get_shared_async_client()
    res = await client.get(url, timeout=DEFAULT_HTTP_TIMEOUT)
    res.raise_for_status()
    data = res.json()

    title = data.get("title", "")
    desc = data.get("description", "")
    img = data.get("image")

    text_seg = MessageSegment.text(f"今日doro抽取：\n\n{title}\n\n{desc}\n")
    if img:
        await matcher.finish(Message(text_seg + MessageSegment.image(img)))
    else:
        await matcher.finish(Message(text_seg))

