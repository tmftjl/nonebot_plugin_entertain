from __future__ import annotations

import re
from typing import Optional

from nonebot.adapters.onebot.v11 import Message


def extract_at_or_id(msg: Message) -> Optional[int]:
    """从消息中提取 @ 的 QQ 号或文本中的纯数字 QQ 号。"""
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
    """解析时长文本为秒。支持：30s/10m/2h/1d/10分/2小时/1天。"""
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

