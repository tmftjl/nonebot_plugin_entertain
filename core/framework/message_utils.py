from __future__ import annotations

from typing import Any, List, Optional
from dataclasses import dataclass, field

try:  # 运行时环境提供
    from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
except Exception:  # 静态工具/检查场景
    Bot = Any  # type: ignore
    Message = Any  # type: ignore
    MessageEvent = Any  # type: ignore


# ===== 基础工具 =====

def _safe_int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None


def _iter_message_segments_as_dicts(msg: Any) -> List[dict]:
    """将 Message 或由其组成的对象迭代为 dict 段列表。"""
    segs: List[dict] = []
    try:
        for seg in (msg or []):
            if isinstance(seg, dict):
                segs.append(seg)
            elif hasattr(seg, "dict") and callable(getattr(seg, "dict")):
                try:
                    segs.append(seg.dict())  # type: ignore[attr-defined]
                except Exception:
                    try:
                        segs.append(vars(seg))
                    except Exception:
                        pass
            elif hasattr(seg, "__dict__"):
                try:
                    segs.append(vars(seg))
                except Exception:
                    pass
    except Exception:
        pass
    return segs


# ===== reply 解析与获取 =====

def get_target_message_id(event: MessageEvent) -> Optional[int]:
    """尽力从事件中获取被回复消息的 message_id。"""
    # 1) event.reply.*
    try:
        reply = getattr(event, "reply", None)
        if reply is not None:
            for key in ("message_id", "id"):
                if hasattr(reply, key):
                    mid = _safe_int(getattr(reply, key))
                    if mid is not None:
                        return mid
            if isinstance(reply, dict):
                for key in ("message_id", "id"):
                    mid = _safe_int(reply.get(key))
                    if mid is not None:
                        return mid
            try:
                import re as _re
                m = _re.search(r"(message_id|id)\D*(\d+)", str(reply))
                if m:
                    return int(m.group(2))
            except Exception:
                pass
    except Exception:
        pass

    # 2) 在 event.message 的 reply 段内
    try:
        for seg in getattr(event, "message", []):
            if getattr(seg, "type", None) == "reply":
                data = getattr(seg, "data", None) or {}
                mid = _safe_int((data.get("id") if isinstance(data, dict) else None))
                if mid is not None:
                    return mid
    except Exception:
        pass

    # 3) 字符串形式 [reply:id=xxxx]
    try:
        import re as _re
        s = str(getattr(event, "message", ""))
        for pat in (
            r"\[CQ:reply,id=(\d+)\]",
            r"\[reply(?::|,)?id=(\d+)\]",
        ):
            m = _re.search(pat, s)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None


async def fetch_replied_message(bot: Bot, event: MessageEvent) -> Optional[Message]:
    """根据事件读取被回复消息，返回 Message；失败返回 None。"""
    try:
        mid = get_target_message_id(event)
        if not mid:
            return None
        data = await bot.get_msg(message_id=mid)  # type: ignore[arg-type]
        raw = data.get("message") if isinstance(data, dict) else None
        if raw is None:
            return None
        try:
            from nonebot.adapters.onebot.v11 import Message as _Msg
            return raw if isinstance(raw, _Msg) else _Msg(raw)
        except Exception:
            return raw  # 尽力返回
    except Exception:
        return None


# ===== 图片与文本提取 =====

async def extract_image_sources_with_bot(bot: Bot, msg: Message) -> List[str]:
    """从消息中提取图片来源：优先 url，其次 get_image 转换的本地路径/临时路径。"""
    out: List[str] = []
    try:
        segs = _iter_message_segments_as_dicts(msg)
        for seg in segs:
            if seg.get("type") != "image":
                continue
            data = seg.get("data") or {}
            url = str((data.get("url") or "")).strip()
            if url:
                out.append(url)
                continue
            file_ = str((data.get("file") or "")).strip()
            if file_:
                try:
                    resp = await bot.get_image(file=file_)  # type: ignore[arg-type]
                    path = resp.get("file") if isinstance(resp, dict) else None
                    if path:
                        out.append(str(path))
                        continue
                except Exception:
                    pass
                # 回退：直接附上 file 字段
                out.append(file_)
    except Exception:
        pass
    return out


