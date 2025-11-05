"""统一 TTS 接口

支持三类提供者：
- openai：使用 OpenAI TTS（通过 manager.client）
- http：调用本地/第三方 HTTP 接口，返回音频字节或 JSON(base64)
- command：执行本地命令，输出音频到指定路径

返回生成的音频文件路径（str），失败返回 None。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any
import base64
import asyncio
import os
import shlex
import tempfile

import httpx
from nonebot.log import logger

from .config import get_config
from ...core.framework.utils import plugin_data_dir
from ...core.constants import DEFAULT_HTTP_TIMEOUT
from ...core.http import get_shared_async_client


def _output_path(session_id: str, fmt: str) -> str:
    base = plugin_data_dir("ai_chat") / "tts"
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(base / f"{session_id}_{ts}.{fmt}")


async def _tts_openai(*, session_id: str, text: str, manager: Any) -> Optional[str]:
    cfg = get_config().output
    fmt = (cfg.tts_format or "mp3").lower()
    voice = cfg.tts_voice or "alloy"
    model = cfg.tts_model or "gpt-4o-mini-tts"
    file_path = _output_path(session_id, fmt)
    if not getattr(manager, "client", None):
        logger.warning("[AI Chat][TTS] OpenAI 客户端未初始化")
        return None
    try:
        async with manager.client.audio.speech.with_streaming_response.create(  # type: ignore[attr-defined]
            model=model,
            voice=voice,
            input=text,
            format=fmt,
        ) as response:
            await response.stream_to_file(file_path)
        return file_path
    except Exception as e:
        logger.error(f"[AI Chat][TTS] OpenAI TTS 失败: {e}")
        return None


async def _tts_http(*, session_id: str, text: str) -> Optional[str]:
    cfg = get_config().output
    fmt = (cfg.tts_format or "mp3").lower()
    url = (cfg.tts_http_url or "").strip()
    if not url:
        logger.warning("[AI Chat][TTS] HTTP TTS 未配置 url")
        return None
    method = (cfg.tts_http_method or "POST").upper()
    headers: Dict[str, str] = dict({})
    file_path = _output_path(session_id, fmt)
    payload = {"text": text, "voice": cfg.tts_voice or "", "format": fmt}
    try:
        client = await get_shared_async_client()
        if method == "GET":
            resp = await client.get(url, params=payload, headers=headers, timeout=DEFAULT_HTTP_TIMEOUT)
        else:
            resp = await client.post(url, json=payload, headers=headers, timeout=DEFAULT_HTTP_TIMEOUT)
        if cfg.tts_http_response_type == "base64":
            try:
                js = resp.json()
                b64 = js.get(cfg.tts_http_base64_field or "audio")
                if not b64:
                    return None
                data = base64.b64decode(b64)
                with open(file_path, "wb") as f:
                    f.write(data)
                return file_path
            except Exception as e:
                logger.error(f"[AI Chat][TTS] HTTP base64 解析失败: {e}")
                return None
        else:
            data = resp.content
            if not data:
                return None
            with open(file_path, "wb") as f:
                f.write(data)
            return file_path
    except Exception as e:
        logger.error(f"[AI Chat][TTS] HTTP TTS 调用失败: {e}")
        return None


_CMD_SEM = asyncio.Semaphore(2)


async def _tts_command(*, session_id: str, text: str) -> Optional[str]:
    cfg = get_config().output
    fmt = (cfg.tts_format or "mp3").lower()
    cmd_tpl = (cfg.tts_command or "").strip()
    if not cmd_tpl or "{out}" not in cmd_tpl:
        logger.warning("[AI Chat][TTS] 命令式 TTS 未配置或缺少 {out}")
        return None
    voice = cfg.tts_voice or ""
    out_path = _output_path(session_id, fmt)

    tmp_path = None
    try:
        # 将 text 写入临时文件，避免命令注入风险
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as tf:
            tf.write(text)
            tmp_path = tf.name

        cmd_str = (
            cmd_tpl.replace("{voice}", voice)
            .replace("{format}", fmt)
            .replace("{out}", out_path)
        )
        if "{text}" in cmd_str:
            cmd_str = cmd_str.replace("{text}", tmp_path)

        argv = shlex.split(cmd_str)

        async with _CMD_SEM:
            proc = await asyncio.create_subprocess_exec(*argv)
            await asyncio.wait_for(proc.communicate(), timeout=60.0)
        if proc.returncode == 0:
            try:
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    return out_path
            except Exception:
                pass
        logger.error(f"[AI Chat][TTS] 命令执行失败，退出码 {proc.returncode}")
        return None
    except asyncio.TimeoutError:
        try:
            proc.kill()  # type: ignore[name-defined]
        except Exception:
            pass
        try:
            await proc.wait()  # type: ignore[name-defined]
        except Exception:
            pass
        logger.error("[AI Chat][TTS] 命令执行超时")
        return None
    except Exception as e:
        logger.error(f"[AI Chat][TTS] 命令执行异常: {e}")
        return None
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass


async def run_tts(*, session_id: str, text: str, manager: Any) -> Optional[str]:
    cfg = get_config().output
    if not cfg.tts_enable:
        return None
    provider = (cfg.tts_provider or "openai").lower()
    if provider == "openai":
        return await _tts_openai(session_id=session_id, text=text, manager=manager)
    if provider == "http":
        return await _tts_http(session_id=session_id, text=text)
    if provider == "command":
        return await _tts_command(session_id=session_id, text=text)
    logger.warning(f"[AI Chat][TTS] 未知 TTS 提供者 {provider}")
    return None

