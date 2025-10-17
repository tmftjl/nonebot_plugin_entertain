from __future__ import annotations

import re
from typing import Optional

from nonebot.adapters.onebot.v11 import Message, MessageEvent

def extract_at_or_id(msg: Message) -> Optional[int]:
    """浠庢秷鎭腑鎻愬彇 @ 鐨?QQ 鍙锋垨鏂囨湰涓殑绾暟瀛?QQ 鍙枫€?""
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
    """瑙ｆ瀽鏃堕暱鏂囨湰涓虹銆傛敮鎸侊細30s/10m/2h/1d/10鍒?2灏忔椂/1澶┿€?""
    try:
        text = (text or "").strip()
        if not text:
            return default_seconds
        m = re.match(r"^(\d+)([a-zA-Z\u4e00-\u9fa5]*)$", text)
        if not m:
            return default_seconds
        num = int(m.group(1))
        unit = (m.group(2) or "").lower()
        if unit in ("s", "绉?):
            return max(1, num)
        if unit in ("m", "min", "鍒嗛挓", "鍒?):
            return max(1, num * 60)
        if unit in ("h", "灏忔椂"):
            return max(1, num * 3600)
        if unit in ("d", "澶?):
            return max(1, num * 86400)
        return max(1, num * 60)
    except Exception:
        return default_seconds


def get_reply_message_id(msg: Message) -> Optional[int]:
    """浠庢秷鎭涓彁鍙栬鍥炲娑堟伅鐨?id銆?""
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
    """Best-effort to fetch replied message_id from event.

    Order:
    1) event.reply.message_id (some adapters only provide here)
    2) reply segment id in event.message
    3) parse from string form like [reply:id=xxxx]
    """
    # 1) from event.reply
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
            # last attempt: parse number from str(reply)
            try:
                import re as _re
                m = _re.search(r"(message_id|id)\D*(\d+)", str(reply))
                if m:
                    return int(m.group(2))
            except Exception:
                pass
    except Exception:
        pass

    # 2) reply segment in message
    try:
        mid = get_reply_message_id(event.message)
        if mid:
            return mid
    except Exception:
        pass

    # 3) parse string form: [reply:id=xxxx]
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


