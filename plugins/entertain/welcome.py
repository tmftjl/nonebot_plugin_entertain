from __future__ import annotations

import json
from typing import Any, Dict, Optional, List
from pathlib import Path
import re
import uuid

from nonebot import on_notice
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup
from nonebot.adapters.onebot.v11 import (
    Message,
    MessageSegment,
    Bot,
    GroupIncreaseNoticeEvent,
    MessageEvent,
)
import base64
import httpx

from ...core.api import plugin_data_dir, data_dir
from ...core.api import Plugin


WELCOME_DIR = plugin_data_dir("entertain")
WELCOME_FILE = WELCOME_DIR / "welcome.json"
# 全局欢迎图片目录：data/welcome
WELCOME_IMG_DIR: Path = data_dir("welcome")
P = Plugin(name="entertain")


def _load_store() -> Dict[str, Dict[str, Any]]:
    try:
        if WELCOME_FILE.exists():
            data = json.loads(WELCOME_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_store(data: Dict[str, Dict[str, Any]]) -> None:
    try:
        WELCOME_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _get_group_key(event: MessageEvent | GroupIncreaseNoticeEvent) -> Optional[str]:
    gid = getattr(event, "group_id", None)
    return str(gid) if gid is not None else None


async def _image_to_base64_uri(bot: Bot, seg: MessageSegment) -> Optional[str]:
    try:
        data = getattr(seg, "data", {}) or {}
        file_val = str(data.get("file") or "")
        if file_val.startswith("base64://"):
            return file_val
        url = data.get("url")
        if isinstance(url, str) and url.startswith("http"):
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                b = resp.content
                return "base64://" + base64.b64encode(b).decode()
        if file_val:
            try:
                info = await bot.call_api("get_image", file=file_val)
                path = (info or {}).get("file")
                if path:
                    with open(path, "rb") as f:
                        b = f.read()
                    return "base64://" + base64.b64encode(b).decode()
            except Exception:
                pass
    except Exception:
        pass
    return None


async def _sanitize_message_to_cq(bot: Bot, msg: Message) -> str:
    out: List[MessageSegment] = []
    for seg in msg:
        try:
            if seg.type == "image":
                b64 = await _image_to_base64_uri(bot, seg)
                if b64:
                    out.append(MessageSegment.image(b64))
                else:
                    out.append(seg)
            else:
                out.append(seg)
        except Exception:
            out.append(seg)
    return str(Message(out))


# ---------- 新逻辑：仅允许文本与图片，图片保存为 UUID 文件，并在 JSON 中以占位符存储 ----------

_PH_PATTERN = re.compile(r"\\[\\[WELCOME_IMG:([^\]]+)\\]\\]")


def _guess_ext(data: bytes) -> str:
    # 简单魔数判断
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith(b"GIF8"):
            return ".gif"
        if data[:4] == b"RIFF" and b"WEBP" in data[:16]:
            return ".webp"
    except Exception:
        pass
    return ".bin"


async def _image_bytes(bot: Bot, seg: MessageSegment) -> Optional[bytes]:
    try:
        data = getattr(seg, "data", {}) or {}
        file_val = str(data.get("file") or "")
        # base64
        if file_val.startswith("base64://"):
            try:
                b64 = file_val.split("base64://", 1)[1]
                return base64.b64decode(b64)
            except Exception:
                return None
        # url
        url = data.get("url")
        if isinstance(url, str) and url.startswith("http"):
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        # from onebot image cache by file id
        if file_val:
            try:
                info = await bot.call_api("get_image", file=file_val)
                path = (info or {}).get("file")
                if path:
                    with open(path, "rb") as f:
                        return f.read()
            except Exception:
                return None
    except Exception:
        return None
    return None


async def _serialize_text_and_images(bot: Bot, msg: Message) -> tuple[str, Dict[str, int]]:
    """将消息序列化为仅文本 + 图片占位符，并保存图片。

    返回: (serialized_str, meta)
      - serialized_str: 包含文本与 [[WELCOME_IMG:<filename>]] 占位符的内容
      - meta: {
          images_saved, images_failed, text_len, segments_ignored
        }
    """
    parts: List[str] = []
    images_saved = 0
    images_failed = 0
    text_len = 0
    segments_ignored = 0

    for seg in msg:
        try:
            if seg.type == "image":
                b = await _image_bytes(bot, seg)
                if not b:
                    images_failed += 1
                    continue
                name = f"{uuid.uuid4().hex}"
                ext = _guess_ext(b)
                fname = name + ext
                fp = WELCOME_IMG_DIR / fname
                try:
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_bytes(b)
                    parts.append(f"[[WELCOME_IMG:{fname}]]")
                    images_saved += 1
                except Exception:
                    images_failed += 1
                    continue
            elif seg.type == "text":
                t = str(getattr(seg, "data", {}).get("text", ""))
                if t:
                    parts.append(t)
                    text_len += len(t)
            else:
                segments_ignored += 1
        except Exception:
            segments_ignored += 1

    return "".join(parts), {
        "images_saved": images_saved,
        "images_failed": images_failed,
        "text_len": text_len,
        "segments_ignored": segments_ignored,
    }


def _render_placeholders_to_message(s: str) -> Message:
    """将占位符字符串转换为带图片段的 Message。"""
    out: List[MessageSegment] = []
    pos = 0
    for m in _PH_PATTERN.finditer(s):
        start, end = m.span()
        if start > pos:
            out.append(MessageSegment.text(s[pos:start]))
        fname = m.group(1)
        fp = (WELCOME_IMG_DIR / fname).resolve()
        try:
            # 使用 file:// URI，兼容 Windows 路径
            uri = Path(fp).as_uri()
            out.append(MessageSegment.image(uri))
        except Exception:
            # 如果路径无效，退化为占位符原文
            out.append(MessageSegment.text(m.group(0)))
        pos = end
    if pos < len(s):
        out.append(MessageSegment.text(s[pos:]))
    return Message(out)


def _render_welcome_content(s: str) -> Message:
    """兼容旧数据：
    - 若包含占位符，则按占位符渲染
    - 否则回退为按 CQ 文本渲染
    """
    if _PH_PATTERN.search(s):
        return _render_placeholders_to_message(s)
    # 旧数据路径：直接使用 CQ 解析
    return Message(s)


set_welcome = P.on_regex(r"^(?:#)?设置欢迎(?:\s*(.+))?$", name="set",display_name="设置欢迎", block=True, priority=12)


@set_welcome.handle()
async def _(matcher: Matcher, bot: Bot, event: MessageEvent, groups: tuple = RegexGroup()):
    key = _get_group_key(event)
    if not key:
        await matcher.finish("请在群聊中使用该命令")
    try:
        raw = (groups[0] or "").strip() if groups else ""
    except Exception:
        raw = ""
    if not raw:
        await matcher.finish("请提供欢迎内容，支持任意格式")
    # 仅允许文本+图片，图片保存为 UUID 文件，内容以占位符保存
    serialized, meta = await _serialize_text_and_images(bot, Message(raw))
    if not serialized:
        msg = ["欢迎内容无效：仅支持文本和图片。"]
        if meta.get("images_failed"):
            msg.append(f"有 {meta['images_failed']} 张图片保存失败")
        if meta.get("segments_ignored"):
            msg.append(f"有 {meta['segments_ignored']} 个非文本/图片片段已忽略")
        await matcher.finish("，".join(msg))

    store = _load_store()
    store[key] = {"enabled": True, "content": serialized}
    _save_store(store)

    # 成功提示更详细：支持仅图片、混排等
    parts = []
    if meta.get("images_saved", 0) > 0 and meta.get("text_len", 0) == 0:
        parts.append(f"已更新欢迎：仅图片（{meta['images_saved']} 张）")
    elif meta.get("images_saved", 0) > 0 and meta.get("text_len", 0) > 0:
        parts.append(f"已更新欢迎：文本+图片（图片 {meta['images_saved']} 张，文本 {meta['text_len']} 字）")
    elif meta.get("text_len", 0) > 0:
        parts.append(f"已更新欢迎：仅文本（{meta['text_len']} 字）")

    if meta.get("images_failed", 0) > 0:
        parts.append(f"其中 {meta['images_failed']} 张图片保存失败")
    if meta.get("segments_ignored", 0) > 0:
        parts.append(f"有 {meta['segments_ignored']} 个非文本/图片片段已忽略")

    await matcher.finish("，".join(parts) or "已更新本群欢迎语")


show_welcome = P.on_regex(r"^(?:#)?查看欢迎$", name="show",display_name="查看欢迎", block=True, priority=12)


@show_welcome.handle()
async def _(matcher: Matcher, event: MessageEvent):
    key = _get_group_key(event)
    if not key:
        await matcher.finish("请在群聊中使用该命令")
    store = _load_store()
    rec = store.get(key)
    if not rec:
        await matcher.finish("当前未设置欢迎语")
    status = "开启" if rec.get("enabled", True) else "关闭"
    # 预览时将占位符渲染为图片
    content_str = rec.get("content", "")
    await matcher.finish(Message(f"当前欢迎已{status}\n") + _render_welcome_content(content_str))


enable_welcome = P.on_regex(r"^(?:#)?开启欢迎$",display_name="开启欢迎", name="enable", block=True, priority=12)


@enable_welcome.handle()
async def _(matcher: Matcher, event: MessageEvent):
    key = _get_group_key(event)
    if not key:
        await matcher.finish("请在群聊中使用该命令")
    store = _load_store()
    rec = store.get(key) or {}
    rec["enabled"] = True
    store[key] = rec
    _save_store(store)
    await matcher.finish("已开启本群欢迎")


disable_welcome = P.on_regex(r"^(?:#)?关闭欢迎$",display_name="关闭欢迎", name="disable", block=True, priority=12)


@disable_welcome.handle()
async def _(matcher: Matcher, event: MessageEvent):
    key = _get_group_key(event)
    if not key:
        await matcher.finish("请在群聊中使用该命令")
    store = _load_store()
    rec = store.get(key) or {}
    rec["enabled"] = False
    store[key] = rec
    _save_store(store)
    await matcher.finish("已关闭本群欢迎")


welcome_notice = on_notice(priority=12, permission=P.permission())


@welcome_notice.handle()
async def _(event: GroupIncreaseNoticeEvent):
    key = _get_group_key(event)
    if not key:
        return
    store = _load_store()
    rec = store.get(key)
    if not rec:
        return
    if not rec.get("enabled", True):
        return
    content_str = rec.get("content", "")
    if not content_str:
        return
    at = MessageSegment.at(event.user_id)
    # 发送时将占位符还原为图片
    await welcome_notice.finish(at + Message(" ") + _render_welcome_content(content_str))
