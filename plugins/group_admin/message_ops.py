from __future__ import annotations

from nonebot.matcher import Matcher
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    GroupMessageEvent,
)

from ...core.api import Plugin
from .utils import get_reply_message_id


P = Plugin()


recall_msg = P.on_regex(
    r"^#撤回$",
    name="recall_msg",
    display_name="撤回消息",
    priority=13,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@recall_msg.handle()
async def _recall_msg(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    mid = get_reply_message_id(event.message)
    if not mid:
        await matcher.finish("请回复要撤回的消息后再使用该命令")
    try:
        await bot.delete_msg(message_id=mid)
        await matcher.finish("已撤回")
    except Exception as e:
        logger.exception(f"撤回失败: {e}")
        await matcher.finish("撤回失败，可能权限不足或超时")


set_essence = P.on_regex(
    r"^#(?:设置精华|设精)$",
    name="set_essence",
    display_name="设置精华",
    priority=13,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@set_essence.handle()
async def _set_essence(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    mid = get_reply_message_id(event.message)
    if not mid:
        await matcher.finish("请回复目标消息后再使用")
    try:
        await bot.set_essence_msg(message_id=mid)
        await matcher.finish("已设置为精华")
    except Exception as e:
        logger.exception(f"设置精华失败: {e}")
        await matcher.finish("设置失败，可能权限不足或该平台不支持")


unset_essence = P.on_regex(
    r"^#取消精华$",
    name="unset_essence",
    display_name="取消精华",
    priority=13,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@unset_essence.handle()
async def _unset_essence(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群聊中使用")
    mid = get_reply_message_id(event.message)
    if not mid:
        await matcher.finish("请回复目标消息后再使用")
    try:
        await bot.delete_essence_msg(message_id=mid)
        await matcher.finish("已取消精华")
    except Exception as e:
        logger.exception(f"取消精华失败: {e}")
        await matcher.finish("取消失败，可能权限不足或该平台不支持")

