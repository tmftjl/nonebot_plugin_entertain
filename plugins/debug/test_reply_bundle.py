from __future__ import annotations

import json
from typing import Optional

from nonebot import on_message
from nonebot.log import logger
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot, MessageEvent

from core.framework.message_utils import (
    get_reply_bundle,
    extract_plain_text,
    extract_image_sources_with_bot,
    _extract_forward_id_from_message,
    _get_forward_nodes_by_id,
)

# 仅主人可用；最高优先级；不阻断其它插件
matcher = on_message(priority=0, permission=SUPERUSER, block=False)


@matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    logger.debug("[test] 进入 on_message")
    try:
        s = str(event.get_message())
        logger.debug(f"[test] 当前消息字符串长度={len(s)} 内容={s!r}")
    except Exception as e:
        logger.debug(f"[test] 获取当前消息字符串失败: {e}")

    # 先解析当前消息（不需要回复也能看到结果）
    try:
        text_cur = extract_plain_text(event.get_message())
        imgs_cur = await extract_image_sources_with_bot(bot, event.get_message())
        fid_cur = _extract_forward_id_from_message(event.get_message())
        nodes_cur = await _get_forward_nodes_by_id(bot, fid_cur) if fid_cur else []
        logger.debug(
            f"[test] 当前消息解析: text_len={len(text_cur or '')} images={len(imgs_cur)} forward_id={fid_cur} nodes={len(nodes_cur)}"
        )
    except Exception as e:
        logger.debug(f"[test] 当前消息解析异常: {e}")
        text_cur, imgs_cur, fid_cur, nodes_cur = "", [], None, []

    # 再获取被回复消息的打包结果
    bundle = await get_reply_bundle(bot, event)

    def _none_guard(x: Optional[object]) -> str:
        return "None" if x is None else str(x)

    parts = []
    parts.append("[测试] 当前消息解析")
    parts.append(f"text: {_none_guard(text_cur)}")
    try:
        parts.append(f"images(len={len(imgs_cur)}): {json.dumps(imgs_cur, ensure_ascii=False)}")
    except Exception:
        parts.append(f"images(len={len(imgs_cur)}): {imgs_cur}")
    parts.append(f"forward_id: {_none_guard(fid_cur)}")
    try:
        parts.append(f"forward_nodes(len={len(nodes_cur)}): {json.dumps(nodes_cur, ensure_ascii=False)}")
    except Exception:
        parts.append(f"forward_nodes(len={len(nodes_cur)}): {nodes_cur}")

    parts.append("")
    parts.append("[测试] 被回复消息解析 get_reply_bundle")
    parts.append(f"message_id: {_none_guard(bundle.message_id)}")
    try:
        parts.append(f"message(str): {_none_guard(bundle.message)}")
    except Exception:
        parts.append("message(str): <转换失败>")
    parts.append(f"text: {_none_guard(bundle.text)}")
    try:
        parts.append(f"images(len={len(bundle.images)}): {json.dumps(bundle.images, ensure_ascii=False)}")
    except Exception:
        parts.append(f"images(len={len(bundle.images)}): {bundle.images}")
    parts.append(f"forward_id: {_none_guard(bundle.forward_id)}")
    try:
        parts.append(f"forward_nodes(len={len(bundle.forward_nodes)}): {json.dumps(bundle.forward_nodes, ensure_ascii=False)}")
    except Exception:
        parts.append(f"forward_nodes(len={len(bundle.forward_nodes)}): {bundle.forward_nodes}")

    out = "\n".join(parts)
    logger.debug(f"[test] 回复文本长度={len(out)}")
    await matcher.finish(out)