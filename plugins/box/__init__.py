from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

import aiohttp
from nonebot import on_notice
from nonebot.log import logger
from nonebot.params import RegexGroup
from nonebot.plugin import PluginMetadata

from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)

from ...registry import Plugin
from .config import plugin_config
from .draw import create_image


__plugin_meta__ = PluginMetadata(
    name="开箱（NoneBot2）",
    description="获取 QQ 用户/群成员资料并生成图片",
    usage="命令：箱 [@某人] 或 <QQ>（支持前缀 #/）",
    type="application",
    homepage="https://github.com/Zhalslar/astrbot_plugin_box",
)


def _b64_image(img_bytes: bytes) -> MessageSegment:
    return MessageSegment.image(f"base64://{base64.b64encode(img_bytes).decode()}")


P = Plugin()

# 触发：箱 [@某人]|<QQ>
box_cmd = P.on_regex(
    r"^(?:[/#])?箱\s*(.*)?$",
    name="open",
    block=True,
    priority=5,
)


@box_cmd.handle()
async def _(bot: Bot, event: MessageEvent, groups: tuple = RegexGroup()):
    # 解析目标：@优先，其次参数数字，否则默认自己
    target_id: Optional[str] = None
    try:
        for seg in event.message:  # type: ignore[attr-defined]
            if seg.type == "at":
                qq = seg.data.get("qq")
                if qq and qq != "all":
                    target_id = str(qq)
                    break
    except Exception:
        pass

    try:
        arg = (groups[0] or "").strip() if groups else ""
    except Exception:
        arg = ""
    if not target_id and arg and arg.isdigit():
        target_id = arg
    if not target_id:
        target_id = str(getattr(event, "user_id", ""))

    # 仅群管理可为他人开箱（当配置 only_admin 启用时）
    is_self = str(target_id) == str(getattr(event, "user_id", ""))
    if plugin_config.only_admin and not is_self:
        is_admin = False
        if isinstance(event, GroupMessageEvent):
            role = getattr(event.sender, "role", None)
            is_admin = role in {"admin", "owner"}
        if not is_admin:
            await box_cmd.finish("仅群管理可为他人开箱")

    # 拉取资料
    try:
        stranger_info: Dict[str, Any] = await bot.call_api(
            "get_stranger_info", user_id=int(target_id), no_cache=True
        )
    except Exception:
        await box_cmd.finish("无效QQ 或接口不可用")

    group_id: Optional[int] = getattr(event, "group_id", None)
    member_info: Dict[str, Any] = {}
    if group_id:
        try:
            member_info = await bot.call_api(
                "get_group_member_info", user_id=int(target_id), group_id=int(group_id)
            )
        except Exception:
            member_info = {}

    # 头像
    avatar: Optional[bytes] = await get_avatar(str(target_id))
    if not avatar:
        from PIL import Image

        with BytesIO() as buffer:
            Image.new("RGB", (640, 640), (255, 255, 255)).save(buffer, format="PNG")
            avatar = buffer.getvalue()

    reply_lines = transform(stranger_info, member_info)
    img_bytes = create_image(avatar, reply_lines)
    await box_cmd.finish(_b64_image(img_bytes))


group_increase = on_notice(priority=50)


@group_increase.handle()
async def _(bot: Bot, event: GroupIncreaseNoticeEvent):
    if not plugin_config.auto_box:
        return
    group_id = str(event.group_id)
    if plugin_config.auto_box_groups and group_id not in plugin_config.auto_box_groups:
        return
    user_id = str(event.user_id)
    if user_id == str(event.self_id):
        return
    if user_id in plugin_config.box_blacklist:
        return
    try:
        stranger_info = await bot.call_api("get_stranger_info", user_id=int(user_id), no_cache=True)
    except Exception:
        return
    try:
        member_info = await bot.call_api(
            "get_group_member_info", user_id=int(user_id), group_id=int(event.group_id)
        )
    except Exception:
        member_info = {}
    avatar: Optional[bytes] = await get_avatar(user_id)
    if not avatar:
        from PIL import Image

        with BytesIO() as buffer:
            Image.new("RGB", (640, 640), (255, 255, 255)).save(buffer, format="PNG")
            avatar = buffer.getvalue()
    reply_lines = transform(stranger_info, member_info)
    img_bytes = create_image(avatar, reply_lines)
    await group_increase.finish(_b64_image(img_bytes))


async def get_avatar(user_id: str) -> Optional[bytes]:
    avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url, timeout=10) as resp:
                resp.raise_for_status()
                return await resp.read()
    except Exception as e:
        logger.warning(f"获取头像失败: {e}")
        return None


def _fmt_date(ts: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        return None


def transform(info: Dict[str, Any], info2: Dict[str, Any]) -> List[str]:
    """将用户/群成员信息转换为渲染文本行，健壮处理缺失字段。"""
    reply: List[str] = []
    user_id = info.get("user_id") or info2.get("user_id")
    if user_id:
        reply.append(f"QQ：{user_id}")
    nickname = info.get("nickname") or info2.get("nickname")
    if nickname:
        reply.append(f"昵称：{nickname}")
    card = (info2.get("card") or "").strip()
    if card:
        reply.append(f"群昵称：{card}")
    title = (info2.get("title") or "").strip()
    if title:
        reply.append(f"头衔：{title}")
    sex = (info.get("sex") or info2.get("sex") or "").lower()
    if sex in ("male", "female", "unknown"):
        sex_txt = {"male": "男", "female": "女"}.get(sex, "未知")
        reply.append(f"性别：{sex_txt}")
    age = info.get("age") or info2.get("age")
    if isinstance(age, int) and age > 0:
        reply.append(f"年龄：{age}")
    area = info2.get("area") or info.get("area")
    if isinstance(area, str) and area.strip():
        reply.append(f"地区：{area}")
    join_time = info2.get("join_time")
    if join_time and (d := _fmt_date(join_time)):
        reply.append(f"入群时间：{d}")
    level = info2.get("level")
    if level is not None and str(level).strip():
        reply.append(f"群等级：{level}")
    qsign = info.get("qsign") or info.get("long_nick")
    if isinstance(qsign, str) and qsign.strip():
        reply.append("签名：" + qsign.strip())
    if not reply:
        reply.append("未获取到任何可展示信息")
    return reply
