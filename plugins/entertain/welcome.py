from __future__ import annotations
from ...core.constants import DEFAULT_HTTP_TIMEOUT


import json
import base64
import re
import uuid
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

import httpx
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

from ...core.api import plugin_data_dir, data_dir
from ...core.api import Plugin


# Storage
WELCOME_DIR = plugin_data_dir("entertain")
WELCOME_FILE = WELCOME_DIR / "welcome.json"
WELCOME_IMG_ROOT: Path = data_dir("welcome")

P = Plugin(name="entertain")


# ---------- storage helpers ----------

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
        WELCOME_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _get_group_key(event: MessageEvent | GroupIncreaseNoticeEvent) -> Optional[str]:
    gid = getattr(event, "group_id", None)
    return str(gid) if gid is not None else None


def _group_img_dir(group_key: str) -> Path:
    return (WELCOME_IMG_ROOT / str(group_key)).resolve()


def _reset_group_img_dir(group_key: str) -> Path:
    gdir = _group_img_dir(group_key)
    try:
        if gdir.exists():
            shutil.rmtree(gdir, ignore_errors=True)
    except Exception:
        pass
    gdir.mkdir(parents=True, exist_ok=True)
    return gdir


# ---------- image IO helpers ----------

def _guess_ext(data: bytes) -> str:
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
            async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        # onebot local cache by file id
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


# placeholder pattern e.g. [[WELCOME_IMG:<filename>]]
_PH_PATTERN = re.compile(r"\[\[WELCOME_IMG:([^\]]+)\]\]")


async def _serialize_text_and_images(
    bot: Bot, msg: Message, group_key: str
) -> Tuple[str, Dict[str, int]]:
    """Serialize message to text + image placeholders and save images.

    Returns: (serialized_str, meta)
      - serialized_str: string containing text and [[WELCOME_IMG:<filename>]]
      - meta: { images_saved, images_failed, text_len, segments_ignored }
    """
    # reset group dir before saving new set
    _reset_group_img_dir(group_key)
    gdir = _group_img_dir(group_key)

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
                name = uuid.uuid4().hex
                ext = _guess_ext(b)
                fname = name + ext
                fp = gdir / fname
                try:
                    fp.write_bytes(b)
                    parts.append(f"[[WELCOME_IMG:{fname}]]")
                    images_saved += 1
                except Exception:
                    images_failed += 1
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


def _render_img_placeholders(s: str, group_key: Optional[str]) -> Message:
    out: List[MessageSegment] = []
    pos = 0
    for m in _PH_PATTERN.finditer(s):
        start, end = m.span()
        if start > pos:
            out.append(MessageSegment.text(s[pos:start]))
        fname = m.group(1)
        base = _group_img_dir(group_key) if group_key else WELCOME_IMG_ROOT
        fp = (base / fname).resolve()
        try:
            with open(fp, "rb") as f:
                b = f.read()
            out.append(MessageSegment.image("base64://" + base64.b64encode(b).decode()))
        except Exception:
            out.append(MessageSegment.text(m.group(0)))
        pos = end
    if pos < len(s):
        out.append(MessageSegment.text(s[pos:]))
    return Message(out)


def _render_welcome_content(group_key: Optional[str], s: str) -> Message:
    if _PH_PATTERN.search(s):
        return _render_img_placeholders(s, group_key)
    # legacy: treat as CQ text
    return Message(s)


# ---------- commands ----------

set_welcome = P.on_regex(
    r"^(?:#)璁剧疆娆㈣繋(?:\s*(.+))?$", name="set", display_name="璁剧疆娆㈣繋", block=True, priority=5
)


