from __future__ import annotations
from ...core.constants import DEFAULT_HTTP_TIMEOUT


from datetime import datetime
from typing import Optional

import httpx
from nonebot import logger
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup
from nonebot.adapters.onebot.v11 import MessageEvent

from ...core.api import Plugin
from .config import cfg_reg_time


# Config centralized in plugins/entertain/config.py
P = Plugin(name="entertain", display_name="濞变箰")


_REG = P.on_regex(
    r"^#娉ㄥ唽鏃堕棿$",
    name="query",
    display_name="娉ㄥ唽鏃堕棿",
    priority=5,
    block=True,
)


def _extract_qq(e: MessageEvent, matched: str) -> Optional[str]:
    for seg in e.message:
        if seg.type == "at":
            qq = seg.data.get("qq")
            if qq and qq.isdigit():
                return qq
    if matched and matched.isdigit():
        return matched
    try:
        return str(e.user_id)
    except Exception:
        return None


async def _query_registration(qq: str) -> Optional[str]:
    cfg = cfg_reg_time()
    api_url = str(cfg.get("qq_reg_time_api_url") )
    api_key = str(cfg.get("qq_reg_time_api_key") or "")`n
    if not api_key:
        logger.warning("[reg_time] API key 鏈厤缃?璇峰湪閰嶇疆鏂囦欢涓缃?qq_reg_time_api_key")
        return None

    params = {"qq": qq, "key": api_key}
    async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
        r = await client.get(api_url, params=params)
        r.raise_for_status()
        text = r.text
        if not text or "娉ㄥ唽鏃堕棿" not in text:
            return None
        return text


def _build_text_message(raw: str, qq: str) -> str:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"馃搶 鏌ヨQQ: {qq}",
        "鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲",
        *lines,
        "鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲",
        f"鏌ヨ鏃堕棿: {now}",
    ]
    return "\n".join(parts)


@_REG.handle()
async def _(matcher: Matcher, event: MessageEvent, groups: tuple = RegexGroup()):
    try:
        matched_digits = (groups[0] or "").strip() if groups else ""
    except Exception:
        matched_digits = ""
    qq = _extract_qq(event, matched_digits)
    if not qq:
        await matcher.finish("鏈寚瀹氭煡璇㈢洰鏍?)
    try:
        text = await _query_registration(qq)
    except httpx.HTTPError as e:
        logger.opt(exception=e).warning("娉ㄥ唽鏃堕棿鏌ヨ鎺ュ彛璇锋眰澶辫触")
        await matcher.finish("鏈嶅姟鏆備笉鍙敤锛岃绋嶅悗閲嶈瘯")
        return
    if not text:
        await matcher.finish("鏌ヨ澶辫触锛岃妫€鏌ヨ处鍙锋湁鏁堟€ф垨API鐘舵€?)
        return
    await matcher.finish(_build_text_message(text, qq))



