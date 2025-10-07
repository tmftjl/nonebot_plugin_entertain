from __future__ import annotations

import base64
import textwrap
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional
import traceback
import aiohttp
from nonebot import on_regex, on_notice
from nonebot.plugin import PluginMetadata
from nonebot.log import logger
from nonebot.params import RegexGroup

from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageEvent,
    GroupMessageEvent,
    GroupIncreaseNoticeEvent,
    MessageSegment,
)

from ...perm import permission_for
from .config import plugin_config
from .draw import create_image


__plugin_meta__ = PluginMetadata(
    name="开盒（NoneBot2）",
    description="获取 QQ 与群资料并生成图片",
    usage="指令：盒 [@某人] 或 盒 <QQ>；支持前缀 #/",
    type="application",
    homepage="https://github.com/Zhalslar/astrbot_plugin_box",
)


def _b64_image(img_bytes: bytes) -> MessageSegment:
    return MessageSegment.image(f"base64://{base64.b64encode(img_bytes).decode()}")


box_cmd = on_regex(r"^(?:(/|#))?盒\s*(.*)?$", block=True, priority=5, permission=permission_for("box"))


@box_cmd.handle()
async def _(bot: Bot, event: MessageEvent, groups: tuple = RegexGroup()):
    target_id: Optional[str] = None

    # @ 优先
    try:
        for seg in event.message:  # type: ignore[attr-defined]
            if seg.type == "at":
                qq = seg.data.get("qq")
                if qq and qq != "all":
                    target_id = str(qq)
                    break
    except Exception:
        pass

    # 解析纯数字参数
    if not target_id:
        try:
            arg = (groups[1] or "").strip() if groups else ""
        except Exception:
            arg = ""
        if arg and arg.isdigit():
            target_id = arg

    # 默认取自己
    if not target_id:
        target_id = str(getattr(event, "user_id", ""))

    # 仅管理员可开他人（如配置）
    if plugin_config.only_admin:
        is_self = str(target_id) == str(getattr(event, "user_id", ""))
        if not is_self:
            is_admin = False
            if isinstance(event, GroupMessageEvent):
                role = getattr(event.sender, "role", None)
                is_admin = role in {"admin", "owner"}
            if not is_admin:
                await box_cmd.finish("仅管理员可开盒他人")

    # 黑名单拦截
    if target_id in plugin_config.box_blacklist:
        await box_cmd.finish("该用户无法被开盒")

    # 拉取资料
    try:
        stranger_info: Dict[str, Any] = await bot.call_api("get_stranger_info", user_id=int(target_id), no_cache=True)
    except Exception:
        await box_cmd.finish("无效QQ")
    group_id: Optional[int] = getattr(event, "group_id", None)
    member_info: Dict[str, Any] = {}
    if group_id:
        try:
            member_info = await bot.call_api("get_group_member_info", user_id=int(target_id), group_id=int(group_id))
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
        member_info = await bot.call_api("get_group_member_info", user_id=int(user_id), group_id=int(event.group_id))
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
            async with session.get(avatar_url) as resp:
                resp.raise_for_status()
                return await resp.read()
    except Exception as e:
        logger.warning(f"下载头像失败: {e}")
        return None


