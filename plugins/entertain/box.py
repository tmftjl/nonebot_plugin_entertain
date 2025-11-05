from __future__ import annotations

import textwrap
from datetime import datetime
from io import BytesIO
from typing import Optional, Tuple

import httpx
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup

from ...core.api import Plugin
from .config import cfg_box
from ...core.constants import DEFAULT_HTTP_TIMEOUT
from ...core.http import get_shared_async_client

from PIL import Image

from nonebot.adapters.onebot.v11 import (
        Bot,
        Message,
        MessageEvent,
        GroupMessageEvent,
        GroupIncreaseNoticeEvent,
        GroupDecreaseNoticeEvent,
        MessageSegment,
    )

from .box_draw import create_image


P = Plugin(name="entertain", display_name="娱乐")

# Persist defaults on first load and provide a safe getter
def _cfg_get(key: str, default=None):
    try:
        return cfg_box().get(key, default)
    except Exception:
        return default

# Initialize to persist defaults on startup
try:
    _ = cfg_box()
except Exception:
    pass


box_matcher = P.on_regex(
    r"^(?:#|/)(?:盒|开盒)\s*(.*?)$",
    name="box",
    display_name="开盒",
    priority=5,
    block=True,
)

@box_matcher.handle()
async def _handle_box(
    matcher: Matcher,
    bot: Bot,
    event: MessageEvent,
    groups: Tuple[Optional[str]] = RegexGroup(),
) -> None:
    # Determine target
    self_id = str(getattr(bot, "self_id", ""))
    target_id: Optional[str] = None
    group_id: Optional[str] = None

    # from @ mention (prefer)
    try:
        for seg in getattr(event, "message", []) or []:
            if getattr(seg, "type", "") == "at":
                qq = str(getattr(seg, "data", {}).get("qq") or "")
                if qq and qq != self_id:
                    target_id = qq
                    break
    except Exception:
        pass

    # from numeric arg (support multiple capture groups; take the first non-empty)
    if not target_id and groups:
        maybe_qq = next((g for g in groups if g), None)
        if maybe_qq and str(maybe_qq) != self_id:
            target_id = str(maybe_qq)

    # fallback to sender
    if not target_id:
        target_id = str(getattr(event, "user_id", "")) or getattr(event, "get_user_id", lambda: "")()

    # get group id when applicable
    if isinstance(event, GroupMessageEvent):
        group_id = str(event.group_id)

    # only-admin restriction
    if _cfg_get("only_admin") and isinstance(event, GroupMessageEvent):
        try:
            mem = await bot.get_group_member_info(group_id=int(event.group_id), user_id=int(event.user_id))
            if str(mem.get("role")) not in {"owner", "admin"}:
                await matcher.finish("仅限管理员可用")
                return
        except Exception:
            await matcher.finish("仅限管理员可用")
            return

    # blacklist
    try:
        bl = _cfg_get("box_blacklist", [])
        if str(target_id) in {str(x) for x in (bl or [])}:
            await matcher.finish("该用户无法被开盒")
            return
    except Exception:
        pass
    
    try:
        if str(target_id) in {str(x) for x in (_cfg_get("box_blacklist", []) or [])}:
            await matcher.finish("该用户无法被开盒")
            return
    except Exception:
        pass

    msg = await _do_box(bot, target_id=target_id, group_id=group_id)
    await matcher.finish(msg)


async def _do_box(bot: Bot, *, target_id: str, group_id: Optional[str]) -> Message:
    # get stranger info
    try:
        stranger_info = await bot.get_stranger_info(user_id=int(target_id), no_cache=True)  # type: ignore[arg-type]
    except Exception:
        return Message(MessageSegment.text("无效QQ号"))

    # member info if in group
    member_info = {}
    if group_id:
        try:
            member_info = await bot.get_group_member_info(user_id=int(target_id), group_id=int(group_id))  # type: ignore[arg-type]
        except Exception:
            member_info = {}

    # avatar
    avatar: Optional[bytes] = await _get_avatar_bytes(target_id)
    if not avatar:
        # fallback to white square
        buf = BytesIO()
        Image.new("RGB", (640, 640), (255, 255, 255)).save(buf, format="PNG")  # type: ignore[name-defined]
        avatar = buf.getvalue()

    reply_lines = _transform_info(stranger_info, member_info)
    img_bytes = create_image(avatar, reply_lines)
    import base64

    b64 = base64.b64encode(img_bytes).decode()
    return Message(MessageSegment.image(f"base64://{b64}"))


async def _get_avatar_bytes(user_id: str) -> Optional[bytes]:
    cfg = cfg_box()
    url_template = str(cfg.get("avatar_api_url"))
    url = url_template.format(user_id=user_id)

    try:
        client = await get_shared_async_client()
        r = await client.get(url, timeout=DEFAULT_HTTP_TIMEOUT)
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.warning(f"下载头像失败: {e}")
        return None


