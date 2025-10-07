from __future__ import annotations

from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ...registry import Plugin


P = Plugin()
panel_upload = P.on_regex(r"^ww上传.*面板.*", name="upload", block=True, priority=1009)
panel_list = P.on_regex(r"^ww.*面板图.*", name="list", block=True, priority=1009)
panel_refresh = P.on_regex(r"^ww(?:刷新|更新)?面板(?:刷新)?$", name="refresh", block=True, priority=1009)


@panel_upload.handle()
async def _(matcher: Matcher, event: MessageEvent):
    gid = getattr(event, "group_id", None)
    if str(gid) != "757463664":
        await matcher.finish("上传面板图需在 757463664 群内")
    await matcher.finish()


@panel_list.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if isinstance(event, GroupMessageEvent):
        await matcher.finish("为防止刷屏，面板图不支持群内查看")
    await matcher.finish()


@panel_refresh.handle()
async def _(matcher: Matcher):
    await matcher.finish("更新已完成，如需刷新角色图请使用 `ww刷新角色面板` 相关命令")

