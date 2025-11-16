from __future__ import annotations

import re
import logging
from typing import Any, List, Optional, Union
from dataclasses import dataclass, field

try:  # 运行时环境提供
    from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
except Exception:  # 静态工具/检查场景
    Bot = Any  # type: ignore
    Message = Any  # type: ignore
    MessageEvent = Any  # type: ignore
    MessageSegment = Any  # type: ignore

log = logging.getLogger(__name__)

# ===== 预编译正则表达式 =====
_RE_REPLY_CQ = re.compile(r"\[CQ:reply,id=(\d+)\]")
_RE_REPLY_GENERIC = re.compile(r"\[reply(?::|,)?id=(\d+)\]")

_RE_FWD_CQ = re.compile(r"\[CQ:forward,id=([A-Za-z0-9_\-+=/]+)\]")
_RE_FWD_GENERIC = re.compile(r"\[forward(?::|,)?(?:id=)?([A-Za-z0-9_\-+=/]+)\]")
_RE_FWD_JSON = re.compile(r"(?:forward_id|id)\D*([A-Za-z0-9_\-+=/]{5,})")


# ===== 基础工具 =====

def _safe_int(x: Any) -> Optional[int]:
    """安全地将输入转换为整数，失败则返回 None。"""
    try:
        return int(x)
    except (ValueError, TypeError, Exception):
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
    except Exception as e:
        log.debug(f"Error in _iter_message_segments_as_dicts: {e}")
        pass
    return segs


# ===== reply 解析与获取 =====

def get_target_message_id(event: MessageEvent) -> Optional[int]:
    """尽力从事件中获取被回复消息的 message_id。"""
    # 1) event.reply.*
    reply = getattr(event, "reply", None)
    if reply:
        mid_val = getattr(reply, "message_id", getattr(reply, "id", None))
        mid = _safe_int(mid_val)
        if mid is not None:
            return mid
        if isinstance(reply, dict):
            mid = _safe_int(reply.get("message_id") or reply.get("id"))
            if mid is not None:
                return mid
        try:
            m = re.search(r"(message_id|id)\D*(\d+)", str(reply))
            if m:
                return int(m.group(2))
        except Exception:
            pass

    # 2) 在 event.message 的 reply 段内
    for seg in getattr(event, "message", []):
        if getattr(seg, "type", None) == "reply":
            data = getattr(seg, "data", {})
            mid = _safe_int(data.get("id"))
            if mid is not None:
                return mid

    # 3) 字符串形式 [reply:id=xxxx]
    try:
        s = str(getattr(event, "message", ""))
        m = _RE_REPLY_CQ.search(s) or _RE_REPLY_GENERIC.search(s)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    
    return None


async def fetch_replied_message(bot: Bot, event: MessageEvent) -> Optional[Message]:
    """根据事件读取被回复消息，返回 Message；失败返回 None。"""
    mid = get_target_message_id(event)
    if not mid:
        return None
    
    try:
        data = await bot.get_msg(message_id=mid)
    except Exception as e:
        log.warning(f"Failed to call bot.get_msg(message_id={mid}): {e}")
        return None

    raw_msg = data.get("message") if isinstance(data, dict) else None
    if raw_msg is None:
        return None

    try:
        return raw_msg if isinstance(raw_msg, Message) else Message(raw_msg)
    except Exception:
        return raw_msg


# ===== 图片与文本提取 =====

async def extract_image_sources_with_bot(bot: Bot, msg: Message) -> List[str]:
    """从消息中提取图片来源：优先 url，其次 get_image 转换的本地路径/临时路径。"""
    out: List[str] = []
    segs = _iter_message_segments_as_dicts(msg)
    
    for seg in segs:
        if seg.get("type") != "image":
            continue
        
        data = seg.get("data") or {}
        url = str(data.get("url") or "").strip()
        if url:
            out.append(url)
            continue
        
        file_ = str(data.get("file") or "").strip()
        if file_:
            try:
                resp = await bot.get_image(file=file_)
                path = resp.get("file") if isinstance(resp, dict) else None
                if path:
                    out.append(str(path))
                    continue
            except Exception as e:
                log.warning(f"Failed to call bot.get_image(file={file_}): {e}")
                pass
            out.append(file_)
    return out


async def get_images_from_event_or_reply(bot: Bot, event: MessageEvent) -> List[str]:
    """【兼容函数】优先从当前消息取图，否则尝试从被回复消息取图。"""
    try:
        cur_msg = event.get_message()
        cur = await extract_image_sources_with_bot(bot, cur_msg)
        if cur:
            return cur
    except Exception:
        pass

    replied_msg = await fetch_replied_message(bot, event)
    if replied_msg:
        try:
            return await extract_image_sources_with_bot(bot, replied_msg)
        except Exception as e:
            log.warning(f"Error extracting images from replied message: {e}")
            pass
            
    return []


