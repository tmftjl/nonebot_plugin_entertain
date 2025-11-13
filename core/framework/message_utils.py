from __future__ import annotations

from typing import Any, List, Optional, Set
from dataclasses import dataclass, field

from nonebot.log import logger

try:  # pragma: no cover - import at runtime in bot environment
    from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
except Exception:  # pragma: no cover - allow static analysis
    Bot = Any  # type: ignore
    Message = Any  # type: ignore
    MessageEvent = Any  # type: ignore


def _safe_int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None


def get_target_message_id(event: MessageEvent) -> Optional[int]:
    """尽可能从事件中获取被回复消息 message_id。

    优先顺序:
    1) event.reply.(message_id|id)
    2) event.message 中的 reply 段 data.id
    3) 字符串形态 [reply:id=xxxx]
    """
    # 1) event.reply
    try:
        reply = getattr(event, "reply", None)
        if reply is not None:
            # 对象 / 字典 两类常见实现
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
            # Fallback: 从字符串里匹配一遍
            try:  # pragma: no cover - best effort
                import re as _re

                m = _re.search(r"(message_id|id)\D*(\d+)", str(reply))
                if m:
                    return int(m.group(2))
            except Exception:
                pass
    except Exception:
        pass

    # 2) reply 段 in event.message
    try:
        for seg in getattr(event, "message", []):
            if getattr(seg, "type", None) == "reply":
                data = getattr(seg, "data", None) or {}
                mid = _safe_int(data.get("id"))
                if mid is not None:
                    return mid
    except Exception:
        pass

    # 3) 字符串兜底 [reply:id=xxxx]
    try:
        import re as _re

        s = str(getattr(event, "message", ""))
        m = _re.search(r"\[reply:(?:id=)?(\d+)\]", s) or _re.search(
            r"\[reply\s*,?\s*id=(\d+)\]", s
        )
        if m:
            return int(m.group(1))
    except Exception:
        pass

    return None


async def fetch_replied_message(bot: Bot, event: MessageEvent) -> Optional[Message]:
    """获取被回复的消息内容（Message 对象）。失败返回 None。"""
    try:
        mid = get_target_message_id(event)
        if not mid:
            return None
        data = await bot.get_msg(message_id=mid)  # type: ignore[arg-type]
        raw = data.get("message") if isinstance(data, dict) else None
        if raw is None:
            return None
        # 将 raw 尽力转成 Message
        try:
            from nonebot.adapters.onebot.v11 import Message as _Msg  # local import

            return raw if isinstance(raw, _Msg) else _Msg(raw)
        except Exception:
            return raw  # type: ignore[return-value]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"fetch_replied_message failed: {e}")
        return None


def _iter_message_segments_as_dicts(msg: Any) -> List[dict]:
    """将消息段尽力转换为 dict 列表（容错）。"""
    segs: List[dict] = []
    try:
        for seg in msg or []:
            if isinstance(seg, dict):
                segs.append(seg)
            elif hasattr(seg, "dict") and callable(getattr(seg, "dict")):
                try:
                    segs.append(seg.dict())
                except Exception:
                    try:
                        segs.append(vars(seg))
                    except Exception:
                        pass
            elif hasattr(seg, "__dict__" ):
                try:
                    segs.append(vars(seg))
                except Exception:
                    pass
    except Exception:
        pass
    return segs


async def extract_image_sources_with_bot(bot: Bot, msg: Message) -> List[str]:
    """从消息段提取图片来源（url 或通过 get_image 解析的本地路径）。"""
    out: List[str] = []
    try:
        for seg in _iter_message_segments_as_dicts(msg):
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
                    # 使用 OneBot get_image 将 file id 转真实路径
                    resp = await bot.get_image(file=file_)  # type: ignore[arg-type]
                    path = resp.get("file") if isinstance(resp, dict) else None
                    if path:
                        out.append(str(path))
                        continue
                except Exception:
                    # 兜底：直接返回 file_，便于定位
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
        for seg in _iter_message_segments_as_dicts(msg):
            if seg.get("type") == "text":
                t = (seg.get("data") or {}).get("text") or ""
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


# ===== 汇总获取：文本 / 图片 / 转发聊天记录 =====

