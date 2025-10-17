from __future__ import annotations

from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ...core.api import Plugin


P = Plugin(name="useful", display_name="有用的")
panel_upload = P.on_regex(r"^ww上传.*面板图$", name="upload",display_name="上传面板图提示", block=True, priority=12)
panel_list = P.on_regex(r"^ww.*面板图列表$", name="list",display_name="面板图列表提示", block=True, priority=12)
panel_refresh = P.on_regex(r"^ww(?:刷新|更新)?面板(?:刷新)?$",display_name="刷新面板提示", name="refresh", block=True, priority=12)


@panel_upload.handle()
async def _(matcher: Matcher, event: MessageEvent):
    gid = getattr(event, "group_id", None)
    if str(gid) != "757463664":
        await matcher.finish("上传面板图需加群 757463664 审核")
    await matcher.finish()


@panel_list.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if isinstance(event, GroupMessageEvent):
        await matcher.finish("为防止刷屏，面板图仅支持私聊查看")
    await matcher.finish()


@panel_refresh.handle()
async def _(matcher: Matcher):
    await matcher.finish("更新已完成，下次刷单个角色请使用 `ww刷新【角色名】面板` ")
