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


P = Plugin(name="entertain", display_name="濞变箰")

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
    r"^(?:#|/)(?:鐩抾寮€鐩?\s*(.*?)$",
    name="box",
    display_name="寮€鐩?,
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
                await matcher.finish("浠呴檺绠＄悊鍛樺彲鐢?)
                return
        except Exception:
            await matcher.finish("浠呴檺绠＄悊鍛樺彲鐢?)
            return

    # blacklist
    try:
        bl = _cfg_get("box_blacklist", [])
        if str(target_id) in {str(x) for x in (bl or [])}:
            await matcher.finish("璇ョ敤鎴锋棤娉曡寮€鐩?)
            return
    except Exception:
        pass
    
    try:
        if str(target_id) in {str(x) for x in (_cfg_get("box_blacklist", []) or [])}:
            await matcher.finish("璇ョ敤鎴锋棤娉曡寮€鐩?)
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
        return Message(MessageSegment.text("鏃犳晥QQ鍙?))

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
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.content
    except Exception as e:
        logger.warning(f"涓嬭浇澶村儚澶辫触: {e}")
        return None


def _transform_info(info: dict, info2: dict) -> list[str]:
    reply: list[str] = []

    if user_id := info.get("user_id"):
        reply.append(f"QQ鍙凤細{user_id}")

    if nickname := info.get("nickname"):
        reply.append(f"鏄电О锛歿nickname}")

    if card := info2.get("card"):
        reply.append(f"缇ゆ樀绉帮細{card}")

    if title := info2.get("title"):
        reply.append(f"澶磋锛歿title}")

    sex = info.get("sex")
    if sex == "male":
        reply.append("鎬у埆锛氱敺瀛╃焊")
    elif sex == "female":
        reply.append("鎬у埆锛氬コ瀛╃焊")

    by, bm, bd = info.get("birthday_year"), info.get("birthday_month"), info.get("birthday_day")
    if by and bm and bd:
        reply.append(f"璇炶景锛歿by}-{bm}-{bd}")
        reply.append(f"鏄熷骇锛歿_get_constellation(int(bm), int(bd))}")
        reply.append(f"鐢熻倴锛歿_get_zodiac(int(by), int(bm), int(bd))}")

    if age := info.get("age"):
        reply.append(f"骞撮緞锛歿age}宀?)

    if phoneNum := info.get("phoneNum"):
        if phoneNum != "-":
            reply.append(f"鐢佃瘽锛歿phoneNum}")

    if eMail := info.get("eMail"):
        if eMail != "-":
            reply.append(f"閭锛歿eMail}")

    if postCode := info.get("postCode"):
        if postCode != "-":
            reply.append(f"閭紪锛歿postCode}")

    country = info.get("country")
    province = info.get("province")
    city = info.get("city")
    if country == "涓浗" and (province or city):
        reply.append(f"鐜板眳锛歿province or ''}-{city or ''}")
    elif country:
        reply.append(f"鐜板眳锛歿country}")

    if homeTown := info.get("homeTown"):
        if homeTown != "0-0-0":
            reply.append(f"鏉ヨ嚜锛歿_parse_home_town(homeTown)}")

    if address := info.get("address"):
        if address != "-":
            reply.append(f"鍦板潃锛歿address}")

    if kBloodType := info.get("kBloodType"):
        try:
            reply.append(f"琛€鍨嬶細{_get_blood_type(int(kBloodType))}")
        except Exception:
            pass

    if (makeFriendCareer := info.get("makeFriendCareer")) and makeFriendCareer != "0":
        try:
            reply.append(f"鑱屼笟锛歿_get_career(int(makeFriendCareer))}")
        except Exception:
            pass

    if remark := info.get("remark"):
        reply.append(f"澶囨敞锛歿remark}")

    if labels := info.get("labels"):
        reply.append(f"鏍囩锛歿labels}")

    if info2.get("unfriendly"):
        reply.append("涓嶈壇璁板綍锛氭湁")

    if info2.get("is_robot"):
        reply.append("鏄惁涓篵ot锛氭槸")

    if info.get("is_vip"):
        reply.append("VIP锛氬凡寮€")

    if info.get("is_years_vip"):
        reply.append("骞磋垂VIP锛氬凡寮€")

    if int(info.get("vip_level", 0)) != 0:
        reply.append(f"VIP绛夌骇锛歿info['vip_level']}")

    if int(info.get("login_days", 0)) != 0:
        reply.append(f"杩炵画鐧诲綍澶╂暟锛歿info['login_days']}")

    if level := info2.get("level"):
        try:
            reply.append(f"缇ょ瓑绾э細{int(level)}绾?)
        except Exception:
            pass

    if join_time := info2.get("join_time"):
        try:
            reply.append(f"鍔犵兢鏃堕棿锛歿datetime.fromtimestamp(int(join_time)).strftime('%Y-%m-%d')}")
        except Exception:
            pass

    if qqLevel := info.get("qqLevel"):
        try:
            reply.append(f"QQ绛夌骇锛歿_qqLevel_to_icon(int(qqLevel))}")
        except Exception:
            pass

    if reg_time := info.get("reg_time"):
        try:
            reply.append(f"娉ㄥ唽鏃堕棿锛歿datetime.fromtimestamp(int(reg_time)).strftime('%Y-%m-%d')}")
        except Exception:
            pass

    if long_nick := info.get("long_nick"):
        for line in textwrap.wrap(text=f"绛惧悕锛歿long_nick}", width=15):
            reply.append(line)

    return reply


def _qqLevel_to_icon(level: int) -> str:
    icons = ["馃憫", "馃尀", "馃寵", "猸?]
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
        "鐧界緤搴?: ((3, 21), (4, 19)),
        "閲戠墰搴?: ((4, 20), (5, 20)),
        "鍙屽瓙搴?: ((5, 21), (6, 20)),
        "宸ㄨ煿搴?: ((6, 21), (7, 22)),
        "鐙瓙搴?: ((7, 23), (8, 22)),
        "澶勫コ搴?: ((8, 23), (9, 22)),
        "澶╃Г搴?: ((9, 23), (10, 22)),
        "澶╄潕搴?: ((10, 23), (11, 21)),
        "灏勬墜搴?: ((11, 22), (12, 21)),
        "鎽╃警搴?: ((12, 22), (1, 19)),
        "姘寸摱搴?: ((1, 20), (2, 18)),
        "鍙岄奔搴?: ((2, 19), (3, 20)),
    }
    for name, ((sm, sd), (em, ed)) in constellations.items():
        if (month == sm and day >= sd) or (month == em and day <= ed):
            return name
        if sm > em:  # wrap year
            if (month == sm and day >= sd) or (month == em + 12 and day <= ed):
                return name
    return f"鏄熷骇{month}-{day}"


def _get_zodiac(year: int, month: int, day: int) -> str:
    base_year = 2024  # dragon
    zodiacs = [
        "榫欚煇?,
        "铔囸煇?,
        "椹煇?,
        "缇婐煇?,
        "鐚答煇?,
        "楦○煇?,
        "鐙楌煇?,
        "鐚煇?,
        "榧狆煇€",
        "鐗涴煇?,
        "铏庰煇?,
        "鍏旔煇?,
    ]
    zodiac_year = year - 1 if (month == 1) or (month == 2 and day < 4) else year
    zodiac_index = (zodiac_year - base_year) % 12
    return zodiacs[zodiac_index]


def _get_career(num: int) -> str:
    career = {
        1: "璁＄畻鏈?浜掕仈缃?閫氫俊",
        2: "鐢熶骇/宸ヨ壓/鍒堕€?,
        3: "鍖荤枟/鎶ょ悊/鍒惰嵂",
        4: "閲戣瀺/閾惰/鎶曡祫/淇濋櫓",
        5: "鍟嗕笟/鏈嶅姟涓?涓綋缁忚惀",
        6: "鏂囧寲/骞垮憡/浼犲獟",
        7: "濞变箰/鑹烘湳/琛ㄦ紨",
        8: "寰嬪笀/娉曞姟",
        9: "鏁欒偛/鍩硅",
        10: "鍏姟鍛?琛屾斂/浜嬩笟鍗曚綅",
        11: "妯＄壒",
        12: "绌哄",
        13: "瀛︾敓",
        14: "鍏朵粬鑱屼笟",
    }
    return career.get(num, f"鑱屼笟{num}")


def _get_blood_type(num: int) -> str:
    blood_types = {1: "A鍨?, 2: "B鍨?, 3: "O鍨?, 4: "AB鍨?, 5: "鍏朵粬琛€鍨?}
    return blood_types.get(num, f"琛€鍨媨num}")


def _parse_home_town(home_town_code: str) -> str:
    # simplified mapping; extend if needed
    country_map = {
        "49": "涓浗",
        "250": "淇勭綏鏂?,
        "222": "鐗圭珛灏艰揪",
        "217": "娉曞浗",
    }
    province_map = {
        "98": "鍖椾含",
        "99": "澶╂触/杈藉畞",
        "100": "娌冲寳/灞辫タ",
        "101": "鍐呰挋鍙?鍚夋灄",
        "102": "榛戦緳姹?涓婃捣",
        "103": "姹熻嫃/娴欐睙",
        "104": "瀹夊窘/绂忓缓",
        "105": "姹熻タ/灞变笢",
        "106": "娌冲崡/婀栧寳/婀栧崡",
        "107": "鏂扮枂",
    }

    try:
        country_code, province_code, _ = home_town_code.split("-")
    except Exception:
        return str(home_town_code)
    country = country_map.get(country_code, f"澶栧浗{country_code}")
    if country_code == "49":  # 涓浗
        if province_code != "0":
            return province_map.get(province_code, f"{province_code}鐪?)
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

