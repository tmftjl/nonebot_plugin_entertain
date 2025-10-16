from __future__ import annotations

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
_cfg = load_cfg()
_updating_gallery = False
from . import update_gallery as update_gallery  # 注册更新命令

# 权限包装与默认命令项
P = Plugin(name="df", display_name="DF")
from ...core.api import upsert_command_defaults as _up_def
_up_def('df', 'poke')
for _c in ('pictures_local','pictures_face','pictures_list','contact','reply'):
    try:
        _up_def('df', _c)
    except Exception:
        pass


# ---------- 工具函数 ----------


def _api_handlers() -> List[Tuple[str, Any]]:
    handlers: List[Tuple[str, Any]] = []

    # jk 图
    handlers.append((r"jk(?:图)?", lambda: MessageSegment.image("https://api.suyanw.cn/api/jk.php")))

    async def _hs():
        # 黑丝
        return Message(MessageSegment.text("黑丝来咯") + MessageSegment.image("https://api.suyanw.cn/api/hs.php"))

    handlers.append((r"黑丝", _hs))

    async def _bs():
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://v2.api-m.com/api/baisi")
            r.raise_for_status()
            link = r.text.replace("\\", "/")
        return Message(MessageSegment.text("白丝来咯~") + MessageSegment.image(link))

    handlers.append((r"白丝", _bs))

    async def _cos():
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://api.suyanw.cn/api/cos.php?type=json")
            link = r.text.replace("\\", "/")
        return Message(MessageSegment.text("COS 来咯~") + MessageSegment.image(link))

    handlers.append((r"cos", _cos))

    async def _leg():
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://api.suyanw.cn/api/meitui.php")
            m = re.search(r"https?://[^ ]+", r.text)
            link = m.group(0) if m else ""
        return Message(MessageSegment.text("美腿来咯~") + (MessageSegment.image(link) if link else MessageSegment.text("")))

    handlers.append((r"(?:腿|美腿)", _leg))

    return handlers


def _build_picture_regex() -> re.Pattern:
    regs = [r for r, _ in _api_handlers()]
    # 触发词：来张/看看/随机 + 目标
    pattern = rf"^#?(?:来张|看看|随机)({'|'.join(regs)})$"
    return re.compile(pattern, re.I)


def _pick_face_image(name: str) -> MessageSegment:
    p = random_local_image(name)
    if p is not None:
        return MessageSegment.image(p.read_bytes())
    return MessageSegment.image(f"https://ciallo.hxxn.cc/?name={name}")


async def _hitokoto(api: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(api)
            r.raise_for_status()
            return r.text.strip()
    except Exception as e:
        logger.debug(f"hitokoto error: {e}")
        return None


# ---------- 随机图片 ----------

_PIC = P.on_regex(
    _build_picture_regex(),
    name="pictures_api",
    priority=12,
    block=True,
)


@_PIC.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if not _cfg.get("random_picture_open", True):
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


# 本地图库：来张/看看/随机 + 名称（优先于外部API）
_LOCAL_PIC = P.on_regex(
    r"^#?(?:来张|看看|随机)\s*(\S+)$",
    name="pictures_local",
    priority=12,
    block=False,
)


@_LOCAL_PIC.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if not _cfg.get("random_picture_open", True):
        return
    m = re.match(r"^#?(?:来张|看看|随机)\s*(\S+)$", str(event.get_message()))
    if not m:
        return
    name = m.group(1)
    if name in face_list():
        await matcher.finish(Message(_pick_face_image(name)))


# 表情：通用匹配，运行时校验
_FACE = P.on_regex(
    r"^#?(?:表情|表情包|表情图)(\S+)$",
    priority=12,
    block=False,
    name="pictures_face",
)


@_FACE.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if not _cfg.get("random_picture_open", True):
        return
    m = re.match(r"^#?(?:表情|表情包|表情图)(\S+)$", str(event.get_message()))
    if not m:
        return
    name = m.group(1)
    if name in face_list():
        await matcher.finish(Message(_pick_face_image(name)))


_LIST = P.on_regex(
    r"^#?DF(?:随机)?表情包列表$",
    priority=12,
    block=True,
    name="pictures_list",
)


@_LIST.handle()
async def _(matcher: Matcher):
    faces = face_list()
    text = "表情列表：\n" + ("、".join(faces) or "(空)") + "\n\n使用 #表情<名称>"
    await matcher.finish(text)


# ---------- 戳一戳 ----------

_POKE = on_notice(priority=12, block=False, permission=P.permission_cmd("poke"))


@_POKE.handle()
async def _(bot: Bot, event: PokeNotifyEvent):  # type: ignore[override]
    cfg = _cfg.get("poke", {})
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


# ---------- 联系主人 ----------

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
    r"^#?联系主人",
    priority=12,
    block=True,
    name="contact",
)


@_CONTACT.handle()
async def _(matcher: Matcher, bot: Bot, event: MessageEvent):
    if not _cfg.get("send_master", {}).get("open", True):
        await matcher.finish("该功能未开启")

    plain = str(event.get_message()).replace("#联系主人", "", 1).strip()
    if not plain:
        await matcher.finish("信息不能为空")

    try:
        su = {str(x) for x in getattr(get_driver().config, "superusers", set())}
    except Exception:
        su = set()

    if not su:
        await matcher.finish("未配置超级用户，无法联系主人")

    msg_id = secrets.token_hex(3)

    scene = "私聊" if isinstance(event, PrivateMessageEvent) else "群聊"
    user = f"{getattr(event, 'sender', None) and getattr(event.sender, 'nickname', '')}({getattr(event, 'user_id', '')})"
    group = "私聊"
    if isinstance(event, GroupMessageEvent):
        try:
            group = f"{getattr(event, 'group_id', '')}"
        except Exception:
            group = "群聊"

    text = (
        f"联系主人的信息({msg_id})\n"
        f"平台: onebot.v11\n"
        f"用户: {user}\n"
        f"场景: {scene} {group}\n"
        f"内容: {plain}"
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
        await matcher.finish(_cfg.get("send_master", {}).get("success", "已将信息转发给主人"))
    else:
        await matcher.finish(_cfg.get("send_master", {}).get("failed", "发送失败，请稍后重试"))


_REPLY = P.on_regex(
    r"^#?回复(\S+)\s+([\s\S]+)$",
    priority=12,
    block=True,
    name="reply",
)


@_REPLY.handle()
async def _(matcher: Matcher, bot: Bot, event: PrivateMessageEvent):
    m = re.match(r"^#?回复(\S+)\s+([\s\S]+)$", str(event.get_message()))
    if not m:
        await matcher.finish()
    rid, content = m.group(1), m.group(2)
    data = _load_contact()
    rec = data.get(rid)
    if not rec:
        await matcher.finish("消息已过期或不存在")
    try:
        gid = rec.get("group_id")
        uid = rec.get("user_id")
        if gid:
            await bot.send_group_msg(group_id=int(gid), message=MessageSegment.text(_cfg.get("send_master", {}).get("reply_prefix", "主人回复：")) + MessageSegment.text(content))
        elif uid:
            await bot.send_private_msg(user_id=int(uid), message=MessageSegment.text(_cfg.get("send_master", {}).get("reply_prefix", "主人回复：")) + MessageSegment.text(content))
        await matcher.finish("消息已发送")
    except Exception as e:
        logger.error(f"回复消息时发生异常: {e}")
        await matcher.finish("操作失败，请查看控制台日志")

