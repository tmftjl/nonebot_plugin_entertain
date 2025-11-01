from ...core.constants import DEFAULT_HTTP_TIMEOUT
import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent
from ...core.api import Plugin
from .config import cfg_cached, cfg_api_urls  # noqa: F401  # ensure unified config is initialized


P = Plugin(name="entertain", display_name="濞变箰")

_DORO = P.on_regex(
    r"^#?(?:鎶藉彇|闅忔満)?(?:浠婃棩)?doro缁撳眬$",
    name="draw",
    display_name="doro缁撳眬",
    priority=5,
    block=True,
)


@_DORO.handle()
async def _(matcher: Matcher, event: MessageEvent):
    urls = cfg_api_urls()`n    url = str(urls.get("doro_api") or "https://doro-api.hxxn.cc/get")`n
    async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
        res = await client.get(url)
        res.raise_for_status()
        data = res.json()

    title = data.get("title", "")
    desc = data.get("description", "")
    img = data.get("image")

    text_seg = MessageSegment.text(f"浠婃棩doro缁撳眬锛歕n\n{title}\n\n{desc}\n")
    if img:
        await matcher.finish(Message(text_seg + MessageSegment.image(img)))
    else:
        await matcher.finish(Message(text_seg))