async def get_images_from_event_or_reply(bot: Bot, event: MessageEvent) -> List[str]:
    """优先从当前消息取图，否则尝试从被回复消息取图。"""
    try:
        cur = await extract_image_sources_with_bot(bot, event.get_message())
        if cur:
            return cur
    except Exception:
        pass
    try:
        mid = get_target_message_id(event)
        if not mid:
            return []
        data = await bot.get_msg(message_id=mid)  # type: ignore[arg-type]
        raw = data.get("message") if isinstance(data, dict) else None
        if raw is None:
            return []
        return await extract_image_sources_with_bot(bot, raw)
    except Exception:
        return []


async def extract_plain_text(bot: Bot, event: MessageEvent, msg: Message) -> str:
    """提取可读文本：拼接 text 与 at 段（@渲染为 @user_id），不做复杂查询。"""
    parts: List[str] = []
    segs = _iter_message_segments_as_dicts(msg)
    for seg in segs:
        t = seg.get("type")
        data = seg.get("data") or {}
        if t == "text":
            parts.append(str(data.get("text") or ""))
        elif t == "at":
            qq = str(data.get("qq") or "").strip()
            if qq:
                parts.append("@" + qq)
    res = "".join(parts)
    return res.strip()


# ===== @ 提及解析 =====

@dataclass
class AtInfo:
    user_id: str
    nickname: Optional[str] = None


async def extract_mentions(bot: Bot, event: MessageEvent) -> List[AtInfo]:
    """从事件的当前消息中提取 @ 信息。"""
    results: List[AtInfo] = []
    try:
        segs = _iter_message_segments_as_dicts(event.get_message())
        for seg in segs:
            if seg.get("type") != "at":
                continue
            data = seg.get("data") or {}
            uid = str(data.get("qq") or "").strip()
            if not uid:
                continue
            nickname = (str(data.get("name") or "").strip() or None)
            results.append(AtInfo(user_id=uid, nickname=nickname))
    except Exception:
        pass
    return results


# ===== 转发解析辅助 =====

def _extract_forward_id_from_message(msg: Any) -> Optional[str]:
    """从 Message 或字符串中尽力解析转发 id。"""
    try:
        segs = _iter_message_segments_as_dicts(msg)
        for seg in segs:
            if seg.get("type") == "forward":
                data = seg.get("data") or {}
                fid = str((data.get("id") or data.get("forward_id") or "")).strip()
                if fid:
                    return fid
    except Exception:
        pass
    try:
        s = str(msg)
        import re as _re
        for pat in (
            r"\[CQ:forward,id=([A-Za-z0-9_\-+=/]+)\]",
            r"\[forward(?::|,)?(?:id=)?([A-Za-z0-9_\-+=/]+)\]",
            r"(?:forward_id|id)\D*([A-Za-z0-9_\-+=/]{5,})",
        ):
            m = _re.search(pat, s)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


async def _get_forward_nodes_by_id(bot: Bot, forward_id: str) -> List[dict]:
    """调用 get_forward_msg 获取转发节点列表。"""
    try:
        data = await bot.call_api("get_forward_msg", id=forward_id)
        if isinstance(data, dict):
            if isinstance(data.get("messages"), list):
                return list(data["messages"])  # type: ignore[return-value]
            d = data.get("data")
            if isinstance(d, dict) and isinstance(d.get("messages"), list):
                return list(d["messages"])  # type: ignore[return-value]
    except Exception:
        pass
    return []


# ===== 通用打包，支持当前/被回复 =====

@dataclass
class MessageBundle:
    """消息打包结构，便于统一获取当前或被回复消息。"""
    source: str = "reply"  # 'current' | 'reply'
    message_id: Optional[int] = None
    message: Optional[Message] = None
    text: Optional[str] = None
    images: List[str] = field(default_factory=list)
    forward_id: Optional[str] = None
    forward_nodes: List[dict] = field(default_factory=list)
    mentions: List[AtInfo] = field(default_factory=list)
    reply: Optional["MessageBundle"] = None