@set_welcome.handle()
async def _(matcher: Matcher, bot: Bot, event: MessageEvent, groups: tuple = RegexGroup()):
    key = _get_group_key(event)
    if not key:
        await matcher.finish("璇峰湪缇よ亰涓娇鐢ㄨ鍛戒护")
    try:
        raw = (groups[0] or "").strip() if groups else ""
    except Exception:
        raw = ""
    if not raw:
        await matcher.finish("璇锋彁渚涙杩庡唴瀹癸紝浠呮敮鎸佹枃鏈笌鍥剧墖")

    serialized, meta = await _serialize_text_and_images(bot, Message(raw), key)
    if not serialized:
        msg = ["娆㈣繋鍐呭鏃犳晥锛氫粎鏀寔鏂囨湰涓庡浘鐗?]
        if meta.get("images_failed"):
            msg.append(f"鏈?{meta['images_failed']} 寮犲浘鐗囦繚瀛樺け璐?)
        if meta.get("segments_ignored"):
            msg.append(f"鏈?{meta['segments_ignored']} 涓潪鏂囨湰/鍥剧墖鐗囨宸插拷鐣?)
        await matcher.finish("锛?.join(msg))

    store = _load_store()
    store[key] = {"enabled": True, "content": serialized}
    _save_store(store)

    parts = []
    if meta.get("images_saved", 0) > 0 and meta.get("text_len", 0) == 0:
        parts.append(f"宸叉洿鏂版杩庯細浠呭浘鐗囷紙{meta['images_saved']} 寮狅級")
    elif meta.get("images_saved", 0) > 0 and meta.get("text_len", 0) > 0:
        parts.append(f"宸叉洿鏂版杩庯細鏂囨湰+鍥剧墖锛堝浘鐗?{meta['images_saved']} 寮狅紝鏂囨湰 {meta['text_len']} 瀛楋級")
    elif meta.get("text_len", 0) > 0:
        parts.append(f"宸叉洿鏂版杩庯細浠呮枃鏈紙{meta['text_len']} 瀛楋級")

    if meta.get("images_failed", 0) > 0:
        parts.append(f"鍏朵腑 {meta['images_failed']} 寮犲浘鐗囦繚瀛樺け璐?)
    if meta.get("segments_ignored", 0) > 0:
        parts.append(f"鏈?{meta['segments_ignored']} 涓潪鏂囨湰/鍥剧墖鐗囨宸插拷鐣?)

    await matcher.finish("锛?.join(parts) or "宸叉洿鏂版湰缇ゆ杩庤")


show_welcome = P.on_regex(
    r"^(?:#)?鏌ョ湅娆㈣繋$", name="show", display_name="鏌ョ湅娆㈣繋", block=True, priority=5
)


@show_welcome.handle()
async def _(matcher: Matcher, event: MessageEvent):
    key = _get_group_key(event)
    if not key:
        await matcher.finish("璇峰湪缇よ亰涓娇鐢ㄨ鍛戒护")
    store = _load_store()
    rec = store.get(key)
    if not rec:
        await matcher.finish("褰撳墠鏈缃杩庤")
    status = "寮€鍚? if rec.get("enabled", True) else "鍏抽棴"
    content_str = rec.get("content", "")
    await matcher.finish(Message(f"褰撳墠娆㈣繋宸瞷status}\n") + _render_welcome_content(key, content_str))


enable_welcome = P.on_regex(
    r"^(?:#)?寮€鍚杩?", display_name="寮€鍚杩?, name="enable", block=True, priority=5
)


@enable_welcome.handle()
async def _(matcher: Matcher, event: MessageEvent):
    key = _get_group_key(event)
    if not key:
        await matcher.finish("璇峰湪缇よ亰涓娇鐢ㄨ鍛戒护")
    store = _load_store()
    rec = store.get(key) or {}
    rec["enabled"] = True
    store[key] = rec
    _save_store(store)
    await matcher.finish("宸插紑鍚湰缇ゆ杩?)


disable_welcome = P.on_regex(
    r"^(?:#)?鍏抽棴娆㈣繋$", display_name="鍏抽棴娆㈣繋", name="disable", block=True, priority=5
)


@disable_welcome.handle()
async def _(matcher: Matcher, event: MessageEvent):
    key = _get_group_key(event)
    if not key:
        await matcher.finish("璇峰湪缇よ亰涓娇鐢ㄨ鍛戒护")
    store = _load_store()
    rec = store.get(key) or {}
    rec["enabled"] = False
    store[key] = rec
    _save_store(store)
    await matcher.finish("宸插叧闂湰缇ゆ杩?)


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
    await welcome_notice.finish(at + Message(" ") + _render_welcome_content(key, content_str))








