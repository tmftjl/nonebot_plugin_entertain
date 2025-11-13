from __future__ import annotations

import json
from typing import Optional

from nonebot import on_message
from nonebot.log import logger
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot, MessageEvent

from ...core.framework.message_utils import (
    get_message_bundle,
)

# 仅主人可用；最高优先级；不阻断其它插件
matcher = on_message(priority=0, permission=SUPERUSER, block=False)


def _none_guard(x: Optional[object]) -> str:
    return "None" if x is None else str(x)


def _dump_bundle(title: str, b) -> str:
    if b is None:
        return f"{title}: None"
    parts = []
    parts.append(title)
    parts.append(f"source: {b.source}")
    parts.append(f"message_id: {_none_guard(b.message_id)}")
    try:
        parts.append(f"message(str): {_none_guard(b.message)}")
    except Exception:
        parts.append("message(str): <转换失败>")
    parts.append(f"text: {_none_guard(b.text)}")
    try:
        parts.append(f"images(len={len(b.images)}): {json.dumps(b.images, ensure_ascii=False)}")
    except Exception:
        parts.append(f"images(len={len(b.images)}): {b.images}")
    parts.append(f"forward_id: {_none_guard(b.forward_id)}")
    try:
        parts.append(f"forward_nodes(len={len(b.forward_nodes)}): {json.dumps(b.forward_nodes, ensure_ascii=False)}")
    except Exception:
        parts.append(f"forward_nodes(len={len(b.forward_nodes)}): {b.forward_nodes}")
    try:
        parts.append(f"mentions(len={len(b.mentions)}): {json.dumps([{'user_id': m.user_id, 'nickname': m.nickname} for m in b.mentions], ensure_ascii=False)}")
    except Exception:
        parts.append(f"mentions(len={len(b.mentions)}): {[ (m.user_id, m.nickname) for m in b.mentions ]}")
    # 嵌套的回复
    if getattr(b, 'reply', None) is not None:
        try:
            parts.append("")
            parts.append(_dump_bundle("[测试] 当前消息的回复(嵌套)", b.reply))
        except Exception:
            parts.append("[测试] 当前消息的回复(嵌套): <打印失败>")
    return "\n".join(parts)


@matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    logger.debug("[test] 进入 on_message")

    # 仅取"当前"，其中会包含嵌套的 reply 字段（如有）
    cur = await get_message_bundle(
        bot, event,
        source="current",
        want_text=True,
        want_images=True,
        want_forward=True,
        want_mentions=True,
        include_reply=True,
    )

    out = _dump_bundle("[测试] 当前消息解析(整合)", cur)
    logger.debug(f"[test] 回复文本长度={len(out)}")
    await matcher.finish(out)