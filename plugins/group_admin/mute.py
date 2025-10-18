from __future__ import annotations

from typing import Tuple

from nonebot.matcher import Matcher
from nonebot.params import RegexGroup
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageEvent,
    GroupMessageEvent,
)

from . import _P as P
from .utils import extract_at_or_id, parse_duration_to_seconds


 


mute_all_on = P.on_regex(
    r"^#开启全体禁言$",
    name="mute_all_on",
    display_name="开启全体禁言",
    priority=5,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@mute_all_on.handle()
async def _mute_all_on(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    try:
        await bot.set_group_whole_ban(group_id=event.group_id, enable=True)  # type: ignore[arg-type]
    except Exception as e:
        logger.exception(f"全体禁言失败: {e}")
        await matcher.finish("操作失败，可能权限不足")
    await matcher.finish("已开启全体禁言")


mute_all_off = P.on_regex(
    r"^#关闭全体禁言$",
    name="mute_all_off",
    display_name="关闭全体禁言",
    priority=5,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@mute_all_off.handle()
async def _mute_all_off(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    try:
        await bot.set_group_whole_ban(group_id=event.group_id, enable=False)  # type: ignore[arg-type]
    except Exception as e:
        logger.exception(f"关闭全体禁言失败: {e}")
        await matcher.finish("操作失败，可能权限不足")
    await matcher.finish("已关闭全体禁言")


mute_member = P.on_regex(
    r"^#禁言\s*(.+?)(?:\s+(\d+[a-zA-Z\u4e00-\u9fa5]*))?$",
    name="mute_member",
    display_name="禁言",
    priority=5,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@mute_member.handle()
async def _mute_member(matcher: Matcher, bot: Bot, event: MessageEvent, groups: Tuple = RegexGroup()):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    target_text = (groups[0] or "").strip() if groups else ""
    dur_text = (groups[1] or "").strip() if groups else ""
    uid = extract_at_or_id(event.message) if not target_text else extract_at_or_id(Message(target_text))
    if not uid:
        await matcher.finish("请@目标或提供QQ号")
    seconds = parse_duration_to_seconds(dur_text or "10m", 600)
    try:
        await bot.set_group_ban(group_id=event.group_id, user_id=uid, duration=seconds)
    except Exception as e:
        logger.exception(f"禁言失败: {e}")
        await matcher.finish("操作失败，可能权限不足或目标不在群内")
    await matcher.finish(f"已禁言 {seconds} 秒")


unmute_member = P.on_regex(
    r"^#(?:解禁|取消禁言)\s*(.+)?$",
    name="unmute_member",
    display_name="解禁",
    priority=5,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@unmute_member.handle()
async def _unmute_member(matcher: Matcher, bot: Bot, event: MessageEvent, groups: Tuple = RegexGroup()):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    target_text = (groups[0] or "").strip() if groups else ""
    uid = extract_at_or_id(event.message) if not target_text else extract_at_or_id(Message(target_text))
    if not uid:
        await matcher.finish("请@目标或提供QQ号")
    try:
        await bot.set_group_ban(group_id=event.group_id, user_id=uid, duration=0)
    except Exception as e:
        logger.exception(f"解禁失败: {e}")
        await matcher.finish("操作失败，可能权限不足或目标不在群内")
    await matcher.finish("已解除禁言")

