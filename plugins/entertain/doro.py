import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent
from ...core.api import Plugin
from ...core.api import register_namespaced_config, register_namespaced_schema


P = Plugin(name="entertain")
_CFG = register_namespaced_config("entertain", "doro", {})

# Minimal schema for namespace visibility in UI
try:
    register_namespaced_schema(
        "entertain",
        "doro",
        {
            "type": "object",
            "title": "doro 结局",
            "description": "无可配置项。发送 ‘doro结局’ 获取随机结局",
            "properties": {},
        },
    )
except Exception:
    pass
_DORO = P.on_regex(
    r"^#?(?:抽取|随机)?(?:今日)?doro结局$",
    name="draw",
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
