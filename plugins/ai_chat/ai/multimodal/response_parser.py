"""将模型文本解析为多模态 ChatResult（UTF-8）\n\n- 识别 Markdown 图片 `![](url)`（含 data URL）\n- data URL 会解码保存至 `plugins/ai_chat/ai/runtime/media/`\n"""
from __future__ import annotations

import base64
import os
import re
import uuid
from pathlib import Path
from typing import List, Tuple

from ..types import ChatResult


# Markdown image: ![alt](url)  or ![](url)
MD_IMG = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _runtime_media_dir() -> Path:
    base = Path(__file__).resolve().parent.parent / "runtime" / "media"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _save_data_url(data_url: str) -> str:
    # data:image/png;base64,<base64>
    try:
        header, b64 = data_url.split(",", 1)
        # Pick extension
        ext = "bin"
        if ";base64" in header and ":" in header:
            mime = header.split(":", 1)[1].split(";", 1)[0]
            if "/" in mime:
                ext = mime.split("/", 1)[1]
        raw = base64.b64decode(b64)
        name = f"img_{uuid.uuid4().hex[:8]}.{ext}"
        path = _runtime_media_dir() / name
        with open(path, "wb") as f:
            f.write(raw)
        return str(path)
    except Exception:
        return data_url


def parse_response_to_chatresult(text: str) -> ChatResult:
    if not text:
        return ChatResult(text="")

    images: List[str] = []
    cleaned = text

    # Extract markdown images
    for m in MD_IMG.finditer(text):
        url = m.group(1)
        if url.startswith("data:"):
            saved = _save_data_url(url)
            images.append(saved)
        else:
            images.append(url)

    # Remove markdown image tags from text
    cleaned = MD_IMG.sub("", cleaned).strip()
    return ChatResult(text=cleaned, images=images)