async def get_message_bundle(
    bot: Bot,
    event: MessageEvent,
    *,
    source: str = "reply",  # 'current' | 'reply' | 'auto'
    want_text: bool = True,
    want_images: bool = True,
    want_forward: bool = True,
    want_mentions: bool = False,
    include_reply: bool = True,
) -> MessageBundle:
    """获取打包后的消息数据。"""
    chosen = source
    mid: Optional[int] = None
    msg: Optional[Message] = None

    # 选择源
    try:
        if source == "current":
            chosen = "current"
            mid = _safe_int(getattr(event, "message_id", None))
            try:
                msg = event.get_message()
            except Exception:
                msg = getattr(event, "message", None)
        elif source in ("reply", "auto"):
            mid = get_target_message_id(event)
            if mid:
                chosen = "reply"
                msg = await fetch_replied_message(bot, event)
            elif source == "auto":
                chosen = "current"
                mid = _safe_int(getattr(event, "message_id", None))
                try:
                    msg = event.get_message()
                except Exception:
                    msg = getattr(event, "message", None)
            else:
                chosen = "reply"
        else:
            # 非法 source 当作 reply 处理
            chosen = "reply"
            mid = get_target_message_id(event)
            if mid:
                msg = await fetch_replied_message(bot, event)
    except Exception:
        pass

    bundle = MessageBundle(source=chosen, message_id=mid, message=msg)

    # 解析
    if msg is not None:
        if want_text:
            try:
                bundle.text = await extract_plain_text(bot, event, msg)
            except Exception:
                pass
        if want_images:
            try:
                bundle.images = await extract_image_sources_with_bot(bot, msg)
            except Exception:
                pass
        if want_forward:
            try:
                bundle.forward_id = _extract_forward_id_from_message(msg)
                if not bundle.forward_id and chosen == "reply" and mid is not None:
                    # 兜底：通过 get_msg 的原始数据再试一次
                    try:
                        raw = await bot.get_msg(message_id=mid)  # type: ignore[arg-type]
                        if isinstance(raw, dict):
                            if raw.get("forward_id"):
                                bundle.forward_id = str(raw.get("forward_id"))
                            if not bundle.forward_id and raw.get("message") is not None:
                                bundle.forward_id = _extract_forward_id_from_message(raw.get("message"))
                            if not bundle.forward_id:
                                bundle.forward_id = _extract_forward_id_from_message(str(raw))
                    except Exception:
                        pass
                if bundle.forward_id:
                    bundle.forward_nodes = await _get_forward_nodes_by_id(bot, bundle.forward_id)
            except Exception:
                pass
        if want_mentions and chosen == "current":
            try:
                bundle.mentions = await extract_mentions(bot, event)
            except Exception:
                pass

    # 嵌套被回复消息（文本/图片/转发/提及）
    try:
        if chosen == "current" and include_reply:
            rid = get_target_message_id(event)
            if rid:
                bundle.reply = await get_message_bundle(
                    bot,
                    event,
                    source="reply",
                    want_text=want_text,
                    want_images=want_images,
                    want_forward=want_forward,
                    want_mentions=want_mentions,
                    include_reply=False,
                )
    except Exception:
        pass
    return bundle


# ===== 批量获取：当前 + 被回复 =====

@dataclass
class MessageBundles:
    current: Optional[MessageBundle] = None
    reply: Optional[MessageBundle] = None


async def get_message_bundles(
    bot: Bot,
    event: MessageEvent,
    *,
    include_current: bool = True,
    include_reply: bool = True,
    want_text: bool = True,
    want_images: bool = True,
    want_forward: bool = True,
    want_mentions: bool = False,
) -> MessageBundles:
    """一次性获取当前/被回复的消息打包。"""
    cur = None
    rep = None
    try:
        if include_current:
            cur = await get_message_bundle(
                bot,
                event,
                source="current",
                want_text=want_text,
                want_images=want_images,
                want_forward=want_forward,
                want_mentions=want_mentions,
            )
    except Exception:
        pass
    try:
        if include_reply:
            rep = await get_message_bundle(
                bot,
                event,
                source="reply",
                want_text=want_text,
                want_images=want_images,
                want_forward=want_forward,
                want_mentions=want_mentions,
            )
    except Exception:
        pass
    return MessageBundles(current=cur, reply=rep)


# 保留向后兼容的导出名
get_images_from_event_or_reply = get_images_from_event_or_reply
