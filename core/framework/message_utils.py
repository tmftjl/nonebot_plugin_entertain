from __future__ import annotations

from typing import Any, List, Optional
from dataclasses import dataclass, field

from nonebot.log import logger

try:  # pragma: no cover - import at runtime in bot environment
    from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
except Exception:  # pragma: no cover - allow static analysis
    Bot = Any  # type: ignore
    Message = Any  # type: ignore
    MessageEvent = Any  # type: ignore


def get_target_message_id(event: MessageEvent) -> Optional[int]:
    """尽可能从事件中获取被回复消息的 message_id。

    优先顺序：
    1) event.reply.message_id（部分实现只在这里提供）
    2) event.message 中的 reply 段 id
    3) 从字符串形态解析 [reply:id=xxxx]
    """
    # 1) event.reply
    try:
        reply = getattr(event, "reply", None)
        if reply:
            mid = None
            if hasattr(reply, "message_id"):
                mid = getattr(reply, "message_id", None)
            elif hasattr(reply, "id"):
                mid = getattr(reply, "id", None)
            if mid is None and isinstance(reply, dict):
                mid = reply.get("message_id") or reply.get("id")
            if mid:
                try:
                    return int(mid)
                except Exception:  # pragma: no cover - best effort cast
                    pass
            # Fallback: parse from string
            try:  # pragma: no cover - string fallback
                import re as _re

                m = _re.search(r"(message_id|id)\D*(\d+)", str(reply))
                if m:
                    return int(m.group(2))
            except Exception:
                pass
    except Exception:
        pass

    # 2) reply segment in event.message
    try:
        for seg in event.message:  # type: ignore[union-attr]
            if getattr(seg, "type", None) == "reply":
                mid = (getattr(seg, "data", None) or {}).get("id")
                if mid is not None:
                    return int(mid)
    except Exception:
        pass

    # 3) Parse from string form [reply:id=xxxx]
    try:
        import re as _re

        s = str(getattr(event, "message", ""))
        m = _re.search(r"\[reply:(?:id=)?(\d+)\]", s)
        if not m:
            m = _re.search(r"\[reply\s*,?\s*id=(\d+)\]", s)
        if m:
            return int(m.group(1))
    except Exception:
        pass

    return None


async def fetch_replied_message(bot: Bot, event: MessageEvent) -> Optional[Message]:
    """获取被回复的消息内容（Message 对象），若不可用则返回 None。"""
    try:
        mid = get_target_message_id(event)
        if not mid:
            return None
        data = await bot.get_msg(message_id=mid)  # type: ignore[arg-type]
        raw = data.get("message") if isinstance(data, dict) else None
        if raw is None:
            return None
        # 若 raw 不是 Message，则尽力转为 Message
        try:
            from nonebot.adapters.onebot.v11 import Message as _Msg  # local import

            if isinstance(raw, _Msg):
                return raw
            return _Msg(raw)
        except Exception:
            return raw  # type: ignore[return-value]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"fetch_replied_message failed: {e}")
        return None


async def extract_image_sources_with_bot(bot: Bot, msg: Message) -> List[str]:
    """从消息段提取图片来源（url 或通过 get_image 解析的本地路径）。"""
    out: List[str] = []
    try:
        for seg in msg:
            seg_dict: dict
            if isinstance(seg, dict):
                seg_dict = seg
            elif hasattr(seg, "dict") and callable(getattr(seg, "dict")):
                try:
                    seg_dict = seg.dict()
                except Exception as e:
                    logger.debug(f"seg.dict() failed: {e}")
                    continue
            elif hasattr(seg, "__dict__"):
                seg_dict = vars(seg)
            else:
                logger.debug(f"unknown segment type: {type(seg)}")
                continue

            if seg_dict.get("type") != "image":
                continue
            data = seg_dict.get("data") or {}
            url = str((data.get("url") or "")).strip()
            if url:
                out.append(url)
                continue
            file_ = str((data.get("file") or "")).strip()
            if file_:
                # 使用 OneBot get_image API 将文件 id 转换为实际路径
                try:
                    resp = await bot.get_image(file=file_)  # type: ignore[arg-type]
                    path = resp.get("file") if isinstance(resp, dict) else None
                    if path:
                        out.append(str(path))
                        continue
                except Exception:
                    # 兜底：直接当成本地路径尝试
                    out.append(file_)
    except Exception as e:
        logger.debug(f"extract_image_sources_with_bot failed: {e}")

    return out


