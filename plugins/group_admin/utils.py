from __future__ import annotations

import re
from typing import Optional

from nonebot.adapters.onebot.v11 import Message, MessageEvent

def extract_at_or_id(msg: Message) -> Optional[int]:
    """从消息中提取 @ 的 QQ 号或消息文本中的纯数字 QQ 号。"""
    try:
        for seg in msg:
            if seg.type == "at":
                qq = str((seg.data or {}).get("qq") or "").strip()
                if qq and qq != "all":
                    return int(qq)
        m = re.search(r"(?<!\d)(\d{5,})(?!\d)", str(msg))
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def parse_duration_to_seconds(text: str, default_seconds: int = 600) -> int:
    """解析时长文本为秒。支持示例：30s、10m、2h、1d、10秒、2小时、1天。"""
    try:
        text = (text or "").strip()
        if not text:
            return default_seconds
        m = re.match(r"^(\d+)([a-zA-Z\u4e00-\u9fa5]*)$", text)
        if not m:
            return default_seconds
        num = int(m.group(1))
        unit = (m.group(2) or "").lower()
        if unit in ("s", "秒"):
            return max(1, num)
        if unit in ("m", "min", "分钟", "分"):
            return max(1, num * 60)
        if unit in ("h", "小时"):
            return max(1, num * 3600)
        if unit in ("d", "天"):
            return max(1, num * 86400)
        return max(1, num * 60)
    except Exception:
        return default_seconds


def get_reply_message_id(msg: Message) -> Optional[int]:
    """从消息段中提取被回复消息的 id。"""
    try:
        for seg in msg:
            if seg.type == "reply":
                mid = (seg.data or {}).get("id")
                if mid is not None:
                    return int(mid)
    except Exception:
        pass
    return None


def get_target_message_id(event: MessageEvent) -> Optional[int]:
    """尽可能从事件中获取被回复消息的 message_id。

    优先顺序：
    1) event.reply.message_id（部分实现只在这里提供）
    2) event.message 中的 reply 段 id
    3) 从字符串形态解析 [reply:id=xxxx]
    """
    # 1) 优先从 event.reply 读取
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
                except Exception:
                    pass
            # 兜底：从其字符串表示中提取数字
            try:
                import re as _re
                m = _re.search(r"(message_id|id)\D*(\d+)", str(reply))
                if m:
                    return int(m.group(2))
            except Exception:
                pass
    except Exception:
        pass

    # 2) 从消息段中的 reply 读取
    try:
        mid = get_reply_message_id(event.message)
        if mid:
            return mid
    except Exception:
        pass

    # 3) 兜底：从消息字符串表示中解析 [reply:id=xxxx]
    try:
        import re as _re
        s = str(event.message)
        m = _re.search(r"\[reply:(?:id=)?(\d+)\]", s)
        if not m:
            m = _re.search(r"\[reply\s*,?\s*id=(\d+)\]", s)
        if m:
            return int(m.group(1))
    except Exception:
        pass

    return None
