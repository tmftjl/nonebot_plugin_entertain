from __future__ import annotations
from ...core.constants import DEFAULT_HTTP_TIMEOUT


import asyncio
import json
import re
import secrets
from typing import Any, Dict, List, Optional, Tuple

import httpx
from nonebot import get_driver, logger, on_notice
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
    GroupMessageEvent,
    PrivateMessageEvent,
    PokeNotifyEvent,
)

from ...core.api import Plugin, plugin_data_dir
from .config import load_cfg, face_list, random_local_image


driver = get_driver()
_updating_gallery = False
from . import update_gallery as update_gallery  # 娉ㄥ唽鏇存柊鍛戒护

# 鏉冮檺鍖呰涓庨粯璁ゅ懡浠ら」
P = Plugin(name="df", display_name="DF")
# ---------- 宸ュ叿鍑芥暟 ----------


def _api_handlers() -> List[Tuple[str, Any]]:
    handlers: List[Tuple[str, Any]] = []
    cfg = load_cfg()
    api_urls = cfg.get("api_urls", {})
    timeout = DEFAULT_HTTP_TIMEOUT

    # jk 鍥?
    jk_url = str(api_urls.get("jk_api", "https://api.suyanw.cn/api/jk.php"))
    handlers.append((r"jk(?:鍥??", lambda: MessageSegment.image(jk_url)))

    async def _hs():
        # 榛戜笣
        hs_url = "https://api.suyanw.cn/api/hs.php"  # 鏆傛椂淇濈暀纭紪鐮?鍙互鍚庣画娣诲姞鍒伴厤缃?
        return Message(MessageSegment.text("榛戜笣鏉ュ挴") + MessageSegment.image(hs_url))

    handlers.append((r"榛戜笣", _hs))

    async def _bs():
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            r = await client.get("https://v2.api-m.com/api/baisi")
            r.raise_for_status()
            link = r.text.replace("\\", "/")
        return Message(MessageSegment.text("鐧戒笣鏉ュ挴~") + MessageSegment.image(link))

    handlers.append((r"鐧戒笣", _bs))

    async def _cos():
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            r = await client.get("https://api.suyanw.cn/api/cos.php?type=json")
            link = r.text.replace("\\", "/")
        return Message(MessageSegment.text("COS 鏉ュ挴~") + MessageSegment.image(link))

    handlers.append((r"cos", _cos))

    async def _leg():
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            r = await client.get("https://api.suyanw.cn/api/meitui.php")
            m = re.search(r"https?://[^ ]+", r.text)
            link = m.group(0) if m else ""
        return Message(MessageSegment.text("缇庤吙鏉ュ挴~") + (MessageSegment.image(link) if link else MessageSegment.text("")))

    handlers.append((r"(?:鑵縷缇庤吙)", _leg))

    return handlers


def _build_picture_regex() -> re.Pattern:
    regs = [r for r, _ in _api_handlers()]
    # 瑙﹀彂璇嶏細鏉ュ紶/鐪嬬湅/闅忔満 + 鐩爣
    pattern = rf"^#?(?:鏉ュ紶|鐪嬬湅|闅忔満)({'|'.join(regs)})$"
    return re.compile(pattern, re.I)


def _pick_face_image(name: str) -> MessageSegment:
    p = random_local_image(name)
    if p is not None:
        return MessageSegment.image(p.read_bytes())

    # 浣跨敤閰嶇疆涓殑澶囩敤API
    cfg = load_cfg()
    api_urls = cfg.get("api_urls", {})
    fallback_template = str(api_urls.get("fallback_api", "https://ciallo.hxxn.cc/?name={name}"))
    fallback_url = fallback_template.format(name=name)
    return MessageSegment.image(fallback_url)


async def _hitokoto(api: str) -> Optional[str]:
    cfg = load_cfg()

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            r = await client.get(api)
            r.raise_for_status()
            return r.text.strip()
    except Exception as e:
        logger.debug(f"hitokoto error: {e}")
        return None


# ---------- 闅忔満鍥剧墖 ----------

_PIC = P.on_regex(
    _build_picture_regex(),
    name="pictures_api",
    display_name="鐪嬬湅鑵?,
    priority=5,
    block=True,
)


