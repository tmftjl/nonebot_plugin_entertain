from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass
import asyncio
import shutil
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple
from urllib.parse import quote_plus

import httpx
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup
from nonebot.exception import FinishedException
from ...core.api import Plugin
from ...core.api import register_namespaced_config


try:
    from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
except Exception:  # pragma: no cover - allow import without adapter during static analysis
    Message = object  # type: ignore
    MessageEvent = object  # type: ignore

    class _Dummy:  # type: ignore
        @staticmethod
        def image(_: str):
            return None

        @staticmethod
        def record(_: str):
            return None

        @staticmethod
        def music_custom(url: str, audio: str, title: str, content: str, image: str):
            return None

    MessageSegment = _Dummy  # type: ignore

from PIL import Image, ImageDraw, ImageFont


Platform = Literal["qq", "kugou", "wangyiyun"]


@dataclass
class Song:
    id: str
    name: str
    artist: str
    cover: Optional[str] = None
    link: Optional[str] = None
    # platform specific
    mid: Optional[str] = None  # qq
    hash: Optional[str] = None  # kugou


# In-memory search cache per user
USER_RESULTS: Dict[str, Tuple[Platform, List[Song]]] = {}


# Regex definitions
P = Plugin(name="entertain")
_CFG = register_namespaced_config("entertain", "musicshare", {})
search_matcher = P.on_regex(
    r"^#?点歌(?:(qq|酷狗|网易云|wyy|kugou|netease))?\s*(.*)$",
    name="search",
    priority=5,
    flags=0,
)

select_matcher = P.on_regex(r"^#?(\d+)$", name="select", flags=0)


def _platform_alias_to_key(alias: Optional[str]) -> Platform:
    if not alias:
        return "wangyiyun"
    a = alias.lower()
    if a in {"qq"}:
        return "qq"
    if a in {"酷狗", "kugou"}:
        return "kugou"
    if a in {"网易", "wyy", "netease"}:
        return "wangyiyun"
    return "wangyiyun"


def _platform_name_human(p: Platform) -> str:
    return {"qq": "QQ音乐", "kugou": "酷狗音乐", "wangyiyun": "网易云音乐"}[p]