@dataclass
class ReplyBundle:
    """被回复消息的汇总结果对象。

    字段:
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
        for seg in _iter_message_segments_as_dicts(msg):
            if seg.get("type") == "forward":
                data = seg.get("data") or {}
                fid = data.get("id")
                if fid:
                    return str(fid)
    except Exception:
        pass

    # 2) 字符串兜底解析（CQ/str 形态）
    try:
        s = str(msg)
        import re as _re

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

    # 解析 message_id
    try:
        bundle.message_id = get_target_message_id(event)
    except Exception:
        bundle.message_id = None

    # 获取被回复的 Message
    try:
        if bundle.message_id is not None:
            bundle.message = await fetch_replied_message(bot, event)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_reply_bundle.fetch_replied_message failed: {e}")
        bundle.message = None

    # 文本与图片
    try:
        if bundle.message:
            txt = extract_plain_text(bundle.message)
            bundle.text = txt if txt else None
            bundle.images = await extract_image_sources_with_bot(bot, bundle.message)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_reply_bundle.extract text/images failed: {e}")

    # 转发 id
    try:
        if bundle.message and not bundle.forward_id:
            bundle.forward_id = _extract_forward_id_from_message(bundle.message)
    except Exception:
        pass

    # 若未获取到，回查 get_msg 返回体再解析一次
    try:
        if not bundle.forward_id and bundle.message_id is not None:
            raw = await bot.get_msg(message_id=bundle.message_id)
            if isinstance(raw, dict):
                if raw.get("forward_id"):
                    bundle.forward_id = str(raw.get("forward_id"))
                if not bundle.forward_id and raw.get("message") is not None:
                    bundle.forward_id = _extract_forward_id_from_message(raw.get("message"))
                if not bundle.forward_id:
                    bundle.forward_id = _extract_forward_id_from_message(str(raw))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_reply_bundle.get_msg for forward failed: {e}")

    # 拉取转发节点
    try:
        if bundle.forward_id:
            bundle.forward_nodes = await _get_forward_nodes_by_id(bot, bundle.forward_id)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_reply_bundle.get_forward_nodes failed: {e}")

    return bundle


# ===== 解析 @ 提及信息 =====

@dataclass
class AtInfo:
    """解析到的 @ 提及信息

    字段:
    - user_id: 被 @ 的 QQ（字符串形式；可能为 'all' 表示全体成员）
    - nickname: 尽力获取到的昵称（优先群名片，其次昵称；若无法获取则为 None）
    """

    user_id: str
    nickname: Optional[str] = None


def _parse_ats_from_string_form(raw: str) -> List[str]:
    """从字符串形态解析 [CQ:at,qq=xxx] / [at:qq=xxx] 等形态。

    仅返回 qq/id 字符串；例如 'all' 或 '123456'.
    """
    ids: Set[str] = set()
    try:
        import re as _re

        for pat in [
            r"\[CQ:at,qq=(all|\d+)\]",
            r"\[at:qq=(all|\d+)\]",
            r"\[AT:qq=(all|\d+)\]",
        ]:
            for m in _re.finditer(pat, raw):
                ids.add(str(m.group(1)))
    except Exception:
        pass
    return list(ids)


async def extract_mentions(
    bot: Bot,
    event: MessageEvent,
    *,
    include_all: bool = True,
) -> List[AtInfo]:
    """解析消息中的 @ 信息，返回包含 id 与昵称的列表。

    策略:
    1) 遍历消息段中 type == 'at' 的段，读取 data.qq
    2) 若为空，兜底从字符串形态解析
    3) 对每个 id 获取昵称：群内优先群名片，然后昵称；非群尝试 get_stranger_info

    参数:
    - include_all: 是否包含 @全体成员（qq=all）
    """

    results: List[AtInfo] = []
    collected_ids: Set[str] = set()

    # 1) 从消息段提取
    try:
        for seg in _iter_message_segments_as_dicts(getattr(event, "message", [])):
            if seg.get("type") != "at":
                continue
            qq = str((seg.get("data") or {}).get("qq") or "").strip()
            if not qq:
                continue
            if qq == "all" and not include_all:
                continue
            collected_ids.add(qq)
    except Exception:
        pass

    # 2) 兜底从字符串解析
    try:
        if not collected_ids:
            raw = str(getattr(event, "message", ""))
            for qq in _parse_ats_from_string_form(raw):
                if qq == "all" and not include_all:
                    continue
                collected_ids.add(qq)
    except Exception:
        pass

    if not collected_ids:
        return []

    # 3) 尝试解析昵称
    group_id = getattr(event, "group_id", None)
    for uid in collected_ids:
        nickname: Optional[str] = None
        # 若 at 段自带 name 字段
        try:
            for seg in _iter_message_segments_as_dicts(getattr(event, "message", [])):
                if seg.get("type") == "at":
                    data = seg.get("data") or {}
                    if str(data.get("qq") or "").strip() == uid:
                        maybe_name = data.get("name")
                        if isinstance(maybe_name, str) and maybe_name.strip():
                            nickname = maybe_name.strip()
                            break
        except Exception:
            pass

        if nickname is None and uid != "all":
            # 群内优先查群名片
            if group_id:
                try:
                    info = await bot.get_group_member_info(
                        group_id=int(group_id), user_id=int(uid)
                    )
                    if isinstance(info, dict):
                        nickname = (
                            str(info.get("card") or "").strip()
                            or str(info.get("nickname") or "").strip()
                            or None
                        )
                except Exception:
                    pass
            # 非群尝试陌生人信息
            if nickname is None:
                try:
                    info = await bot.call_api("get_stranger_info", user_id=int(uid))
                    if isinstance(info, dict):
                        nickname = str(info.get("nickname") or "").strip() or None
                except Exception:
                    pass

        if uid == "all" and nickname is None:
            nickname = "全体成员"

        results.append(AtInfo(user_id=str(uid), nickname=nickname))

    return results