def _transform_info(info: dict, info2: dict) -> list[str]:
    reply: list[str] = []

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
        reply.append("性别：男孩纸")
    elif sex == "female":
        reply.append("性别：女孩纸")

    by, bm, bd = info.get("birthday_year"), info.get("birthday_month"), info.get("birthday_day")
    if by and bm and bd:
        reply.append(f"诞辰：{by}-{bm}-{bd}")
        reply.append(f"星座：{_get_constellation(int(bm), int(bd))}")
        reply.append(f"生肖：{_get_zodiac(int(by), int(bm), int(bd))}")

    if age := info.get("age"):
        reply.append(f"年龄：{age}岁")

    if phoneNum := info.get("phoneNum"):
        if phoneNum != "-":
            reply.append(f"电话：{phoneNum}")

    if eMail := info.get("eMail"):
        if eMail != "-":
            reply.append(f"邮箱：{eMail}")

    if postCode := info.get("postCode"):
        if postCode != "-":
            reply.append(f"邮编：{postCode}")

    country = info.get("country")
    province = info.get("province")
    city = info.get("city")
    if country == "中国" and (province or city):
        reply.append(f"现居：{province or ''}-{city or ''}")
    elif country:
        reply.append(f"现居：{country}")

    if homeTown := info.get("homeTown"):
        if homeTown != "0-0-0":
            reply.append(f"来自：{_parse_home_town(homeTown)}")

    if address := info.get("address"):
        if address != "-":
            reply.append(f"地址：{address}")

    if kBloodType := info.get("kBloodType"):
        try:
            reply.append(f"血型：{_get_blood_type(int(kBloodType))}")
        except Exception:
            pass

    if (makeFriendCareer := info.get("makeFriendCareer")) and makeFriendCareer != "0":
        try:
            reply.append(f"职业：{_get_career(int(makeFriendCareer))}")
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

    if qqLevel := info.get("qqLevel"):
        try:
            reply.append(f"QQ等级：{_qqLevel_to_icon(int(qqLevel))}")
        except Exception:
            pass

    if reg_time := info.get("reg_time"):
        try:
            reply.append(f"注册时间：{datetime.fromtimestamp(int(reg_time)).strftime('%Y-%m-%d')}")
        except Exception:
            pass

    if long_nick := info.get("long_nick"):
        for line in textwrap.wrap(text=f"签名：{long_nick}", width=15):
            reply.append(line)

    return reply


def _qqLevel_to_icon(level: int) -> str:
    icons = ["👑", "🌞", "🌙", "⭐"]
    levels = [64, 16, 4, 1]
    result = ""
    original_level = level
    for icon, lvl in zip(icons, levels):
        count, level = divmod(level, lvl)
        result += icon * count
    result += f"({original_level})"
    return result


def _get_constellation(month: int, day: int) -> str:
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
    for name, ((sm, sd), (em, ed)) in constellations.items():
        if (month == sm and day >= sd) or (month == em and day <= ed):
            return name
        if sm > em:  # wrap year
            if (month == sm and day >= sd) or (month == em + 12 and day <= ed):
                return name
    return f"星座{month}-{day}"


def _get_zodiac(year: int, month: int, day: int) -> str:
    base_year = 2024  # dragon
    zodiacs = [
        "龙🐲",
        "蛇🐍",
        "马🐎",
        "羊🐑",
        "猴🐒",
        "鸡🐓",
        "狗🐕",
        "猪🐖",
        "鼠🐀",
        "牛🐂",
        "虎🐅",
        "兔🐇",
    ]
    zodiac_year = year - 1 if (month == 1) or (month == 2 and day < 4) else year
    zodiac_index = (zodiac_year - base_year) % 12
    return zodiacs[zodiac_index]


def _get_career(num: int) -> str:
    career = {
        1: "计算机/互联网/通信",
        2: "生产/工艺/制造",
        3: "医疗/护理/制药",
        4: "金融/银行/投资/保险",
        5: "商业/服务业/个体经营",
        6: "文化/广告/传媒",
        7: "娱乐/艺术/表演",
        8: "律师/法务",
        9: "教育/培训",
        10: "公务员/行政/事业单位",
        11: "模特",
        12: "空姐",
        13: "学生",
        14: "其他职业",
    }
    return career.get(num, f"职业{num}")


def _get_blood_type(num: int) -> str:
    blood_types = {1: "A型", 2: "B型", 3: "O型", 4: "AB型", 5: "其他血型"}
    return blood_types.get(num, f"血型{num}")


def _parse_home_town(home_town_code: str) -> str:
    # simplified mapping; extend if needed
    country_map = {
        "49": "中国",
        "250": "俄罗斯",
        "222": "特立尼达",
        "217": "法国",
    }
    province_map = {
        "98": "北京",
        "99": "天津/辽宁",
        "100": "河北/山西",
        "101": "内蒙古/吉林",
        "102": "黑龙江/上海",
        "103": "江苏/浙江",
        "104": "安徽/福建",
        "105": "江西/山东",
        "106": "河南/湖北/湖南",
        "107": "新疆",
    }

    try:
        country_code, province_code, _ = home_town_code.split("-")
    except Exception:
        return str(home_town_code)
    country = country_map.get(country_code, f"外国{country_code}")
    if country_code == "49":  # 中国
        if province_code != "0":
            return province_map.get(province_code, f"{province_code}省")
        else:
            return country
    else:
        return country


# ----- Auto box on join/leave notices (optional) -----
from nonebot import on_notice  # noqa: E402


_notice_increase = on_notice()


@_notice_increase.handle()
async def _on_increase(bot: Bot, event: GroupIncreaseNoticeEvent):  # type: ignore[valid-type]
    try:
        if not _cfg_get("increase_box"):
            return
        group_id = str(event.group_id)
        if _cfg_get("auto_box_groups"):
            if str(group_id) not in {str(g) for g in _cfg_get("auto_box_groups", [])}:
                return
        user_id = str(event.user_id)
        msg = await _do_box(bot, target_id=user_id, group_id=group_id)
    except Exception:
        # do not block other notice handlers
        return
    await _notice_increase.finish(msg)