async def _search_songs(platform: Platform, keyword: str) -> List[Song]:
    timeout = httpx.Timeout(10.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if platform == "kugou":
            url = (
                "http://mobilecdn.kugou.com/api/v3/search/song"
                f"?format=json&keyword={quote_plus(keyword)}&page=1&pagesize=20&showtype=1"
            )
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            infos = data.get("data", {}).get("info", []) or []
            results: List[Song] = []
            for item in infos:
                name = item.get("songname") or "未知歌曲"
                artist = item.get("singername") or "未知歌手"
                song_hash = item.get("hash")
                album_id = str(item.get("album_id") or "")
                cover = None
                if item.get("imgurl"):
                    cover = "http://" + str(item["imgurl"]).lstrip("http://").lstrip("https://")
                results.append(
                    Song(
                        id=f"{song_hash or ''}:{album_id}",
                        name=name,
                        artist=artist,
                        cover=cover,
                        hash=song_hash,
                        link="https://www.kugou.com/song/",
                    )
                )
            return results

        if platform == "qq":
            url = (
                "http://datukuai.top:1450/djs/API/QQ_Music/api.php"
                f"?type=search&msg={quote_plus(keyword)}"
            )
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            list_ = data.get("data", []) or []
            results: List[Song] = []
            for item in list_:
                name = item.get("song") or "未知歌曲"
                artist = item.get("singer") or "未知歌手"
                link = item.get("url") or None
                mid = item.get("mid") or None
                cover = item.get("cover") or None
                results.append(
                    Song(
                        id=str(mid or ""),
                        name=name,
                        artist=artist,
                        cover=cover,
                        link=link,
                        mid=mid,
                    )
                )
            return results

        # 默认网易云
        url = (
            "https://music.163.com/api/search/get/web"
            f"?type=1&s={quote_plus(keyword)}&limit=20&offset=0"
        )
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        songs = (data.get("result", {}) or {}).get("songs", []) or []
        results: List[Song] = []
        for item in songs:
            name = item.get("name") or "未知歌曲"
            artist = ", ".join(a.get("name") for a in item.get("artists", []) or []) or "未知歌手"
            song_id = item.get("id")
            album = item.get("album") or {}
            cover = album.get("picUrl") or None
            link = f"https://music.163.com/#/song?id={song_id}" if song_id else None
            results.append(Song(id=str(song_id or ""), name=name, artist=artist, cover=cover, link=link))
        return results


async def _resolve_audio_url(platform: Platform, song: Song) -> Optional[str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        if platform == "kugou" and song.hash:
            api = f"https://www.kugou.com/yy/index.php?r=play/getdata&hash={song.hash}"
            r = await client.get(api)
            r.raise_for_status()
            data = r.json().get("data") or {}
            return data.get("play_url") or None
        if platform == "qq" and song.mid:
            # 直接返回搜索接口提供的 url（若有）
            return song.link
        if platform == "wangyiyun" and song.id:
            # 网易云需要客户端代理或第三方解析，退回到链接
            return None
    return None


def _ffmpeg_path() -> Optional[str]:
    """Locate ffmpeg executable via env var or PATH."""
    env_bin = os.getenv("FFMPEG_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin
    which = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    return which


async def _download_audio_via_ffmpeg(url: str, name_hint: str) -> Optional[Path]:
    """
    下载音频/转码为 mp3，并返回 NapCat 容器内可用的路径
    """
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        logger.error("FFmpeg not found in PATH and FFMPEG_BIN not set; cannot download locally.")
        return None
    logger.info(f"Found ffmpeg executable at: {ffmpeg}")
    host_base_path = Path("/opt/bot/data/temp/musicshare")
    container_base_path = Path("/root/data/temp/musicshare")

    try:
        host_base_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create temp directory on host {host_base_path}: {e}")
        return None

    safe = "".join(ch for ch in name_hint if ch.isalnum() or ch in (" ", "-", "_", "."))
    safe = safe.strip() or "audio"

    host_out_path = host_base_path / f"{safe}.mp3"

    if host_out_path.exists():
        try:
            host_out_path.unlink()
        except Exception:
            pass

    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-hide_banner",
        "-user_agent",
        ua,
        "-i",
        url,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "44100",
        "-b:a",
        "192k",
        str(host_out_path),
    ]

    logger.debug(f"Executing ffmpeg command to create file at: {host_out_path}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        if proc.returncode == 0 and host_out_path.exists() and host_out_path.stat().st_size > 1024:
            container_return_path = container_base_path / host_out_path.name
            logger.success(
                f"FFmpeg created file {host_out_path}, returning container path {container_return_path}"
            )
            return container_return_path
        else:
            error_message = stderr.decode(errors="ignore").strip()
            logger.error(f"FFmpeg process failed with exit code {proc.returncode}.")
            if error_message:
                logger.error(f"FFmpeg stderr: {error_message}")
            if not host_out_path.exists():
                logger.error("Output file was not created on host.")
            elif host_out_path.stat().st_size <= 1024:
                logger.error(
                    f"Output file on host is too small ({host_out_path.stat().st_size} bytes)."
                )
            return None

    except asyncio.TimeoutError:
        logger.error("FFmpeg process timed out after 120 seconds.")
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except FileNotFoundError:
        logger.error("FFmpeg executable not found when trying to run the process.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during ffmpeg execution: {e}")
        return None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\\Windows\\Fonts\\msyh.ttc",
        r"C:\\Windows\\Fonts\\simhei.ttf",
        r"C:\\Windows\\Fonts\\msyh.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _make_song_list_image_grid(platform: Platform, keyword: str, songs: List[Song]) -> bytes:
    title = f"点歌 · {_platform_name_human(platform)}"
    subtitle = f"关键词：{keyword}"
    footer_text = "发送序号选择（例如：#1）"
    max_items = min(len(songs), 8)
    columns = 2
    rows = (max_items + columns - 1) // columns

    bg_color = (248, 248, 250)
    fg_color = (30, 30, 30)
    accent_color = (65, 140, 240)

    pad_x, pad_y = 24, 22
    grid_gap_x, grid_gap_y = 18, 18
    card_inner_pad = 16
    card_bg = (255, 255, 255)
    card_border = (225, 225, 230)
    col_width = 400
    card_height = 100
    badge_r = 16
    text_left_offset = 20

    width = pad_x * 2 + col_width * columns + grid_gap_x * (columns - 1)
    font_title = _load_font(40)
    font_subtitle = _load_font(22)
    font_item = _load_font(22)
    font_footer = _load_font(18)

    # footer size for final height
    footer_h = text_size(footer_text, font_footer)[1]

    def text_size(t: str, f: ImageFont.ImageFont) -> Tuple[int, int]:
        im = Image.new("L", (10, 10))
        d = ImageDraw.Draw(im)
        return d.textlength(t, font=f), f.getbbox("Hg")[3]

    title_w, title_h = text_size(title, font_title)
    sub_w, sub_h = text_size(subtitle, font_subtitle)

    rendered: List[Tuple[str, int, int]] = []
    col_width_text = col_width - card_inner_pad * 2 - badge_r * 2 - text_left_offset
    for idx, s in enumerate(songs[:max_items]):
        text = f"{idx + 1}. {s.name} - {s.artist}"
        max_chars = max(10, col_width_text // 18)
        if len(text) > max_chars:
            text = text[: max_chars - 1] + "…"
        _, h = text_size(text, font_item)
        rendered.append((text, 0, h))

    rows = (max_items + columns - 1) // columns
    height = (
        pad_y * 2
        + title_h
        + 8
        + sub_h
        + 16
        + rows * card_height
        + (rows - 1) * grid_gap_y
        + 10
        + footer_h
    )

    im = Image.new("RGB", (width, height), color=bg_color)
    d = ImageDraw.Draw(im)

    cur_y = pad_y
    d.text((pad_x, cur_y), title, fill=accent_color, font=font_title)
    cur_y += title_h + 8
    d.text((pad_x, cur_y), subtitle, fill=fg_color, font=font_subtitle)
    cur_y += sub_h + 16

    for idx in range(max_items):
        row = idx // columns
        col = idx % columns
        x0 = pad_x + col * (col_width + grid_gap_x)
        y0 = cur_y + row * (card_height + grid_gap_y)
        x1 = x0 + col_width
        y1 = y0 + card_height

        d.rounded_rectangle([(x0, y0), (x1, y1)], radius=10, fill=card_bg, outline=card_border)

        cx = x0 + card_inner_pad + badge_r
        cy = y0 + card_height // 2
        d.ellipse([(cx - badge_r, cy - badge_r), (cx + badge_r, cy + badge_r)], fill=accent_color)
        num_text = str(idx + 1)
        tw, th = text_size(num_text, font_footer)
        d.text((cx - tw / 2, cy - th / 2), num_text, fill=(255, 255, 255), font=font_footer)

        text_x = x0 + card_inner_pad + text_left_offset
        text_y = y0 + (card_height - rendered[idx][2]) // 2
        d.text((text_x, text_y), rendered[idx][0], fill=fg_color, font=font_item)

    d.text((pad_x, cur_y + rows * (card_height + grid_gap_y) - grid_gap_y + 10), footer_text, fill=(120, 120, 120), font=font_footer)

    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


@search_matcher.handle()
async def _(matcher: Matcher, event: MessageEvent, groups: Tuple[Optional[str], str] = RegexGroup()) -> None:
    alias, keyword = groups
    keyword = (keyword or "").strip()
    if not keyword:
        await matcher.finish("请输入要搜索的歌曲名，例如：#点歌 晴天")

    platform = _platform_alias_to_key(alias)
    try:
        songs = await _search_songs(platform, keyword)
    except Exception:
        logger.exception("search songs failed")
        await matcher.finish("搜索歌曲时发生错误，请稍后再试")
        return

    if not songs:
        await matcher.finish(
            f"在“{_platform_name_human(platform)}”未找到“{keyword}”相关的歌曲"
        )
        return

    USER_RESULTS[event.get_user_id()] = (platform, songs)
    img_bytes = _make_song_list_image_grid(platform, keyword, songs)
    b64 = base64.b64encode(img_bytes).decode()
    await matcher.finish(MessageSegment.image(f"base64://{b64}"))


@select_matcher.handle()
async def _(matcher: Matcher, event: MessageEvent, groups: Tuple[str] = RegexGroup()) -> None:
    user_id = event.get_user_id()
    if user_id not in USER_RESULTS:
        await matcher.finish("您的点歌记录已过期，请先搜索歌曲。例如：#点歌 晴天")
        return

    index_str = groups[0]
    try:
        index = int(index_str) - 1
    except Exception:
        await matcher.finish("无效的歌曲序号，请检查后重试")
        return

    platform, songs = USER_RESULTS[user_id]
    if index < 0 or index >= len(songs):
        await matcher.finish("无效的歌曲序号，请检查后重试")
        return

    song = songs[index]
    await matcher.send(f"正在获取：{song.name} - {song.artist}，请稍等...")

    audio_url = await _resolve_audio_url(platform, song)

    if audio_url:
        try:
            local_path = await _download_audio_via_ffmpeg(
                audio_url, f"{song.name}-{song.artist}"
            )
            if local_path:
                await matcher.finish(
                    MessageSegment.record(local_path.resolve().as_uri())
                )
        except FinishedException:
            raise
        except Exception as ee:
            logger.warning(f"本地转码发送失败: {ee}")

    fallback = audio_url or song.link
    if fallback:
        await matcher.finish(f"{song.name} - {song.artist}\n{fallback}")
    else:
        await matcher.finish("播放失败：未能获取歌曲播放地址")
