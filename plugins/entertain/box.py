from __future__ import annotations

import base64
import textwrap
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

import aiohttp
from nonebot import on_notice
from nonebot.log import logger
from nonebot.params import RegexGroup
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupIncreaseNoticeEvent,
    GroupDecreaseNoticeEvent,
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
)

from pydantic import BaseModel, Field

from ...core.api import Plugin
from ...core.api import register_namespaced_config
from .box_draw import create_image


def _b64_image(img_bytes: bytes) -> MessageSegment:
    return MessageSegment.image(f"base64://{base64.b64encode(img_bytes).decode()}")


class Config(BaseModel):
    auto_box: bool = False
    increase_box: bool = False
    decrease_box: bool = False
    only_admin: bool = False
    auto_box_groups: List[str] = Field(default_factory=list)
    box_blacklist: List[str] = Field(default_factory=list)


CFG = register_namespaced_config("entertain", "box", defaults=Config().dict())


def _load_cfg() -> Config:
    try:
        data = CFG.load()
        return Config.parse_obj(data)
    except Exception:
        return Config()


P = Plugin(name="entertain")


box_cmd = P.on_regex(r"^(?:[/#])?(?:盒|开盒)\s*(.*)?$", name="open", block=True, priority=5)


@box_cmd.handle()
async def _(bot: Bot, event: MessageEvent, groups: tuple = RegexGroup()):
    plugin_config = _load_cfg()
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

    is_self = str(target_id) == str(getattr(event, "user_id", ""))
    if plugin_config.only_admin and not is_self:
        is_admin = False
        if isinstance(event, GroupMessageEvent):
            role = getattr(event.sender, "role", None)
            is_admin = role in {"admin", "owner"}
        if not is_admin:
            await box_cmd.finish("在群聊中仅允许自开")

    if str(target_id) in set(plugin_config.box_blacklist or []):
        await box_cmd.finish("该用户已被禁用")

    try:
        stranger_info: Dict[str, Any] = await bot.call_api(
            "get_stranger_info", user_id=int(target_id), no_cache=True
        )
    except Exception:
        await box_cmd.finish("无效QQ号")

    group_id: Optional[int] = getattr(event, "group_id", None)
    member_info: Dict[str, Any] = {}
    if group_id:
        try:
            member_info = await bot.call_api(
                "get_group_member_info", user_id=int(target_id), group_id=int(group_id)
            )
        except Exception:
            member_info = {}

    avatar: Optional[bytes] = await get_avatar(str(target_id))
    if not avatar:
        from PIL import Image

        with BytesIO() as buffer:
            Image.new("RGB", (640, 640), (255, 255, 255)).save(buffer, format="PNG")
            avatar = buffer.getvalue()

    reply_lines = transform(stranger_info, member_info)
    img_bytes = create_image(avatar, reply_lines)
    await box_cmd.finish(_b64_image(img_bytes))


_group_increase = on_notice(priority=50, permission=P.permission())


@_group_increase.handle()
async def _(bot: Bot, event: GroupIncreaseNoticeEvent):
    plugin_config = _load_cfg()
    effective_increase = bool(getattr(plugin_config, "increase_box", False) or getattr(plugin_config, "auto_box", False))
    if not effective_increase:
        return
    group_id = str(event.group_id)
    if plugin_config.auto_box_groups and group_id not in plugin_config.auto_box_groups:
        return
    user_id = str(event.user_id)
    if user_id == str(event.self_id):
        return
    if user_id in (plugin_config.box_blacklist or []):
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
    await _group_increase.finish(_b64_image(img_bytes))


_group_decrease = on_notice(priority=50, permission=P.permission())


