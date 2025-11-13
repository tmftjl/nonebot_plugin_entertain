from __future__ import annotations

from typing import Any, List, Optional, Set
from dataclasses import dataclass, field

from nonebot.log import logger

try:  # pragma: no cover - 运行期由适配器提供
    from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
except Exception:  # pragma: no cover - 便于静态检查
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
    logger.debug("[mu] 进入 get_target_message_id")
    # 1) event.reply
    try:
        reply = getattr(event, "reply", None)
        logger.debug(f"[mu] event.reply = {reply!r}")
        if reply is not None:
            for key in ("message_id", "id"):
                if hasattr(reply, key):
                    mid = _safe_int(getattr(reply, key))
                    logger.debug(f"[mu] reply 对象属性 {key} -> {mid}")
                    if mid is not None:
                        return mid
            if isinstance(reply, dict):
                for key in ("message_id", "id"):
                    mid = _safe_int(reply.get(key))
                    logger.debug(f"[mu] reply 字典键 {key} -> {mid}")
                    if mid is not None:
                        return mid
            try:  # pragma: no cover - 兜底
                import re as _re
                m = _re.search(r"(message_id|id)\D*(\d+)", str(reply))
                if m:
                    logger.debug("[mu] 从 str(reply) 匹配到 message_id")
                    return int(m.group(2))
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"[mu] get_target_message_id: reply 分支异常: {e}")

    # 2) reply 段 in event.message
    try:
        for seg in getattr(event, "message", []):
            logger.debug(f"[mu] 遍历消息段: type={getattr(seg,'type',None)} data={getattr(seg,'data',None)}")
            if getattr(seg, "type", None) == "reply":
                data = getattr(seg, "data", None) or {}
                mid = _safe_int(data.get("id"))
                logger.debug(f"[mu] reply 段 id -> {mid}")
                if mid is not None:
                    return mid
    except Exception as e:
        logger.debug(f"[mu] get_target_message_id: 消息段分支异常: {e}")

    # 3) 字符串兜底 [reply:id=xxxx]
    try:
        import re as _re
        s = str(getattr(event, "message", ""))
        logger.debug(f"[mu] 消息字符串: {s!r}")
        m = _re.search(r"\[reply:(?:id=)?(\d+)\]", s) or _re.search(r"\[reply\s*,?\s*id=(\d+)\]", s)
        if m:
            val = int(m.group(1))
            logger.debug(f"[mu] 字符串匹配到 reply id -> {val}")
            return val
    except Exception as e:
        logger.debug(f"[mu] get_target_message_id: 字符串分支异常: {e}")

    logger.debug("[mu] 未解析到 message_id -> None")
    return None


async def fetch_replied_message(bot: Bot, event: MessageEvent) -> Optional[Message]:
    """获取被回复的消息内容（Message 对象）。失败返回 None。"""
    try:
        mid = get_target_message_id(event)
        logger.debug(f"[mu] fetch_replied_message: 目标 message_id = {mid}")
        if not mid:
            return None
        data = await bot.get_msg(message_id=mid)  # type: ignore[arg-type]
        logger.debug(
            f"[mu] fetch_replied_message: get_msg 返回类型/键 = {list(data.keys()) if isinstance(data, dict) else type(data)}"
        )
        raw = data.get("message") if isinstance(data, dict) else None
        logger.debug(f"[mu] fetch_replied_message: raw 类型 = {type(raw)}")
        if raw is None:
            return None
        try:
            from nonebot.adapters.onebot.v11 import Message as _Msg  # 局部导入
            msg_obj = raw if isinstance(raw, _Msg) else _Msg(raw)
            logger.debug(f"[mu] fetch_replied_message: 已转换为 Message；长度 = {len(str(msg_obj))}")
            return msg_obj
        except Exception as e:
            logger.debug(f"[mu] fetch_replied_message: Message 转换失败，返回原始对象: {e}")
            return raw  # type: ignore[return-value]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[mu] fetch_replied_message 失败: {e}")
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
            elif hasattr(seg, "__dict") or hasattr(seg, "__dict__"):
                try:
                    segs.append(vars(seg))
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"[mu] _iter_message_segments_as_dicts: 异常 {e}")
    logger.debug(f"[mu] _iter_message_segments_as_dicts: 得到 {len(segs)} 段")
    return segs