async def get_images_from_event_or_reply(
    bot: Bot, event: MessageEvent, *, include_current: bool = True
) -> List[str]:
    """优先从当前消息取图；没有则尝试从被引用的消息中取图。"""
    # 1) 当前消息
    if include_current:
        try:
            current = await extract_image_sources_with_bot(bot, event.get_message())
            if current:
                return current
        except Exception:
            pass

    # 2) 被回复消息
    try:
        replied = await fetch_replied_message(bot, event)
        if replied:
            return await extract_image_sources_with_bot(bot, replied)
    except Exception:
        pass
    return []


def extract_plain_text(msg: Message, *, strip: bool = True) -> str:
    """提取消息中的纯文本内容（忽略 CQ 码）。"""
    try:
        # OneBot v11 Message 提供 extract_plain_text
        text = msg.extract_plain_text()  # type: ignore[attr-defined]
        return text.strip() if strip else text
    except Exception:
        pass

    # Fallback: 拼接 text 段
    texts: List[str] = []
    try:
        for seg in msg:
            if getattr(seg, "type", None) == "text":
                t = (getattr(seg, "data", None) or {}).get("text") or ""
                texts.append(str(t))
    except Exception:
        return str(msg).strip() if strip else str(msg)
    joined = "".join(texts)
    return joined.strip() if strip else joined


async def get_reply_text(bot: Bot, event: MessageEvent) -> Optional[str]:
    """获取被回复消息的纯文本（若不可用返回 None）。"""
    try:
        replied = await fetch_replied_message(bot, event)
        if not replied:
            return None
        text = extract_plain_text(replied)
        return text if text else None
    except Exception:
        return None


async def get_chat_history(
    bot: Bot, event: MessageEvent, *, count: int = 10
) -> List[dict]:
    """尽力获取最近的群聊消息记录（仅在适配器支持时生效）。

    返回为底层适配器字典（如 go-cqhttp 的消息结构）。在不支持的环境下返回空列表。
    """
    # 仅尝试群聊
    try:
        group_id = getattr(event, "group_id", None)
        if not group_id:
            return []

        # 获取 message_seq（如果可用）
        message_seq: Optional[int] = getattr(event, "message_seq", None)
        if message_seq is None:
            try:
                detail = await bot.get_msg(message_id=getattr(event, "message_id", 0))  # type: ignore[arg-type]
                if isinstance(detail, dict):
                    message_seq = detail.get("message_seq")
            except Exception:
                pass

        params = {"group_id": group_id, "count": int(count)}
        if message_seq:
            # 从当前消息之前开始获取
            params["message_seq"] = int(message_seq) - 1

        try:
            data = await bot.call_api("get_group_msg_history", **params)  # type: ignore[arg-type]
            # go-cqhttp: {"messages": [...]} 或 {"data": {"messages": [...]}}
            if isinstance(data, dict):
                if "messages" in data and isinstance(data["messages"], list):
                    return list(data["messages"])[:count]
                if "data" in data and isinstance(data["data"], dict):
                    msgs = data["data"].get("messages")
                    if isinstance(msgs, list):
                        return list(msgs)[:count]
        except Exception as e:  # noqa: BLE001
            logger.debug(f"get_group_msg_history not available: {e}")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_chat_history failed: {e}")
    return []


# ===== 汇总获取：文本 / 图片 / 转发聊天记录 =====