@_PIC.handle()
async def _(matcher: Matcher, event: MessageEvent):
    cfg = load_cfg()
    if not cfg.get("random_picture_open", True):
        await matcher.finish()
    m = _build_picture_regex().match(str(event.get_message()))
    if not m:
        await matcher.finish()
    t = m.group(1).lower()
    for reg, fn in _api_handlers():
        if re.fullmatch(reg, t, re.I):
            res = fn()
            if asyncio.iscoroutine(res):
                res = await res  # type: ignore
            if isinstance(res, Message):
                await matcher.finish(res)
            else:
                await matcher.finish(Message(res))
    await matcher.finish()


# 鏈湴鍥惧簱锛氭潵寮?鐪嬬湅/闅忔満 + 鍚嶇О锛堜紭鍏堜簬澶栭儴API锛?
_LOCAL_PIC = P.on_regex(
    r"^#?(?:鏉ュ紶|鐪嬬湅|闅忔満)\s*(\S+)$",
    name="pictures_local",
    priority=5,
    block=False,
    display_name="闅忔満鏈湴琛ㄦ儏",
)


@_LOCAL_PIC.handle()
async def _(matcher: Matcher, event: MessageEvent):
    cfg = load_cfg()
    if not cfg.get("random_picture_open", True):
        return
    m = re.match(r"^#?(?:鏉ュ紶|鐪嬬湅|闅忔満)\s*(\S+)$", str(event.get_message()))
    if not m:
        return
    name = m.group(1)
    if name in face_list():
        await matcher.finish(Message(_pick_face_image(name)))


_LIST = P.on_regex(
    r"^#?DF(?:闅忔満)?琛ㄦ儏鍖呭垪琛?",
    priority=5,
    block=True,
    name="pictures_list",
    display_name="闅忔満琛ㄦ儏鍒楄〃",
)


