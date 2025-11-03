"""OneBot v11 消息解析工具（UTF-8）\n\n- 提取纯文本与图片 URL/路径\n- 兼容常见实现（url 或 file 字段）\n"""
from __future__ import annotations

from typing import List, Tuple

try:
    # Type-only import; keep runtime import lightweight
    from nonebot.adapters.onebot.v11 import Message
except Exception:  # pragma: no cover - optional import during static analysis
    Message = object  # type: ignore


def extract_text_and_images(message: "Message") -> Tuple[str, List[str]]:
    """Extract text and image URLs/paths from an OneBot v11 Message.

    Strategy:
    - Concatenate all `text` segments into a single string with spaces.
    - Collect `image` segment `url` if present; otherwise collect `file` as-is.
      Many implementations provide an HTTP URL; some provide a local path or
      a CQ image file identifier. Downstream can implement a resolver if needed.
    """
    text_parts: List[str] = []
    images: List[str] = []

    try:
        for seg in message:  # type: ignore[attr-defined]
            if seg.type == "text":
                text_parts.append((seg.data.get("text") or "").strip())
            elif seg.type == "image":
                data = seg.data or {}
                url = data.get("url")
                file_ = data.get("file")
                if url:
                    images.append(url)
                elif file_:
                    images.append(str(file_))
    except Exception:
        # Fallback to plain string
        try:
            text_parts.append(str(message))  # type: ignore[arg-type]
        except Exception:
            pass

    text = " ".join([p for p in text_parts if p]).strip()
    return text, images


