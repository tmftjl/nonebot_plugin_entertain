from __future__ import annotations

from datetime import datetime
from typing import Optional

import httpx
from nonebot import logger
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup
from nonebot.adapters.onebot.v11 import MessageEvent

from ...registry import Plugin
from ...config import register_plugin_config


# Plugin-local configuration
DEFAULT_CFG = {
    "qq_reg_time_api_key": None,
}
CFG = register_plugin_config("reg_time", DEFAULT_CFG)
P = Plugin()


_REG = P.on_regex(
    r"^#*注册时间\s*(\d*)$",
    name="query",
    priority=13,
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
    api_url = "https://api.s01s.cn/API/zcsj/"
    cfg = CFG.load()
    api_key = (cfg.get("qq_reg_time_api_key") or "B9FB02FC6AC1AF34F7D2B5390B468EAC")
    params = {"qq": qq, "key": api_key}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(api_url, params=params)
        r.raise_for_status()
        text = r.text
        if not text or "注册时间" not in text:
            return None
        return text


def _build_text_message(raw: str, qq: str) -> str:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"📌 查询QQ: {qq}",
        "══════════════",
        *lines,
        "══════════════",
        f"查询时间: {now}",
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
        await matcher.finish("未指定查询目标")
    try:
        text = await _query_registration(qq)
    except httpx.HTTPError as e:
        logger.opt(exception=e).warning("注册时间查询接口请求失败")
        await matcher.finish("服务暂不可用，请稍后重试")
        return
    if not text:
        await matcher.finish("查询失败，请检查账号有效性或API状态")
        return
    await matcher.finish(_build_text_message(text, qq))