def extract_plain_text(msg: Message) -> str:
    """提取可读文本：拼接 text 与 at 段（@渲染为 @user_id）。"""
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
    return "".join(parts).strip()

# ===== 转发解析辅助 =====

def _extract_forward_id_from_message(msg: Any) -> Optional[str]:
    """从 Message 或字符串中尽力解析转发 id。"""
    segs = _iter_message_segments_as_dicts(msg)
    for seg in segs:
        if seg.get("type") == "forward":
            data = seg.get("data") or {}
            fid = str((data.get("id") or data.get("forward_id") or "")).strip()
            if fid:
                return fid
    
    try:
        s = str(msg)
        m = _RE_FWD_CQ.search(s) or _RE_FWD_GENERIC.search(s) or _RE_FWD_JSON.search(s)
        if m:
            return m.group(1)
    except Exception:
        pass
        
    return None


async def _get_forward_nodes_by_id(bot: Bot, forward_id: str) -> List[dict]:
    """调用 get_forward_msg 获取转发节点列表。"""
    if not forward_id:
        return []
    try:
        data = await bot.call_api("get_forward_msg", id=forward_id)
    except Exception as e:
        log.warning(f"Failed to call bot.get_forward_msg(id={forward_id}): {e}")
        return []

    if not isinstance(data, dict):
        return []

    messages = data.get("messages")
    if isinstance(messages, list):
        return messages
    
    d = data.get("data")
    if isinstance(d, dict):
        messages = d.get("messages")
        if isinstance(messages, list):
            return messages
            
    return []

async def get_enhance_message_byId(message_id: int) -> EnhanceMessage:
    data = await bot.get_msg(message_id=mid)


@dataclass
class EnhanceMessage:
    """消息打包结构"""
    message_id: Optional[int] = None
    message: Optional[Message] = None
    text: Optional[str] = None
    images: List[str] = field(default_factory=list)
    forward_id: Optional[str] = None
    forward_nodes: List[dict] = field(default_factory=list)
    reply: EnhanceMessage

# 获取增强消息
async def get_enhance_message(
    bot: Bot,
    event: MessageEvent,
) -> EnhanceMessage:
    """
    【推荐】一次性获取当前和被回复的消息打包。
    自动获取所有信息 (文本, 图片, 转发, @提及)。
    """
    cur: Optional[EnhanceMessage] = None
    rep: Optional[EnhanceMessage] = None
    
    # 获取当前消息
    mid = _safe_int(getattr(event, "message_id", None))
    msg = event.get_message()
    
    # 1.2 解析消息
    enhance_message = get_enhance_message_byId(message_id=mid)
    bundle = EnhanceMessage(message_id=mid, message=msg)
    if msg is not None:
        bundle.text = extract_plain_text(msg)
        bundle.images = await extract_image_sources_with_bot(bot, msg)
        
        bundle.forward_id = _extract_forward_id_from_message(msg)
        if bundle.forward_id:
            bundle.forward_nodes = await _get_forward_nodes_by_id(
                bot, bundle.forward_id
            )
    
    cur = bundle

    # 2. ===== 获取被回复消息 (内联逻辑) =====
    try:
        mid: Optional[int] = None
        msg: Optional[Message] = None
        
        # 2.1 查找消息
        msg = await fetch_replied_message(bot, event)
        if msg:
            mid = get_target_message_id(event)
        
        # 2.2 解析消息
        bundle = EnhanceMessage(source=source, message_id=mid, message=msg)
        if msg is not None:
            bundle.text = extract_plain_text(msg)
            bundle.images = await extract_image_sources_with_bot(bot, msg)
            
            bundle.forward_id = _extract_forward_id_from_message(msg)
            if not bundle.forward_id and mid is not None:
                try:
                    raw = await bot.get_msg(message_id=mid)
                    if isinstance(raw, dict):
                        fid = raw.get("forward_id") or _extract_forward_id_from_message(
                            raw.get("message")
                        )
                        if fid:
                            bundle.forward_id = str(fid)
                except Exception:
                    pass
            if bundle.forward_id:
                bundle.forward_nodes = await _get_forward_nodes_by_id(
                    bot, bundle.forward_id
                )
            
            # bundle.mentions 保持为空 (被回复消息不解析@)
        
        # 只有当被回复消息确实存在时才赋值
        if bundle.message is not None or bundle.message_id is not None:
            rep = bundle
            
    except Exception as e:
        log.error(f"Error getting reply message bundle: {e}", exc_info=True)
    cur.reply = rep
    return cur