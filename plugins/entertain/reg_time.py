from __future__ import annotations

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
P = Plugin(name="entertain", display_name="娱乐")


_REG = P.on_regex(
    r"^#注册时间$",
    name="query",
    display_name="注册时间",
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
    api_key = str(cfg.get("qq_reg_time_api_key") or "")
    timeout = int(cfg.get("qq_reg_time_timeout") or 15)

    if not api_key:
        logger.warning("[reg_time] API key 未配置,请在配置文件中设置 qq_reg_time_api_key")
        return None

    params = {"qq": qq, "key": api_key}
    async with httpx.AsyncClient(timeout=timeout) as client:
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