@_group_decrease.handle()
async def _(bot: Bot, event: GroupDecreaseNoticeEvent):
    plugin_config = _load_cfg()
    if not getattr(plugin_config, "decrease_box", False):
        return
    try:
        sub_type = getattr(event, "sub_type", None)
    except Exception:
        sub_type = None
    if sub_type != "leave":
        return
    group_id = str(event.group_id)
    if plugin_config.auto_box_groups and group_id not in plugin_config.auto_box_groups:
        return
    user_id = str(event.user_id)
    if user_id == str(event.self_id):
        return
    if user_id in (plugin_config.box_blacklist or []):
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
    await _group_decrease.finish(_b64_image(img_bytes))


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
    reply: List[str] = []

    if user_id := info.get("user_id") or info2.get("user_id"):
        reply.append(f"QQ：{user_id}")

    if nickname := info.get("nickname") or info2.get("nickname"):
        reply.append(f"昵称：{nickname}")

    card = (info2.get("card") or "").strip()
    if card:
        reply.append(f"群昵称：{card}")

    title = (info2.get("title") or "").strip()
    if title:
        reply.append(f"头衔：{title}")

    sex = info.get("sex") or info2.get("sex")
    if sex == "male":
        reply.append("性别：男生")
    elif sex == "female":
        reply.append("性别：女生")

    if (info.get("birthday_year") and info.get("birthday_month") and info.get("birthday_day")):
        try:
            by, bm, bd = int(info["birthday_year"]), int(info["birthday_month"]), int(info["birthday_day"])
            reply.append(f"生日：{by}-{bm}-{bd}")
            reply.append(f"星座：{get_constellation(bm, bd)}")
            reply.append(f"生肖：{get_zodiac(by, bm, bd)}")
        except Exception:
            pass

    if (age := info.get("age")):
        try:
            age_i = int(age)
            if age_i > 0:
                reply.append(f"年龄：{age_i}岁")
        except Exception:
            pass

    if (phoneNum := info.get("phoneNum")) and phoneNum != "-":
        reply.append(f"电话：{phoneNum}")

    if (eMail := info.get("eMail")) and eMail != "-":
        reply.append(f"邮箱：{eMail}")

    if (postCode := info.get("postCode")) and postCode != "-":
        reply.append(f"邮编：{postCode}")

    country = info.get("country")
    province = info.get("province")
    city = info.get("city")
    if country == "中国" and (province or city):
        reply.append(f"籍贯：{province or ''}-{city or ''}")
    elif country:
        reply.append(f"籍贯：{country}")

    if (homeTown := info.get("homeTown")) and homeTown != "0-0-0":
        reply.append(f"家乡：{parse_home_town(homeTown)}")

    if (address := info.get("address")) and address != "-":
        reply.append(f"地址：{address}")

    if (kBloodType := info.get("kBloodType")):
        try:
            reply.append(f"血型：{get_blood_type(int(kBloodType))}")
        except Exception:
            pass

    makeFriendCareer = info.get("makeFriendCareer")
    if makeFriendCareer and makeFriendCareer != "0":
        try:
            reply.append(f"职业：{get_career(int(makeFriendCareer))}")
        except Exception:
            pass

    if remark := info.get("remark"):
        reply.append(f"备注：{remark}")

    if labels := info.get("labels"):
        reply.append(f"标签：{labels}")

    if info2.get("unfriendly"):
        reply.append("是否拉黑：是")

    if info2.get("is_robot"):
        reply.append("是否为bot: 是")

    if info.get("is_vip"):
        reply.append("VIP：是")

    if info.get("is_years_vip"):
        reply.append("年费VIP：是")

    try:
        vip_level = int(info.get("vip_level", 0))
        if vip_level:
            reply.append(f"VIP等级：{vip_level}")
    except Exception:
        pass

    try:
        login_days = int(info.get("login_days", 0))
        if login_days:
            reply.append(f"已连续登录天数：{login_days}")
    except Exception:
        pass

    try:
        level = int(info.get("level", 0))
        if level:
            reply.append(f"等级：{qqLevel_to_icon(level)}")
    except Exception:
        pass

    if (uin := info.get("uin")) and (qzone_name := info.get("qzone_name")):
        reply.append(f"QQ空间：{qzone_name}（{uin}）")

    if (join_ts := info2.get("join_time")):
        jt = _fmt_date(join_ts)
        if jt:
            reply.append(f"入群日期：{jt}")

    if (last := info2.get("last_sent_time")):
        dt = _fmt_date(last)
        if dt:
            reply.append(f"最后发言：{dt}")

    if (honor := info2.get("title_expire_time")):
        dt = _fmt_date(honor)
        if dt:
            reply.append(f"荣誉过期：{dt}")

    if (sh := info2.get("shut_up_timestamp")):
        dt = _fmt_date(sh)
        if dt:
            reply.append(f"禁言到期：{dt}")

    if long_nick := info.get("long_nick"):
        lines = textwrap.wrap(text="签名：" + str(long_nick), width=15)
        reply.extend(lines)

    if not reply:
        reply.append("未获取到可展示信息")

    return reply