async def extract_image_sources_with_bot(bot: Bot, msg: Message) -> List[str]:
    """从消息段提取图片来源（url 或通过 get_image 解析的本地路径）。"""
    out: List[str] = []
    try:
        segs = _iter_message_segments_as_dicts(msg)
        logger.debug(f"[mu] extract_image_sources_with_bot: 消息段数量 = {len(segs)}")
        for seg in segs:
            if seg.get("type") != "image":
                continue
            data = seg.get("data") or {}
            url = str((data.get("url") or "")).strip()
            if url:
                out.append(url)
                logger.debug(f"[mu] extract_image_sources_with_bot: 发现图片 URL -> {url}")
                continue
            file_ = str((data.get("file") or "")).strip()
            if file_:
                try:
                    resp = await bot.get_image(file=file_)  # type: ignore[arg-type]
                    path = resp.get("file") if isinstance(resp, dict) else None
                    if path:
                        out.append(str(path))
                        logger.debug(f"[mu] extract_image_sources_with_bot: get_image 返回文件路径 -> {path}")
                        continue
                except Exception as e:
                    logger.debug(f"[mu] extract_image_sources_with_bot: get_image 失败 {e}; 回退 file={file_}")
                    out.append(file_)
    except Exception as e:
        logger.debug(f"[mu] extract_image_sources_with_bot 异常: {e}")

    logger.debug(f"[mu] extract_image_sources_with_bot: 结果数量 = {len(out)}")
    return out


async def get_images_from_event_or_reply(
    bot: Bot, event: MessageEvent, *, include_current: bool = True
) -> List[str]:
    """优先从当前消息取图；没有则尝试从被引用的消息中取图。"""
    if include_current:
        try:
            logger.debug("[mu] get_images_from_event_or_reply: 尝试从当前消息取图")
            current = await extract_image_sources_with_bot(bot, event.get_message())
            if current:
                logger.debug("[mu] get_images_from_event_or_reply: 已从当前消息获取到图片")
                return current
        except Exception as e:
            logger.debug(f"[mu] get_images_from_event_or_reply: 当前消息取图异常 {e}")

    try:
        logger.debug("[mu] get_images_from_event_or_reply: 尝试从被回复消息取图")
        replied = await fetch_replied_message(bot, event)
        if replied:
            return await extract_image_sources_with_bot(bot, replied)
    except Exception as e:
        logger.debug(f"[mu] get_images_from_event_or_reply: 被回复消息取图异常 {e}")
    return []


def extract_plain_text(msg: Message, *, strip: bool = True) -> str:
    """提取消息中的纯文本内容（忽略 CQ 码）。"""
    try:
        text = msg.extract_plain_text()  # type: ignore[attr-defined]
        res = text.strip() if strip else text
        logger.debug(f"[mu] extract_plain_text: 适配器 extract_plain_text 成功，文本 = {res!r}")
        return res
    except Exception as e:
        logger.debug(f"[mu] extract_plain_text: 适配器 extract_plain_text 失败: {e}")

    texts: List[str] = []
    try:
        for seg in _iter_message_segments_as_dicts(msg):
            if seg.get("type") == "text":
                t = (seg.get("data") or {}).get("text") or ""
                texts.append(str(t))
    except Exception as e:
        logger.debug(f"[mu] extract_plain_text: 遍历段失败，使用 str(msg): {e}")
        joined = str(msg)
        return joined.strip() if strip else joined
    joined = "".join(texts)
    res = joined.strip() if strip else joined
    logger.debug(f"[mu] extract_plain_text: 拼接 text 段完成，文本 = {res!r}")
    return res