@_LIST.handle()
async def _(matcher: Matcher):
    faces = face_list()
    text = "琛ㄦ儏鍒楄〃锛歕n" + ("銆?.join(faces) or "(绌?") + "\n\n浣跨敤 #闅忔満<鍚嶇О>"
    await matcher.finish(text)


# ---------- 鎴充竴鎴?----------

_POKE = on_notice(priority=12, block=False, permission=P.permission_cmd("poke"))


@_POKE.handle()
async def _(bot: Bot, event: PokeNotifyEvent):  # type: ignore[override]
    full_cfg = load_cfg()
    cfg = full_cfg.get("poke", {})
    if not bool(cfg.get("chuo", True)):
        return
    try:
        if str(getattr(event, "target_id", "")) != str(event.self_id):
            return
    except Exception:
        return

    mode = str(cfg.get("mode", "random")).lower()
    if mode == "random":
        mode = __import__("random").choice(["image", "text", "mix"])  # type: ignore

    msg_parts: List[MessageSegment] = []

    if mode in ("image", "mix"):
        image_type = str(cfg.get("imageType", "all")).lower()
        faces = face_list()
        black = set(map(str, cfg.get("imageBlack", []) or []))
        if image_type == "all":
            pool = [x for x in faces if x not in black] or faces
            name = __import__("random").choice(pool) if pool else "default"
        else:
            name = image_type
        msg_parts.append(_pick_face_image(name))

    if mode in ("text", "mix"):
        text_mode = str(cfg.get("textMode", "hitokoto")).lower()
        text_list = list(cfg.get("textList", []) or [])
        text: Optional[str] = None
        if text_mode == "hitokoto":
            api = str(cfg.get("hitokoto_api", "https://v1.hitokoto.cn/?encode=text"))
            text = await _hitokoto(api)
        elif text_mode == "list" and text_list:
            text = __import__("random").choice(text_list)
        if text:
            msg_parts.insert(0, MessageSegment.text(text))

    if msg_parts:
        await bot.send(event, Message(msg_parts))


# ---------- 鑱旂郴涓讳汉 ----------

CONTACT_FILE = plugin_data_dir("df") / "contact_index.json"


def _load_contact() -> Dict[str, Any]:
    try:
        return json.loads(CONTACT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_contact(data: Dict[str, Any]) -> None:
    try:
        CONTACT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


_CONTACT = P.on_regex(
    r"^#鑱旂郴涓讳汉",
    priority=5,
    block=True,
    name="contact",
    display_name="鑱旂郴涓讳汉",
)


@_CONTACT.handle()
async def _(matcher: Matcher, bot: Bot, event: MessageEvent):
    cfg = load_cfg()
    if not cfg.get("send_master", {}).get("open", True):
        await matcher.finish("璇ュ姛鑳芥湭寮€鍚?)

    plain = str(event.get_message()).replace("#鑱旂郴涓讳汉", "", 1).strip()
    if not plain:
        await matcher.finish("淇℃伅涓嶈兘涓虹┖")

    try:
        su = {str(x) for x in getattr(get_driver().config, "superusers", set())}
    except Exception:
        su = set()

    if not su:
        await matcher.finish("鏈厤缃秴绾х敤鎴凤紝鏃犳硶鑱旂郴涓讳汉")

    msg_id = secrets.token_hex(3)

    scene = "绉佽亰" if isinstance(event, PrivateMessageEvent) else "缇よ亰"
    user = f"{getattr(event, 'sender', None) and getattr(event.sender, 'nickname', '')}({getattr(event, 'user_id', '')})"
    group = "绉佽亰"
    if isinstance(event, GroupMessageEvent):
        try:
            group = f"{getattr(event, 'group_id', '')}"
        except Exception:
            group = "缇よ亰"

    text = (
        f"鑱旂郴涓讳汉鐨勪俊鎭?{msg_id})\n"
        f"骞冲彴: onebot.v11\n"
        f"鐢ㄦ埛: {user}\n"
        f"鍦烘櫙: {scene} {group}\n"
        f"鍐呭: {plain}"
    )

    data = _load_contact()
    data[msg_id] = {
        "self_id": str(event.self_id),
        "group_id": str(getattr(event, "group_id", "")) if isinstance(event, GroupMessageEvent) else "",
        "user_id": str(getattr(event, "user_id", "")),
    }
    _save_contact(data)

    ok = 0
    for uid in su:
        try:
            await bot.send_private_msg(user_id=int(uid), message=text)
            ok += 1
        except Exception as e:
            logger.warning(f"Failed to send to superuser {uid}: {e}")

    if ok:
        await matcher.finish(cfg.get("send_master", {}).get("success", "宸插皢淇℃伅杞彂缁欎富浜?))
    else:
        await matcher.finish(cfg.get("send_master", {}).get("failed", "鍙戦€佸け璐ワ紝璇风◢鍚庨噸璇?))


_REPLY = P.on_regex(
    r"^#鍥炲(\S+)\s+([\s\S]+)$",
    priority=5,
    block=True,
    name="reply",
    display_name="鍥炲",
)


@_REPLY.handle()
async def _(matcher: Matcher, bot: Bot, event: PrivateMessageEvent):
    cfg = load_cfg()
    m = re.match(r"^#?鍥炲(\S+)\s+([\s\S]+)$", str(event.get_message()))
    if not m:
        await matcher.finish()
    rid, content = m.group(1), m.group(2)
    data = _load_contact()
    rec = data.get(rid)
    if not rec:
        await matcher.finish("娑堟伅宸茶繃鏈熸垨涓嶅瓨鍦?)
    try:
        gid = rec.get("group_id")
        uid = rec.get("user_id")
        reply_prefix = cfg.get("send_master", {}).get("reply_prefix", "涓讳汉鍥炲锛?)
        if gid:
            await bot.send_group_msg(group_id=int(gid), message=MessageSegment.text(reply_prefix) + MessageSegment.text(content))
        elif uid:
            await bot.send_private_msg(user_id=int(uid), message=MessageSegment.text(reply_prefix) + MessageSegment.text(content))
        await matcher.finish("娑堟伅宸插彂閫?)
    except Exception as e:
        logger.error(f"鍥炲娑堟伅鏃跺彂鐢熷紓甯? {e}")
        await matcher.finish("鎿嶄綔澶辫触锛岃鏌ョ湅鎺у埗鍙版棩蹇?)













