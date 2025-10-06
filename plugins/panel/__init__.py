from __future__ import annotations

from nonebot import on_regex
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ...perm import permission_for_cmd


# 规则来自原 Yunzai 插件（面板.js）
panel_upload = on_regex(r"^ww上传.*面板.*", block=True, priority=1009, permission=permission_for_cmd("panel", "upload"))
panel_list = on_regex(r"^ww.*面板图", block=True, priority=1009, permission=permission_for_cmd("panel", "list"))
panel_refresh = on_regex(r"^ww(?:刷新|更新)?面板(?:刷新)?$", block=True, priority=1009, permission=permission_for_cmd("panel", "refresh"))


@panel_upload.handle()
async def _(matcher: Matcher, event: MessageEvent):
    gid = getattr(event, "group_id", None)
    if str(gid) != "757463664":
        await matcher.finish("上传面板图需要加群 757463664 审核")
    # 在指定群内不提示（保持与原 JS 行为一致）
    await matcher.finish()


@panel_list.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if isinstance(event, GroupMessageEvent):
        await matcher.finish("为防止刷屏，面板图仅支持私聊查看")
    await matcher.finish()


@panel_refresh.handle()
async def _(matcher: Matcher):
    await matcher.finish("这次给你刷新了，下次刷新单个角色请使用`ww刷新【角色名】面板`，求求了")