def qqLevel_to_icon(level: int) -> str:
    icons = ["🟨", "🟧", "🟥", "🟦"]
    levels = [64, 16, 4, 1]
    result = ""
    original_level = level
    for icon, lvl in zip(icons, levels):
        count, level = divmod(level, lvl)
        result += icon * count
    result += f"({original_level})"
    return result


def get_constellation(month: int, day: int) -> str:
    constellations = {
        "白羊座": ((3, 21), (4, 19)),
        "金牛座": ((4, 20), (5, 20)),
        "双子座": ((5, 21), (6, 20)),
        "巨蟹座": ((6, 21), (7, 22)),
        "狮子座": ((7, 23), (8, 22)),
        "处女座": ((8, 23), (9, 22)),
        "天秤座": ((9, 23), (10, 22)),
        "天蝎座": ((10, 23), (11, 21)),
        "射手座": ((11, 22), (12, 21)),
        "摩羯座": ((12, 22), (1, 19)),
        "水瓶座": ((1, 20), (2, 18)),
        "双鱼座": ((2, 19), (3, 20)),
    }

    for constellation, ((start_month, start_day), (end_month, end_day)) in constellations.items():
        if (month == start_month and day >= start_day) or (month == end_month and day <= end_day):
            return constellation
        if start_month > end_month:
            if (month == start_month and day >= start_day) or (month == end_month + 12 and day <= end_day):
                return constellation
    return f"{month}-{day}"


def get_zodiac(year: int, month: int, day: int) -> str:
    base_year = 2024
    zodiacs = [
        "鼠🐭",
        "牛🐮",
        "虎🐯",
        "兔🐰",
        "龙🐲",
        "蛇🐍",
        "马🐴",
        "羊🐑",
        "猴🐵",
        "鸡🐔",
        "狗🐶",
        "猪🐷",
    ]
    zodiac_year = year - 1 if (month == 1) or (month == 2 and day < 4) else year
    zodiac_index = (zodiac_year - base_year) % 12
    return zodiacs[zodiac_index]


def get_career(num: int) -> str:
    career = {
        1: "物流/运营/交通",
        2: "法律/金融/财会",
        3: "医疗/护理/药剂",
        4: "制造/工程/投资/金融",
        5: "创业/个体/或营运",
        6: "文化/媒体/新媒",
        7: "互联网/软件/游戏",
        8: "教师/教育",
        9: "健身/训练",
        10: "公务员/事业/国企岗位",
        11: "模特",
        12: "军人",
        13: "学生",
        14: "其他职业",
    }
    return career.get(num, f"职业{num}")


def get_blood_type(num: int) -> str:
    blood_types = {1: "A型", 2: "B型", 3: "O型", 4: "AB型", 5: "稀有血型"}
    return blood_types.get(num, f"血型{num}")


def parse_home_town(home_town_code: str) -> str:
    country_map = {"49": "中国", "250": "俄罗斯", "222": "法国", "217": "德国"}
    province_map = {
        "98": "北京",
        "99": "天津/河北",
        "100": "山西/内蒙",
        "101": "辽宁/吉林/黑龙江",
        "102": "上海/江苏/浙江",
        "103": "安徽/福建/江西",
        "104": "山东/河南/台湾",
        "105": "湖北/湖南/广东",
        "106": "广西/海南/四川/贵州",
        "107": "新疆",
    }

    parts = str(home_town_code).split("-")
    if len(parts) != 3:
        return str(home_town_code)
    country_code, province_code, _ = parts
    country = country_map.get(country_code, f"国家{country_code}")

    if country_code == "49":
        if province_code != "0":
            province = province_map.get(province_code, f"{province_code}省")
            return province
        else:
            return country
    else:
        return country
