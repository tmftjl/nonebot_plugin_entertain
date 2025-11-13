from __future__ import annotations

import json
from typing import Optional

from nonebot import on_message
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot, MessageEvent

from core.framework.message_utils import get_reply_bundle

# 仅主人可用；最高优先级；不阻断其它插件
matcher = on_message(priority=0, permission=SUPERUSER, block=False)


@matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    bundle = await get_reply_bundle(bot, event)

    def _none_guard(x: Optional[object]) -> str:
        return "None" if x is None else str(x)

    # 为可读性，构造多行文本
    parts = []
    parts.append("[测试] get_reply_bundle 解析结果")
    parts.append(f"message_id: {_none_guard(bundle.message_id)}")

    # message 显示为字符串形态，避免对象过长
    try:
        parts.append(f"message(str): {_none_guard(bundle.message)}")
    except Exception:
        parts.append("message(str): <转换失败>")

    parts.append(f"text: {_none_guard(bundle.text)}")

    try:
        images_json = json.dumps(bundle.images, ensure_ascii=False)
    except Exception:
        images_json = str(bundle.images)
    parts.append(f"images(len={len(bundle.images)}): {images_json}")

    parts.append(f"forward_id: {_none_guard(bundle.forward_id)}")

    try:
        nodes_json = json.dumps(bundle.forward_nodes, ensure_ascii=False)
    except Exception:
        nodes_json = str(bundle.forward_nodes)
    parts.append(f"forward_nodes(len={len(bundle.forward_nodes)}): {nodes_json}")

    await matcher.finish("\n".join(parts))