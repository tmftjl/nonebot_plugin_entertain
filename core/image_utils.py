"""image 实用工具

提供从 URL 下载图片并转换为 Base64 的工具函数。

特性：
- 复用全局 HTTP 连接池，支持超时与重试
- 自动识别图片 MIME（优先使用响应头，失败时回退到 Pillow 检测）
- 可选返回 Data URL（data:image/...;base64,...）
"""
from __future__ import annotations

import base64
import io
from typing import Optional

from nonebot.log import logger
from PIL import Image

from .constants import DEFAULT_HTTP_TIMEOUT
from .http import http_get


def _clean_content_type(ct: str) -> str:
    """标准化 Content-Type，只保留主类型部分。

    例如: "image/jpeg; charset=binary" -> "image/jpeg"
    """
    try:
        ct = (ct or "").strip().lower()
        if not ct:
            return ""
        if ";" in ct:
            ct = ct.split(";", 1)[0].strip()
        return ct
    except Exception:
        return ""


def _mime_from_pillow(data: bytes) -> Optional[str]:
    """通过 Pillow 从字节流推断图片 MIME 类型。

    返回形如 "image/png"、"image/jpeg" 等；失败返回 None。
    """
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").upper()
        mapping = {
            "PNG": "image/png",
            "JPEG": "image/jpeg",
            "JPG": "image/jpeg",
            "GIF": "image/gif",
            "WEBP": "image/webp",
            "BMP": "image/bmp",
            "TIFF": "image/tiff",
            "ICO": "image/x-icon",
            "SVG": "image/svg+xml",
        }
        return mapping.get(fmt)
    except Exception:
        return None


def _to_base64(data: bytes) -> str:
    """将字节转 Base64（不带前缀）。"""
    return base64.b64encode(data).decode("ascii")


async def image_url_to_base64(
    url: str,
    *,
    include_data_url: bool = False,
    timeout: Optional[float] = None,
    retries: int = 1,
) -> Optional[str]:
    """下载指定 URL 的图片并转换为 Base64 字符串。

    Args:
        url: 图片直链 URL（支持 http/https）。
        include_data_url: 是否返回 Data URL（data:image/...;base64,...）。
        timeout: 单次请求超时（秒），默认使用全局超时。
        retries: 失败重试次数（仅对连接/超时错误生效）。

    Returns:
        - `str`: Base64 字符串（或 Data URL）。
        - `None`: 失败。
    """
    try:
        # 基础校验
        url = (url or "").strip()
        if not url:
            return None

        # 直接透传 data URL
        if url.startswith("data:"):
            if include_data_url:
                return url
            try:
                # 截取逗号后的 base64 内容
                idx = url.find(",")
                return url[idx + 1 :] if idx != -1 else None
            except Exception:
                return None

        # 发起请求
        to = DEFAULT_HTTP_TIMEOUT if timeout is None else timeout
        resp = await http_get(url, timeout=to, retries=retries)
        resp.raise_for_status()
        data = resp.content or b""
        if not data:
            return None

        # 判定 MIME
        ct = _clean_content_type(resp.headers.get("content-type", ""))
        mime: Optional[str] = None
        if ct.startswith("image/"):
            mime = ct
        if not mime:
            mime = _mime_from_pillow(data)

        b64 = _to_base64(data)
        if include_data_url:
            if not mime:
                # 保底使用通用类型，避免前缀缺失
                mime = "image/png"
            return f"data:{mime};base64,{b64}"
        return b64

    except Exception as e:
        logger.error(f"[AI Chat][utils] 下载或转码失败: {e}")
        return None


__all__ = ["image_url_to_base64"]

