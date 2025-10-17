from __future__ import annotations

import re
from typing import List, Optional, Tuple

from nonebot.matcher import Matcher
from nonebot.params import RegexGroup
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageEvent,
    GroupMessageEvent,
)

from ...core.api import Plugin
from .utils import extract_at_or_id


P = Plugin()


quit_group = P.on_regex(
    r"^#?退群(\d+)?$",
    name="quit_group",
    display_name="退群",
    priority=13,
    block=True,
    enabled=True,
    level="superuser",
    scene="all",
)


@quit_group.handle()
async def _quit_group(matcher: Matcher, bot: Bot, event: MessageEvent):
    text = event.get_plaintext().strip()
    m = re.match(r"^#?退群(\d+)?$", text)
    assert m
    gid_str = m.group(1)

    gid: Optional[int] = None
    if gid_str:
        try:
            gid = int(gid_str)
        except Exception:
            await matcher.finish("群号不合法")
    else:
        if isinstance(event, GroupMessageEvent):
            gid = int(event.group_id)
        else:
            await matcher.finish("请提供群号：#退群123456789")

    try:
        if isinstance(event, GroupMessageEvent) and (gid == event.group_id):
            try:
                await bot.send_group_msg(group_id=gid, message=Message("3秒后将退出本群聊"))
            except Exception:
                pass
        await bot.set_group_leave(group_id=gid, is_dismiss=False)
        await matcher.finish("已退出群聊")
    except Exception as e:
        logger.exception(f"退群失败: {e}")
        await matcher.finish("退群失败，可能没有该群或权限不足")


set_group_card = P.on_regex(
    r"^#?改群名片(?:\s+(\d+))?(?:\s+(.+))?$",
    name="set_group_card",
    display_name="改群名片",
    priority=13,
    block=True,
    enabled=True,
    level="admin",
    scene="all",
)


@set_group_card.handle()
async def _set_group_card(matcher: Matcher, bot: Bot, event: MessageEvent, groups: Tuple = RegexGroup()):
    at_uid = extract_at_or_id(event.message) or int(getattr(event, "self_id"))

    gid_text = (groups[0] or "").strip() if groups and len(groups) >= 1 else ""
    card_text = (groups[1] or "").strip() if groups and len(groups) >= 2 else ""

    gid: Optional[int] = None
    if isinstance(event, GroupMessageEvent) and not gid_text:
        gid = int(event.group_id)
    else:
        if not gid_text:
            await matcher.finish("请提供群号与名片，例如：#改群名片 123456789 新名片")
        try:
            gid = int(gid_text)
        except Exception:
            await matcher.finish("群号不合法")

    if not card_text:
        await matcher.finish("请提供要设置的群名片")

    try:
        await bot.set_group_card(group_id=gid, user_id=at_uid, card=card_text)
        await matcher.finish("群名片修改成功")
    except Exception as e:
        logger.exception(f"改群名片失败: {e}")
        await matcher.finish("群名片修改失败，可能权限不足或该成员不存在")


set_group_name = P.on_regex(
    r"^#?改群(?:昵|名)称?(?:\s+(\d+))?\s+(.+)$",
    name="set_group_name",
    display_name="改群名称",
    priority=13,
    block=True,
    enabled=True,
    level="admin",
    scene="all",
)


@set_group_name.handle()
async def _set_group_name(matcher: Matcher, bot: Bot, event: MessageEvent, groups: Tuple = RegexGroup()):
    gid_text = (groups[0] or "").strip() if groups and len(groups) >= 1 else ""
    name_text = (groups[1] or "").strip() if groups and len(groups) >= 2 else ""

    gid: Optional[int] = None
    if isinstance(event, GroupMessageEvent) and not gid_text:
        gid = int(event.group_id)
    else:
        if not gid_text:
            await matcher.finish("请提供群号与新名称，例如：#改群名 123456789 新名称")
        try:
            gid = int(gid_text)
        except Exception:
            await matcher.finish("群号不合法")

    if not name_text:
        await matcher.finish("请提供要设置的群名称")

    try:
        await bot.set_group_name(group_id=gid, group_name=name_text)
        await matcher.finish("群名称修改成功")
    except Exception as e:
        logger.exception(f"改群名称失败: {e}")
        await matcher.finish("群名称修改失败，可能权限不足或群不存在")


group_list = P.on_regex(
    r"^#?(?:获取)?群列表$",
    name="group_list",
    display_name="群列表",
    priority=13,
    block=True,
    enabled=True,
    level="superuser",
    scene="all",
)


@group_list.handle()
async def _group_list(matcher: Matcher, bot: Bot):
    try:
        data = await bot.get_group_list()
    except Exception as e:
        logger.exception(f"获取群列表失败: {e}")
        await matcher.finish("获取群列表失败")
        return

    try:
        groups: List[dict] = list(data) if isinstance(data, list) else []
    except Exception:
        groups = []

    if not groups:
        await matcher.finish("暂未加入任何群")

    lines = ["群列表如下："]
    for idx, g in enumerate(groups, start=1):
        name = str(g.get("group_name", ""))
        gid = str(g.get("group_id", ""))
        lines.append(f"{idx}. {name} ({gid})")
    lines.append("示例：#发群列表 1,2 测试消息")
    await matcher.finish("\n".join(lines))


send_group_from_list = P.on_regex(
    r"^#?发群列表\s+(\S+)\s+(.+)$",
    name="send_group_from_list",
    display_name="发群列表",
    priority=13,
    block=True,
    enabled=True,
    level="superuser",
    scene="all",
)


@send_group_from_list.handle()
async def _send_group_from_list(matcher: Matcher, bot: Bot, groups: Tuple = RegexGroup()):
    index_text = (groups[0] or "").strip()
    content = (groups[1] or "").strip()
    if not index_text:
        await matcher.finish("请提供要发送的群序号，例如：#发群列表 1,3 测试")
    try:
        gl = await bot.get_group_list()
        group_list: List[dict] = list(gl) if isinstance(gl, list) else []
    except Exception as e:
        logger.exception(f"获取群列表失败: {e}")
        await matcher.finish("获取群列表失败")
        return

    if not group_list:
        await matcher.finish("暂无可用群")

    idx_parts = (
        index_text.replace("，", ",").replace(" ", ",").split(",")
    )
    idx_nums: List[int] = []
    for s in idx_parts:
        s = s.strip()
        if not s:
            continue
        if not s.isdigit():
            await matcher.finish("序号必须为数字，多个用逗号分隔")
        idx_nums.append(int(s))

    if not idx_nums:
        await matcher.finish("未提供合法序号")
    if len(idx_nums) > 3:
        await matcher.finish("一次最多向3个群发送以避免风控")

    gids: List[int] = []
    for n in idx_nums:
        if n <= 0 or n > len(group_list):
            await matcher.finish("序号超出范围")
        gids.append(int(group_list[n - 1].get("group_id")))

    sent = 0
    for gid in gids:
        try:
            await bot.send_group_msg(group_id=gid, message=Message(content))
            sent += 1
        except Exception as e:
            logger.debug(f"向群 {gid} 发送失败: {e}")
            continue

    await matcher.finish(f"已成功发送到 {sent}/{len(gids)} 个群")

