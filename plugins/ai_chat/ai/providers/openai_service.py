"""OpenAI 服务封装（UTF-8）\n\n- 提供文生图与语音合成的便捷访问\n- 使用当前激活的 AI 配置\n"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import List, Optional

from nonebot.log import logger
from openai import AsyncOpenAI

from ...config import get_active_api


class OpenAIService:
    def __init__(self) -> None:
        api = get_active_api()
        if not api.api_key:
            raise RuntimeError("OpenAI API key not configured")
        self.client = AsyncOpenAI(api_key=api.api_key, base_url=api.base_url, timeout=api.timeout)

    async def generate_images(self, prompt: str, *, n: int = 1, size: str = "1024x1024") -> List[str]:
        """Generate images and return list of URLs or data URLs.

        Uses Images API; returns URLs if available; otherwise returns data URLs.
        """
        try:
            res = await self.client.images.generate(model="gpt-image-1", prompt=prompt, n=n, size=size)
            images: List[str] = []
            for d in res.data:
                if getattr(d, "url", None):
                    images.append(d.url)
                elif getattr(d, "b64_json", None):
                    images.append("data:image/png;base64," + d.b64_json)
            return images
        except Exception as e:
            logger.error(f"[AI Chat] OpenAI image generate failed: {e}")
            return []

    async def text_to_speech(self, text: str, *, voice: str = "alloy", fmt: str = "mp3") -> Optional[str]:
        """Synthesize speech and return local file path.

        Saves to plugins/ai_chat/runtime/media/ and returns path; None on error.
        """
        try:
            # gpt-4o-mini-tts or tts-1 per provider
            response = await self.client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice=voice,
                input=text,
                format=fmt,
            )
            raw = response.content  # bytes
            media_dir = Path(__file__).resolve().parent.parent / "runtime" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            path = media_dir / f"speech_{voice}.{fmt}"
            with open(path, "wb") as f:
                f.write(raw)
            return str(path)
        except Exception as e:
            logger.error(f"[AI Chat] OpenAI TTS failed: {e}")
            return None


