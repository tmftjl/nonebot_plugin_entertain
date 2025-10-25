"""群聊主动回复（AstrBot 风格）

- 在未 @ 机器人的普通群消息上，按概率触发一次“主动回复”
- 构造上下文时清空历史，仅用 System（含聊天室历史）+ 当前消息 + 可选后缀
"""
from __future__ import annotations

import random
from nonebot import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, Message

from .commands import (
    P,
    get_session_id,
    get_user_name,
    extract_plain_text,
    _is_at_bot_robust,
)
from .manager import chat_manager
from .config import get_config, CFG


@P.on_message(name="ai_active_reply_auto", priority=120, block=False).handle()
async def handle_active_reply_auto(bot: Bot, event: MessageEvent):
    try:
        # 仅群聊触发
        if not isinstance(event, GroupMessageEvent):
            return
        # 若包含 @/to_me 则按原通道走
        if _is_at_bot_robust(bot, event) or getattr(event, "to_me", False):
            return

        cfg_raw = CFG.load() or {}
        sess = (cfg_raw.get("session") or {})
        ch_enh = (sess.get("chatroom_enhance") or {})
        ar = (ch_enh.get("active_reply") or {})
        if not ar.get("enable", False):
            return
        prob = float(ar.get("probability", 0.0) or 0.0)
        if prob <= 0.0:
            return

        text = extract_plain_text(event.message)
        if not text:
            return
        if random.random() > prob:
            return

        session_id = get_session_id(event)
        user_id = str(event.user_id)
        user_name = get_user_name(event)
        group_id = str(getattr(event, "group_id", ""))

        suffix = ar.get(
            "prompt_suffix",
            "Now, a new message is coming: `{message}`. Please react to it. Only output your response and do not output any other information.",
        )

        response = await chat_manager.process_message(
            session_id=session_id,
            user_id=user_id,
            user_name=user_name,
            message=text,
            session_type="group",
            group_id=group_id,
            active_reply=True,
            active_reply_suffix=suffix,
        )

        if response:
            response = response.lstrip("\r\n")
            cfg = get_config()
            if cfg.response.enable_at_reply:
                await bot.send(event, Message(f"[CQ:at,qq={user_id}] {response}"))
            else:
                await bot.send(event, Message(response))
    except Exception:
        # 静默失败，避免打扰
        return