@dataclass
class ReplyBundle:
    """被回复消息的汇总结果对象。

    字段：
    - message_id: 被回复消息的 ID（若无法解析则为 None）
    - message: 被回复消息的 Message 对象（若获取失败为 None）
    - text: 从被回复消息中提取的纯文本（可能为 None）
    - images: 从被回复消息中提取的图片来源（URL 或本地路径）
    - forward_id: 若被回复消息为“转发消息”，则为转发 id
    - forward_nodes: 通过 get_forward_msg 获取到的节点列表
    """

    message_id: Optional[int] = None
    message: Optional[Message] = None
    text: Optional[str] = None
    images: List[str] = field(default_factory=list)
    forward_id: Optional[str] = None
    forward_nodes: List[dict] = field(default_factory=list)


def _extract_forward_id_from_message(msg: Any) -> Optional[str]:
    """从 Message 或字符串中尽力解析转发 id。"""
    # 1) Message 段解析
    try:
        for seg in msg:  # OneBot v11 Message 可迭代
            t = getattr(seg, "type", None)
            if t == "forward":
                data = getattr(seg, "data", None) or {}
                fid = data.get("id")
                if fid:
                    return str(fid)
    except Exception:
        pass

    # 2) 字符串兜底解析（CQ/str 形态）
    try:
        s = str(msg)
        import re as _re

        # 常见形态：[CQ:forward,id=xxxx] 或 [forward:id=xxxx]
        for pat in [
            r"\[CQ:forward,id=([A-Za-z0-9_\-+=/]+)\]",
            r"\[forward(?::|,)?(?:id=)?([A-Za-z0-9_\-+=/]+)\]",
            r"(?:forward_id|id)\D*([A-Za-z0-9_\-+=/]{5,})",
        ]:
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
            # go-cqhttp 常见：{"messages": [...]} 或 {"data": {"messages": [...]}}
            if isinstance(data.get("messages"), list):
                return list(data["messages"])
            d = data.get("data")
            if isinstance(d, dict) and isinstance(d.get("messages"), list):
                return list(d["messages"])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_forward_msg failed: {e}")
    return []


async def get_reply_bundle(bot: Bot, event: MessageEvent) -> ReplyBundle:
    """获取被回复消息的文本、图片与（如有）转发聊天记录。"""
    bundle = ReplyBundle()

    # 解析被回复的 message_id
    try:
        bundle.message_id = get_target_message_id(event)
    except Exception:
        bundle.message_id = None

    # 获取被回复的 Message 对象
    try:
        if bundle.message_id is not None:
            bundle.message = await fetch_replied_message(bot, event)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_reply_bundle.fetch_replied_message failed: {e}")
        bundle.message = None

    # 提取纯文本
    try:
        if bundle.message:
            text = extract_plain_text(bundle.message)
            bundle.text = text if text else None
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_reply_bundle.extract_plain_text failed: {e}")

    # 提取图片来源
    try:
        if bundle.message:
            bundle.images = await extract_image_sources_with_bot(bot, bundle.message)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_reply_bundle.extract_image_sources_with_bot failed: {e}")

    # 提取“转发聊天记录”
    # 1) 先从被回复的 Message 段里找 forward 段
    try:
        if bundle.message:
            bundle.forward_id = _extract_forward_id_from_message(bundle.message)
    except Exception:
        pass

    # 2) 若未获取到，回查 get_msg 返回体再解析一次
    try:
        if not bundle.forward_id and bundle.message_id is not None:
            raw = await bot.get_msg(message_id=bundle.message_id)
            if isinstance(raw, dict):
                # 直接字段或从 message 字段解析
                bundle.forward_id = (
                    str(raw.get("forward_id"))
                    if raw.get("forward_id")
                    else _extract_forward_id_from_message(raw.get("message"))
                    or _extract_forward_id_from_message(str(raw))
                )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_reply_bundle.get_msg for forward failed: {e}")

    # 3) 有 forward_id 则取节点列表
    try:
        if bundle.forward_id:
            bundle.forward_nodes = await _get_forward_nodes_by_id(bot, bundle.forward_id)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_reply_bundle.get_forward_nodes failed: {e}")

    return bundle

