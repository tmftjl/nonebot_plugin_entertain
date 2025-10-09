from __future__ import annotations

import json
from typing import Any, Dict, Optional, List

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

from ...utils import plugin_data_dir
from ...registry import Plugin


WELCOME_DIR = plugin_data_dir("welcome")
WELCOME_FILE = WELCOME_DIR / "welcome.json"
P = Plugin()


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


set_welcome = P.on_regex(r"^(?:#)?设置欢迎(?:\s*(.+))?$", name="set", block=True, priority=13)


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
    cq_content = await _sanitize_message_to_cq(bot, Message(raw))
    store = _load_store()
    store[key] = {"enabled": True, "content": cq_content}
    _save_store(store)
    await matcher.finish("已更新本群欢迎语")


show_welcome = P.on_regex(r"^(?:#)?查看欢迎$", name="show", block=True, priority=13)


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
    await matcher.finish(Message(f"当前欢迎已{status}\n") + Message(rec.get("content", "")))


enable_welcome = P.on_regex(r"^(?:#)?开启欢迎$", name="enable", block=True, priority=13)


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


disable_welcome = P.on_regex(r"^(?:#)?关闭欢迎$", name="disable", block=True, priority=13)


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


welcome_notice = on_notice(priority=50, permission=P.permission())


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
    await welcome_notice.finish(at + Message(" ") + Message(content_str))
