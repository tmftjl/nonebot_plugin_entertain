from __future__ import annotations

"""AI 对话指令（精简版，UTF-8 中文注释与提示）。

保留统一的权限与命令名称，避免外部依赖报错；核心流程保持一致，
尽量少做业务改动，文本全部修正为 UTF-8 中文。
"""

import re
from typing import Optional

from nonebot import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, MessageEvent, Message
from nonebot.params import RegexMatched
from nonebot.log import logger

from ...core.framework.registry import Plugin
from ...core.framework.perm import _is_superuser, _uid, _has_group_role, PermLevel, PermScene

# 业务依赖（保持原模块路径与名称，便于接入）
from .manager import chat_manager  # type: ignore
from .config import get_config, get_personas, reload_all, save_config, CFG  # type: ignore


P = Plugin(name="ai_chat", display_name="AI 对话", enabled=True, level=PermLevel.LOW, scene=PermScene.ALL)


def get_session_id(event: MessageEvent) -> str:
    if isinstance(event, GroupMessageEvent):
        return f"group_{event.group_id}"
    elif isinstance(event, PrivateMessageEvent):
        return f"private_{event.user_id}"
    return f"unknown_{event.user_id}"


def _is_at_bot_robust(bot: Bot, event: MessageEvent) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    try:
        for seg in event.message:
            if seg.type == "at" and seg.data.get("qq") == bot.self_id:
                return True
        raw = str(event.message)
        if f"[CQ:at,qq={bot.self_id}]" in raw or f"[at:qq={bot.self_id}]" in raw:
            return True
    except Exception:
        pass
    return False


def extract_plain_text(message: Message) -> str:
    text_parts = []
    for seg in message:
        if seg.type == "text":
            text_parts.append(seg.data.get("text", "").strip())
    return " ".join(text_parts).strip()


async def check_superuser(event: MessageEvent) -> bool:
    return _is_superuser(_uid(event))


# 统一触发（群聊需 @ 机器人；私聊直接触发）
at_cmd = P.on_regex(
    r"^(.+)$",
    name="ai_chat_at",
    display_name="@ 机器人对话",
    priority=100,
    block=False,
)


@at_cmd.handle()
async def handle_chat_auto(bot: Bot, event: MessageEvent):
    # 群聊未 @ 时不触发
    if isinstance(event, GroupMessageEvent) and not (_is_at_bot_robust(bot, event) or getattr(event, "to_me", False)):
        return

    message = extract_plain_text(event.message)
    if not message:
        return

    session_type = "group" if isinstance(event, GroupMessageEvent) else "private"
    session_id = get_session_id(event)
    user_id = str(event.user_id)
    user_name = user_id
    group_id = str(getattr(event, "group_id", "")) if isinstance(event, GroupMessageEvent) else None

    try:
        response = await chat_manager.process_message(
            session_id=session_id,
            user_id=user_id,
            user_name=user_name,
            message=message,
            session_type=session_type,
            group_id=group_id,
        )
        if response:
            await at_cmd.send(response.lstrip("\r\n"))
    except Exception as e:
        logger.exception(f"[AI Chat] 对话处理失败: {e}")


# 会话信息
info_cmd = P.on_regex(r"^#会话信息$", name="ai_session_info", display_name="会话信息", priority=5, block=True)


@info_cmd.handle()
async def handle_info(event: MessageEvent):
    session_id = get_session_id(event)
    session = await chat_manager.get_session_info(session_id)
    if not session:
        await info_cmd.finish("未找到当前会话")

    personas = get_personas()
    persona = personas.get(session.persona_name, personas.get("default"))

    status = "已启用" if session.is_active else "已停用"
    info_text = (
        f"会话信息\n"
        f"会话 ID: {session.session_id}\n"
        f"状态: {status}\n"
        f"人格: {persona.name if persona else session.persona_name}\n"
        f"创建时间: {session.created_at[:19]}\n"
        f"更新时间: {session.updated_at[:19]}"
    )
    await info_cmd.finish(info_text)


# 清空会话
clear_cmd = P.on_regex(r"^#清空会话$", name="ai_clear_session", display_name="清空会话", priority=5, block=True, level=PermLevel.ADMIN)


@clear_cmd.handle()
async def handle_clear(event: MessageEvent):
    session_id = get_session_id(event)
    try:
        await chat_manager.clear_history(session_id)
    except Exception as e:
        logger.error(f"[AI Chat] 清空会话失败: {e}")
        await clear_cmd.finish("× 清空会话失败")
    await clear_cmd.finish("√ 已清空当前会话历史")


# 重载配置（超管）
reload_cmd = P.on_regex(
    r"^#重载AI配置$",
    name="ai_reload_config",
    display_name="重载 AI 配置",
    priority=5,
    block=True,
    level=PermLevel.SUPERUSER,
)


@reload_cmd.handle()
async def handle_reload(event: MessageEvent):
    if not await check_superuser(event):
        await reload_cmd.finish("需要超级用户权限")
    reload_all()
    chat_manager.reset_client()
    await reload_cmd.finish("√ 已重载所有配置并清理缓存")

