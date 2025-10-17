from __future__ import annotations

from nonebot.matcher import Matcher
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    GroupMessageEvent,
)

from . import _P as P
from .utils import get_target_message_id

recall_msg = P.on_regex(
    r"^#鎾ゅ洖$",
    name="recall_msg",
    display_name="鎾ゅ洖娑堟伅",
    priority=13,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@recall_msg.handle()
async def _recall_msg(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("璇峰湪缇よ亰涓娇鐢?)
    mid = get_target_message_id(event)
    if not mid:
        await matcher.finish("璇峰洖澶嶈鎾ゅ洖鐨勬秷鎭悗鍐嶄娇鐢ㄨ鍛戒护")
    try:
        await bot.delete_msg(message_id=mid)
    except Exception as e:
        logger.exception(f"鎾ゅ洖澶辫触: {e}")
        await matcher.finish("鎾ゅ洖澶辫触锛屽彲鑳芥潈闄愪笉瓒虫垨瓒呮椂")
    await matcher.finish("宸叉挙鍥?)


set_essence = P.on_regex(
    r"^#(?:璁剧疆绮惧崕|璁剧簿)$",
    name="set_essence",
    display_name="璁剧疆绮惧崕",
    priority=13,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@set_essence.handle()
async def _set_essence(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("璇峰湪缇よ亰涓娇鐢?)
    mid = get_target_message_id(event)
    if not mid:
        await matcher.finish("璇峰洖澶嶇洰鏍囨秷鎭悗鍐嶄娇鐢?)
    try:
        await bot.set_essence_msg(message_id=mid)
    except Exception as e:
        logger.exception(f"璁剧疆绮惧崕澶辫触: {e}")
        await matcher.finish("璁剧疆澶辫触锛屽彲鑳芥潈闄愪笉瓒虫垨璇ュ钩鍙颁笉鏀寔")
    await matcher.finish("宸茶缃负绮惧崕")


unset_essence = P.on_regex(
    r"^#鍙栨秷绮惧崕$",
    name="unset_essence",
    display_name="鍙栨秷绮惧崕",
    priority=13,
    block=True,
    enabled=True,
    level="admin",
    scene="group",
)


@unset_essence.handle()
async def _unset_essence(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("璇峰湪缇よ亰涓娇鐢?)
    mid = get_target_message_id(event)
    if not mid:
        await matcher.finish("璇峰洖澶嶇洰鏍囨秷鎭悗鍐嶄娇鐢?)
    try:
        await bot.delete_essence_msg(message_id=mid)
    except Exception as e:
        logger.exception(f"鍙栨秷绮惧崕澶辫触: {e}")
        await matcher.finish("鍙栨秷澶辫触锛屽彲鑳芥潈闄愪笉瓒虫垨璇ュ钩鍙颁笉鏀寔")
    await matcher.finish("宸插彇娑堢簿鍗?)


