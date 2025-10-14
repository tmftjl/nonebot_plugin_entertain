from __future__ import annotations

import base64
from typing import Optional

import httpx
from nonebot.params import RegexGroup
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageEvent,
    MessageSegment,
)

from ...core.api import Plugin, register_namespaced_config
from .box_draw import create_image


def _b64_image(img_bytes: bytes) -> MessageSegment:
    return MessageSegment.image(f"base64://{base64.b64encode(img_bytes).decode()}")


P = Plugin(name="entertain")

# 写入 entertain/config.json 的 box 默认节点
DEFAULT_CFG = {
    "auto_box": False,
    "increase_box": False,
    "decrease_box": False,
    "only_admin": False,
    "auto_box_groups": [],
    "box_blacklist": [],
}
_BOX_CFG = register_namespaced_config("entertain", "box", DEFAULT_CFG)
try:
    _ = _BOX_CFG.load()
except Exception:
    pass

box_cmd = P.on_regex(r"^(?:[/#])?(?:盒|开盒)\s*(.*)?$", name="open", block=True, priority=5)


@box_cmd.handle()
async def _(bot: Bot, event: MessageEvent, groups: tuple = RegexGroup()):
    # 解析目标 QQ
    target_id: Optional[str] = None
    try:
        for seg in event.message:  # type: ignore[attr-defined]
            if seg.type == "at":
                qq = seg.data.get("qq")
                if qq and qq != "all":
                    target_id = str(qq)
                    break
    except Exception:
        pass

    try:
        arg = (groups[0] or "").strip() if groups else ""
    except Exception:
        arg = ""
    if not target_id and arg and arg.isdigit():
        target_id = arg
    if not target_id:
        target_id = str(getattr(event, "user_id", ""))

    # 拉取头像
    avatar_bytes: Optional[bytes] = None
    try:
        url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={target_id}&spec=640"
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
            avatar_bytes = r.content
    except Exception:
        avatar_bytes = None

    if not avatar_bytes:
        await box_cmd.finish("未能获取头像，请稍后再试")

    # 生成图片
    reply_lines = [
        f"为 {target_id} 开盒",
        "祝你天天开心，事事顺利",
    ]
    try:
        img = create_image(avatar_bytes, reply_lines)
        await box_cmd.finish(_b64_image(img))
    except Exception:
        await box_cmd.finish("生成图片失败")
