import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent
from ...core.api import Plugin
from .config import cfg_cached  # noqa: F401  # ensure unified config is initialized


P = Plugin(name="entertain", display_name="娱乐")

_DORO = P.on_regex(
    r"^#?(?:抽取|随机)?(?:今日)?doro结局$",
    name="draw",
    display_name="doro结局",
    priority=12,
    block=True,
)


@_DORO.handle()
async def _(matcher: Matcher, event: MessageEvent):
    url = "https://doro-api.hxxn.cc/get"
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(url)
        res.raise_for_status()
        data = res.json()

    title = data.get("title", "")
    desc = data.get("description", "")
    img = data.get("image")

    text_seg = MessageSegment.text(f"今日doro结局：\n\n{title}\n\n{desc}\n")
    if img:
        await matcher.finish(Message(text_seg + MessageSegment.image(img)))
    else:
        await matcher.finish(Message(text_seg))