async def get_reply_text(bot: Bot, event: MessageEvent) -> Optional[str]:
    """获取被回复消息的纯文本（若不可用返回 None）。"""
    try:
        replied = await fetch_replied_message(bot, event)
        if not replied:
            logger.debug("[mu] get_reply_text: 没有被回复的消息")
            return None
        text = extract_plain_text(replied)
        logger.debug(f"[mu] get_reply_text: 文本 = {text!r}")
        return text if text else None
    except Exception as e:
        logger.debug(f"[mu] get_reply_text: 异常 {e}")
        return None


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
    except Exception as e:
        logger.debug(f"[mu] _parse_ats_from_string_form: 异常 {e}")
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
    """

    results: List[AtInfo] = []
    collected_ids: Set[str] = set()

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
        logger.debug(f"[mu] extract_mentions: 从段解析到的 @ 集合: {collected_ids}")
    except Exception as e:
        logger.debug(f"[mu] extract_mentions: 段解析异常 {e}")

    try:
        if not collected_ids:
            raw = str(getattr(event, "message", ""))
            for qq in _parse_ats_from_string_form(raw):
                if qq == "all" and not include_all:
                    continue
                collected_ids.add(qq)
        logger.debug(f"[mu] extract_mentions: 字符串解析后的 @ 集合: {collected_ids}")
    except Exception as e:
        logger.debug(f"[mu] extract_mentions: 字符串解析异常 {e}")

    if not collected_ids:
        return []

    group_id = getattr(event, "group_id", None)
    for uid in collected_ids:
        nickname: Optional[str] = None
        try:
            for seg in _iter_message_segments_as_dicts(getattr(event, "message", [])):
                if seg.get("type") == "at":
                    data = seg.get("data") or {}
                    if str(data.get("qq") or "").strip() == uid:
                        maybe_name = data.get("name")
                        if isinstance(maybe_name, str) and maybe_name.strip():
                            nickname = maybe_name.strip()
                            break
        except Exception as e:
            logger.debug(f"[mu] extract_mentions: 从段读取 name 异常 {e}")

        if nickname is None and uid != "all":
            if group_id:
                try:
                    info = await bot.get_group_member_info(group_id=int(group_id), user_id=int(uid))
                    if isinstance(info, dict):
                        nickname = (
                            str(info.get("card") or "").strip()
                            or str(info.get("nickname") or "").strip()
                            or None
                        )
                except Exception as e:
                    logger.debug(f"[mu] extract_mentions: get_group_member_info 异常 {e}")
            if nickname is None:
                try:
                    info = await bot.call_api("get_stranger_info", user_id=int(uid))
                    if isinstance(info, dict):
                        nickname = str(info.get("nickname") or "").strip() or None
                except Exception as e:
                    logger.debug(f"[mu] extract_mentions: get_stranger_info 异常 {e}")

        if uid == "all" and nickname is None:
            nickname = "全体成员"

        results.append(AtInfo(user_id=str(uid), nickname=nickname))

    logger.debug(f"[mu] extract_mentions: 最终 @ 结果 = {[(r.user_id,r.nickname) for r in results]}")
    return results


# ===== 转发解析辅助 =====

def _extract_forward_id_from_message(msg: Any) -> Optional[str]:
    """从 Message 或字符串中尽力解析转发 id。"""
    try:
        segs = _iter_message_segments_as_dicts(msg)
        logger.debug(f"[mu] _extract_forward_id_from_message: 消息段数量 = {len(segs)}")
        for seg in segs:
            if seg.get("type") == "forward":
                data = seg.get("data") or {}
                fid = data.get("id")
                logger.debug(f"[mu] _extract_forward_id_from_message: forward 段 id = {fid}")
                if fid:
                    return str(fid)
    except Exception as e:
        logger.debug(f"[mu] _extract_forward_id_from_message: 段解析异常 {e}")

    try:
        s = str(msg)
        import re as _re
        logger.debug(f"[mu] _extract_forward_id_from_message: 字符串长度 = {len(s)}")
        for pat in [
            r"\[CQ:forward,id=([A-Za-z0-9_\-+=/]+)\]",
            r"\[forward(?::|,)?(?:id=)?([A-Za-z0-9_\-+=/]+)\]",
            r"(?:forward_id|id)\D*([A-Za-z0-9_\-+=/]{5,})",
        ]:
            m = _re.search(pat, s)
            if m:
                fid = m.group(1)
                logger.debug(f"[mu] _extract_forward_id_from_message: 在字符串中匹配到 forward_id = {fid}")
                return fid
    except Exception as e:
        logger.debug(f"[mu] _extract_forward_id_from_message: 字符串解析异常 {e}")
    return None


async def _get_forward_nodes_by_id(bot: Bot, forward_id: str) -> List[dict]:
    """调用 get_forward_msg 获取转发节点列表。"""
    try:
        data = await bot.call_api("get_forward_msg", id=forward_id)
        if isinstance(data, dict):
            if isinstance(data.get("messages"), list):
                logger.debug(f"[mu] _get_forward_nodes_by_id: 节点数量 = {len(data['messages'])}")
                return list(data["messages"])
            d = data.get("data")
            if isinstance(d, dict) and isinstance(d.get("messages"), list):
                logger.debug(f"[mu] _get_forward_nodes_by_id: 节点数量(data) = {len(d['messages'])}")
                return list(d["messages"])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[mu] get_forward_msg 失败: {e}")
    return []


# ===== 通用整合：可按需选择字段，支持当前/被回复 =====

@dataclass
class MessageBundle:
    """通用消息汇总结构（可表示当前消息或被回复的消息）。

    字段:
    - source: 'current' | 'reply'，表示来源
    - message_id: 源消息的 message_id（当前消息则尽力取 event.message_id）
    - message: 源消息的 Message 对象
    - text/images/forward_id/forward_nodes/mentions: 解析结果
    """

    source: str = "reply"
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
    """整合获取：根据参数选择要素，支持当前/被回复。

    - source: 'current' 解析当前消息；'reply' 解析被回复消息；'auto' 若有被回复则取被回复，否则当前。
    - want_*: 控制是否解析对应要素，避免不必要的 API 开销。
    """

    logger.debug(f"[mu] 进入 get_message_bundle: source={source}, want_text={want_text}, want_images={want_images}, want_forward={want_forward}, want_mentions={want_mentions}")

    chosen = source
    mid: Optional[int] = None
    msg: Optional[Message] = None

    # 选源
    try:
        if source == "current":
            chosen = "current"
            mid = _safe_int(getattr(event, "message_id", None))
            try:
                msg = event.get_message()
            except Exception:
                msg = getattr(event, "message", None)
        elif source == "reply" or source == "auto":
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
            # 非法 source 按 reply 处理
            chosen = "reply"
            mid = get_target_message_id(event)
            if mid:
                msg = await fetch_replied_message(bot, event)
    except Exception as e:
        logger.debug(f"[mu] get_message_bundle: 选择消息源异常 {e}")

    bundle = MessageBundle(source=chosen, message_id=mid, message=msg)

    # 按需解析
    if msg is not None:
        if want_text:
            try:
                bundle.text = await extract_display_text(bot, event, msg)
            except Exception as e:
                logger.debug(f"[mu] get_message_bundle: 提取文本异常 {e}")
        if want_images:
            try:
                bundle.images = await extract_image_sources_with_bot(bot, msg)
            except Exception as e:
                logger.debug(f"[mu] get_message_bundle: 提取图片异常 {e}")
        if want_forward:
            try:
                bundle.forward_id = _extract_forward_id_from_message(msg)
                if not bundle.forward_id and chosen == "reply" and mid is not None:
                    # 尝试在 get_msg 的原始体中查找
                    raw = await bot.get_msg(message_id=mid)
                    if isinstance(raw, dict):
                        if raw.get("forward_id"):
                            bundle.forward_id = str(raw.get("forward_id"))
                        if not bundle.forward_id and raw.get("message") is not None:
                            bundle.forward_id = _extract_forward_id_from_message(raw.get("message"))
                        if not bundle.forward_id:
                            bundle.forward_id = _extract_forward_id_from_message(str(raw))
                if bundle.forward_id:
                    bundle.forward_nodes = await _get_forward_nodes_by_id(bot, bundle.forward_id)
            except Exception as e:
                logger.debug(f"[mu] get_message_bundle: 解析/获取转发异常 {e}")
        if want_mentions:
            try:
                if chosen == "current":
                    bundle.mentions = await extract_mentions(bot, event)
                else:
                    # 尝试仅解析 id；昵称通过 group_id 进行尽力查询
                    ids: Set[str] = set()
                    for seg in _iter_message_segments_as_dicts(msg):
                        if seg.get("type") == "at":
                            qq = str((seg.get("data") or {}).get("qq") or "").strip()
                            if qq:
                                ids.add(qq)
                    # 查询昵称（可选）
                    results: List[AtInfo] = []
                    group_id = getattr(event, "group_id", None)
                    for uid in ids:
                        nickname: Optional[str] = None
                        if uid != "all" and group_id:
                            try:
                                info = await bot.get_group_member_info(group_id=int(group_id), user_id=int(uid))
                                if isinstance(info, dict):
                                    nickname = (str(info.get("card") or "").strip() or str(info.get("nickname") or "").strip() or None)
                            except Exception:
                                pass
                        if uid == "all" and nickname is None:
                            nickname = "全体成员"
                        results.append(AtInfo(user_id=str(uid), nickname=nickname))
                    bundle.mentions = results
            except Exception as e:
                logger.debug(f"[mu] get_message_bundle: 提取 @ 信息异常 {e}")

    logger.debug(
        f"[mu] get_message_bundle: 完成 -> source={bundle.source} mid={bundle.message_id} text_len={len(bundle.text or '') if bundle.text is not None else 0} images={len(bundle.images)} forward_id={bundle.forward_id} nodes={len(bundle.forward_nodes)} mentions={len(bundle.mentions)}"
    )
    
    # 嵌入被回复消息（不混淆图片等字段）
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
    except Exception as e:
        logger.debug(f"[mu] get_message_bundle: 构造嵌套 reply 异常 {e}")
    return bundle


# ===== 批量整合：一次返回当前与被回复 =====

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
    """一次性获取“当前/被回复”的消息汇总。

    - include_current/include_reply 控制要返回哪些部分
    - want_* 同 get_message_bundle
    """
    logger.debug(f"[mu] 进入 get_message_bundles: include_current={include_current}, include_reply={include_reply}, want_text={want_text}, want_images={want_images}, want_forward={want_forward}, want_mentions={want_mentions}")

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
    except Exception as e:
        logger.debug(f"[mu] get_message_bundles: 获取当前消息异常 {e}")
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
    except Exception as e:
        logger.debug(f"[mu] get_message_bundles: 获取被回复消息异常 {e}")

    logger.debug(f"[mu] get_message_bundles: 完成 -> current={cur is not None} reply={rep is not None}")
    return MessageBundles(current=cur, reply=rep)
async def extract_display_text(
    bot: Bot,
    event: MessageEvent,
    msg: Message,
    *,
    strip: bool = True,
) -> str:
    """提取“可读文本”，会把 @ 段渲染为“@昵称”。

    昵称解析顺序：
    1) 段内 data.name
    2) 群成员 card/nickname（如有 group_id）
    3) qq=all -> 全体成员
    4) 兜底 qq 本身
    仅渲染 text/at 段，其余段忽略。
    """
    parts: List[str] = []

    async def _get_name(qq: str, data: dict) -> str:
        name = str(data.get("name") or "").strip()
        if name:
            return name
        if qq == "all":
            return "全体成员"
        group_id = getattr(event, "group_id", None)
        if group_id:
            try:
                info = await bot.get_group_member_info(group_id=int(group_id), user_id=int(qq))
                if isinstance(info, dict):
                    card = str(info.get("card") or "").strip()
                    nick = str(info.get("nickname") or "").strip()
                    if card or nick:
                        return card or nick
            except Exception:
                pass
        return qq

    segs = _iter_message_segments_as_dicts(msg)
    for seg in segs:
        t = seg.get("type")
        data = seg.get("data") or {}
        if t == "text":
            parts.append(str(data.get("text") or ""))
        elif t == "at":
            qq = str(data.get("qq") or "").strip()
            if qq:
                name = await _get_name(qq, data)
                parts.append("@" + name)

    res = "".join(parts)
    return res.strip() if strip else res