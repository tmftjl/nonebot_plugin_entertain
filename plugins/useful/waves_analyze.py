from __future__ import annotations

import asyncio
import base64
from typing import Iterable, List, Optional, Tuple, Union

from nonebot.matcher import Matcher
from nonebot.params import RegexGroup
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
)

from ...core.api import Plugin
from ...core.http import get_shared_async_client
from ..group_admin.utils import get_target_message_id


# 参照 temp/wutheringwaves_custom 的实现
# 外部评分服务
API_URL = "http://loping151.site:5678/score"
TOKEN = "f3e6d1d382925f0c63bd296e3e92a314"


P = Plugin(name="useful", display_name="有用")
waves_analyze_cmd = P.on_regex(
    r"^ww(?:分析|评分)\s*(.*)$",
    name="waves_analyze",
    display_name="鸣潮分析评分",
    block=True,
    priority=5,
)


async def _fetch_bytes_from_source(src: Union[str, bytes]) -> Optional[bytes]:
    """支持 bytes / http(s) URL / base64://... / 文件路径"""
    if isinstance(src, bytes):
        return src
    s = (src or "").strip()
    if not s:
        return None

    # base64:// 前缀
    if s.startswith("base64://"):
        try:
            return base64.b64decode(s[len("base64://") :])
        except Exception:
            return None

    # http(s) URL
    if s.startswith("http://") or s.startswith("https://"):
        try:
            client = await get_shared_async_client()
            resp = await client.get(s, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()
            return resp.content
        except Exception:
            return None

    # 文件路径（尽力而为）
    try:
        with open(s, "rb") as f:
            return f.read()
    except Exception:
        return None


def _encode_images_to_b64(images: Iterable[bytes]) -> List[str]:
    return [base64.b64encode(b).decode("utf-8") for b in images]


async def _post_score(images_b64: List[str], command_str: str) -> Tuple[Optional[bytes], Optional[str]]:
    """调用远端评分服务，返回(图片字节, 提示消息)"""
    payload = {"command_str": command_str or "", "images_base64": images_b64}
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        client = await get_shared_async_client()
        resp = await client.post(API_URL, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            return None, f"评分服务返回了无法解析的响应: {resp.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return None, f"请求评分服务失败: {e}"

    message: Optional[str] = data.get("message") if isinstance(data, dict) else None
    result_b64: Optional[str] = data.get("result_image_base64") if isinstance(data, dict) else None
    if not result_b64:
        return None, message or "评分服务未返回结果图片"
    try:
        return base64.b64decode(result_b64), message
    except Exception as e:  # noqa: BLE001
        return None, f"结果图片解析失败: {e}"


def _extract_image_sources(msg: Message) -> List[str]:
    """从消息段提取图片来源（url/base64/file）。"""
    out: List[str] = []
    try:
        for seg in msg:
            if seg.type != "image":
                continue
            data = seg.data or {}
            url = (data.get("url") or "").strip()
            if url:
                out.append(url)
                continue
            file_ = (data.get("file") or "").strip()
            if file_:
                # 可能是 base64:// / 也可能是路径 / go-cqhttp 内部路径
                out.append(file_)
    except Exception:
        pass
    return out


async def _get_images_from_event_or_reply(bot: Bot, event: MessageEvent) -> List[str]:
    """优先从当前消息取图；没有则尝试从被引用的消息中取图。"""
    # 1) 当前消息
    current = _extract_image_sources(event.get_message())
    if current:
        return current

    # 2) 被回复/引用的消息
    try:
        mid = get_target_message_id(event)
        if not mid:
            return []
        data = await bot.get_msg(message_id=mid)  # type: ignore[arg-type]
        raw = data.get("message") if isinstance(data, dict) else None
        if isinstance(raw, str) and raw:
            quoted_msg = Message(raw)
            return _extract_image_sources(quoted_msg)
    except Exception:
        return []
    return []


@waves_analyze_cmd.handle()
async def _handle(
    matcher: Matcher,
    bot: Bot,
    event: MessageEvent,
    groups: tuple = RegexGroup(),
):
    # 解析命令参数
    try:
        command_str = (groups[0] or "").strip() if groups else ""
    except Exception:
        command_str = ""

    img_src_list = await _get_images_from_event_or_reply(bot, event)

    if (not img_src_list) or (not command_str):
        msg = MessageSegment.reply(event.message_id) + MessageSegment.text(
            "请同时发送图片与命令：ww分析土豆 1c"
        )
        await matcher.finish(Message(msg))
        return

    # 并发读取图片字节
    tasks = [asyncio.create_task(_fetch_bytes_from_source(src)) for src in img_src_list]
    results = await asyncio.gather(*tasks)
    img_bytes_list = [b for b in results if b]

    if not img_bytes_list:
        msg = MessageSegment.reply(event.message_id) + MessageSegment.text("未能读取到有效的图片数据")
        await matcher.finish(Message(msg))
        return

    images_b64 = _encode_images_to_b64(img_bytes_list)
    result_img, tip = await _post_score(images_b64, command_str)

    if not result_img:
        text = tip or "分析失败，请重试"
        await matcher.finish(Message(MessageSegment.reply(event.message_id) + MessageSegment.text(text)))
        return

    await matcher.finish(
        Message(MessageSegment.reply(event.message_id) + MessageSegment.image(result_img))
    )