def transform(info: Dict[str, Any], info2: Dict[str, Any]) -> List[str]:
    reply: List[str] = []
    if user_id := info.get("user_id"):
        reply.append(f"QQ号：{user_id}")
    if nickname := info.get("nickname"):
        reply.append(f"昵称：{nickname}")
    if card := info2.get("card"):
        reply.append(f"群昵称：{card}")
    if title := info2.get("title"):
        reply.append(f"头衔：{title}")
    sex = info.get("sex")
    if sex == "male":
        reply.append("性别：男")
    elif sex == "female":
        reply.append("性别：女")
    if info.get("birthday_year") and info.get("birthday_month") and info.get("birthday_day"):
        by, bm, bd = int(info["birthday_year"]), int(info["birthday_month"]), int(info["birthday_day"])
        reply.append(f"诞辰：{by}-{bm}-{bd}")
        reply.append(f"星座：{get_constellation(bm, bd)}")
        reply.append(f"生肖：{get_zodiac(by, bm, bd)}")
    if age := info.get("age"):
        reply.append(f"年龄：{age}")
    if phone := info.get("phoneNum"):
        if phone != "-":
            reply.append(f"电话：{phone}")
    if email := info.get("eMail"):
        if email != "-":
            reply.append(f"邮箱：{email}")
    location = []
    if (country := info.get("country")):
        location.append("" if country == "中国" else country)
    if province := info.get("province"):
        location.append(province)
    if city := info.get("city"):
        location.append(city)
    if any(location):
        reply.append("现居地：" + "-".join(filter(None, location)))
    if home_town := info.get("homeTown"):
        if home_town != "0-0-0":
            reply.append(f"来自：{parse_home_town(home_town)}")
    if address := info.get("address"):
        if address != "-":
            reply.append(f"地址：{address}")
    if k_blood := info.get("kBloodType"):
        try:
            reply.append(f"血型：{get_blood_type(int(k_blood))}")
        except Exception:
            pass
    if career := info.get("makeFriendCareer"):
        if career != "0":
            try:
                reply.append(f"职业：{get_career(int(career))}")
            except Exception:
                pass
    if remark := info.get("remark"):
        reply.append(f"备注：{remark}")
    if labels := info.get("labels"):
        reply.append(f"标签：{labels}")
    if info2.get("unfriendly"):
        reply.append("不良记录：有")
    if info2.get("is_robot"):
        reply.append("是否为bot：是")
    if info.get("is_vip"):
        reply.append("VIP：已开")
    if info.get("is_years_vip"):
        reply.append("年费VIP：已开")
    if int(info.get("vip_level", 0)) != 0:
        reply.append(f"VIP等级：{info['vip_level']}")
    if int(info.get("login_days", 0)) != 0:
        reply.append(f"连续登录天数：{info['login_days']}")
    if level := info2.get("level"):
        try:
            reply.append(f"群等级：{int(level)}级")
        except Exception:
            pass
    if join_time := info2.get("join_time"):
        try:
            reply.append(f"加群时间：{datetime.fromtimestamp(int(join_time)).strftime('%Y-%m-%d')}")
        except Exception:
            pass
    if qq_level := info.get("qqLevel"):
        try:
            reply.append(f"QQ等级：{qq_level_to_icon(int(qq_level))}")
        except Exception:
            pass
    if reg_time := info.get("reg_time"):
        try:
            reply.append(f"注册时间：{datetime.fromtimestamp(int(reg_time)).strftime('%Y-%m-%d')}")
        except Exception:
            pass
    if long_nick := info.get("long_nick"):
        lines = textwrap.wrap(text="签名：" + str(long_nick), width=15)
        reply.extend(lines)
    return reply


def qq_level_icon_list() -> List[str]:
    return ["👑", "🌞", "🌙", "⭐"]


def qq_level_to_icon(level: int) -> str:
    icons = qq_level_icon_list()
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
    for constellation, ((sm, sd), (em, ed)) in constellations.items():
        if (month == sm and day >= sd) or (month == em and day <= ed):
            return constellation
        if sm > em:
            if (month == sm and day >= sd) or (month == em + 12 and day <= ed):
                return constellation
    return f"星座{month}-{day}"


def get_zodiac(year: int, month: int, day: int) -> str:
    base_year = 2024  # 龙年基准
    zodiacs = ["龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪", "鼠", "牛", "虎", "兔"]
    zodiac_year = year - 1 if (month == 1) or (month == 2 and day < 4) else year
    zodiac_index = (zodiac_year - base_year) % 12
    return zodiacs[zodiac_index]


def get_career(num: int) -> str:
    career = {
        1: "计算机/互联网/通信",
        2: "生产/工艺/制造",
        3: "医疗/护理/制药",
        4: "金融/银行/投资/保险",
        5: "商业/服务/个体经营",
        6: "文化/广告/传媒",
        7: "娱乐/艺术/表演",
        8: "律师/法务",
        9: "教育/培训",
        10: "公务员/行政/事业单位",
        11: "模特",
        12: "空乘",
        13: "学生",
        14: "其他职业",
    }
    return career.get(num, f"职业{num}")


def get_blood_type(num: int) -> str:
    blood_types = {1: "A", 2: "B", 3: "O", 4: "AB", 5: "其他"}
    return blood_types.get(num, f"血型{num}")


def parse_home_town(home_town_code: str) -> str:
    country_map = {
        "49": "中国",
        "250": "俄罗斯",
        "222": "土耳其",
        "217": "法国",
    }
    province_map = {
        "98": "北京",
        "99": "天津",
        "100": "河北",
        "101": "山西",
        "102": "内蒙古",
        "103": "辽宁",
        "104": "吉林",
        "105": "黑龙江",
        "106": "上海",
        "107": "新疆",
    }
    try:
        country_code, province_code, _ = home_town_code.split("-")
    except Exception:
        return f"故乡{home_town_code}"
    country = country_map.get(country_code, f"外国{country_code}")
    if country_code == "49" and province_code != "0":
        return province_map.get(province_code, f"省份{province_code}")
    return country

