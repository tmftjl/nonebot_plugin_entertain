from __future__ import annotations
from ...core.constants import DEFAULT_HTTP_TIMEOUT


import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent

from ...core.api import Plugin
from .config import cfg_cached, cfg_api_urls  # noqa: F401  # ensure unified config is initialized


P = Plugin(name="entertain", display_name="濞变箰")

_SICK = P.on_regex(
    r"^(?:#|/)?鍙戠梾璇綍$",
    name="get",
    display_name="鍙戠梾璇綍",
    priority=5,
    block=True,
)


@_SICK.handle()
async def _(matcher: Matcher, event: MessageEvent):
    urls = cfg_api_urls()`n    url = str(urls.get("sick_quote_api") or "https://oiapi.net/API/SickL/")`n
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            res = await client.get(url)
            res.raise_for_status()
            data = res.json()
    except Exception:
        await matcher.finish("鑾峰彇鍙戠梾璇綍澶辫触锛岃绋嶅悗閲嶈瘯")
        return

    yl = data.get("message") or data.get("msg") or ""
    try:
        msg = Message(MessageSegment.at(event.user_id) + MessageSegment.text(f"\n{yl}"))
    except Exception:
        msg = Message(MessageSegment.text(f"# 鍙戠梾璇綍\n> {yl}"))
    # 鏀逛负 @ 鍥炲锛氬紩鐢ㄦ秷鎭苟@鍘熷彂閫佽€?    msg = Message(
        MessageSegment.at(event.user_id)
        + MessageSegment.text(f"\n{yl}")
    )
    await matcher.finish(msg)



