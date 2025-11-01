﻿from __future__ import annotations

from nonebot.matcher import Matcher
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    GroupMessageEvent,
)
from . import _P as P
from .utils import extract_at_or_id
from ...core.framework.perm import PermLevel, PermScene

set_admin = P.on_regex(
    r"^#设置管理员\\s*(.+)$",
    name="set_admin",
    display_name="设置管理员",
    priority=5,
    block=True,
    enabled=True,
    level=PermLevel.OWNER,
    scene=PermScene.GROUP,
)


unset_admin = P.on_regex(
    r"^#取消管理员\\s*(.+)$",
    name="unset_admin",
    display_name="取消管理员",
    priority=5,
    block=True,
    enabled=True,
    level=PermLevel.OWNER,
    scene=PermScene.GROUP,
)


@set_admin.handle()
async def _set_admin(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    uid = extract_at_or_id(event.message)
    if not uid:
        await matcher.finish("请@目标或提供QQ号")
    try:
        await bot.set_group_admin(group_id=event.group_id, user_id=uid, enable=True)
    except Exception as e:
        logger.exception(f"设置管理员失败 {e}")
        await matcher.finish("操作失败，可能权限不足或目标不在群内")
    await matcher.finish("已设置为管理员")


@unset_admin.handle()
async def _unset_admin(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    uid = extract_at_or_id(event.message)
    if not uid:
        await matcher.finish("请@目标或提供QQ号")
    try:
        await bot.set_group_admin(group_id=event.group_id, user_id=uid, enable=False)
    except Exception as e:
        logger.exception(f"取消管理员失败 {e}")
        await matcher.finish("操作失败，可能权限不足或目标不在群内")
    await matcher.finish("已取消管理员")


kick_member = P.on_regex(
    r"^#踢出\\s*(.+)$",
    name="kick_member",
    display_name="踢人",
    priority=5,
    block=True,
    enabled=True,
    level=PermLevel.ADMIN,
    scene=PermScene.GROUP,
)


ban_kick_member = P.on_regex(
    r"^#拉黑踢出\\s*(.+)$",
    name="ban_kick_member",
    display_name="设置管理员",
    priority=5,
    block=True,
    enabled=True,
    level=PermLevel.ADMIN,
    scene=PermScene.GROUP,
)


@kick_member.handle()
async def _kick_member(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    uid = extract_at_or_id(event.message)
    if not uid:
        await matcher.finish("请@目标或提供QQ号")
    try:
        await bot.set_group_kick(group_id=event.group_id, user_id=uid, reject_add_request=False)
    except Exception as e:
        logger.exception(f"踢人失败: {e}")
        await matcher.finish("操作失败，可能权限不足或目标不在群内")
    await matcher.finish("已将其移出群聊")


@ban_kick_member.handle()
async def _ban_kick_member(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    uid = extract_at_or_id(event.message)
    if not uid:
        await matcher.finish("请@目标或提供QQ号")
    try:
        await bot.set_group_kick(group_id=event.group_id, user_id=uid, reject_add_request=True)
    except Exception as e:
        logger.exception(f"拉黑踢出失败 {e}")
        await matcher.finish("操作失败，可能权限不足或目标不在群内")
    await matcher.finish("已将其移出并加入黑名单")










