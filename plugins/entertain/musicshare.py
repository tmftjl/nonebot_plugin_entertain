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
from .config import cfg_music, cfg_api_timeouts


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
Provider = Literal["tencent", "netease"]


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
P = Plugin(name="entertain", display_name="娱乐")
search_matcher = P.on_regex(
    r"^#点歌(?:(qq|酷狗|网易云|wyy|kugou|netease))?\s*(.*)$",
    name="search",
    display_name="点歌",
    priority=5,
    block=True,
    flags=0,
)

select_matcher = P.on_regex(r"^#(\d+)$", name="select",display_name="选择歌", flags=0)


def _platform_alias_to_key(alias: Optional[str]) -> Platform:
    if not alias:
        return "wangyiyun"
    a = alias.lower()
    if a in {"qq"}:
        return "qq"
    if a in {"酷狗", "kugou"}:
        return "kugou"
    if a in {"网易云", "wyy", "netease"}:
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
                f"?msg={quote_plus(keyword)}&limit=30"
            )
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            items = data.get("data") or []
            results: List[Song] = []
            for item in items:
                name = item.get("song") or "未知歌曲"
                artist = item.get("singers") or "未知歌手"
                mid = item.get("mid")
                cover = item.get("picture")
                results.append(
                    Song(
                        id=str(item.get("id") or mid or name),
                        name=name,
                        artist=artist,
                        cover=cover,
                        link=f"https://y.qq.com/n/ryqq/songDetail/{mid}" if mid else None,
                        mid=mid,
                    )
                )
            return results

        # wangyiyun
        url = f"http://datukuai.top:3000/search?keywords={quote_plus(keyword)}"
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        songs = (data.get("result") or {}).get("songs") or []
        results: List[Song] = []
        for s in songs:
            sid = str(s.get("id"))
            name = s.get("name") or "未知歌曲"
            artists = s.get("artists") or []
            artist = artists[0].get("name") if artists else "未知歌手"
            cover = None
            if s.get("al") and s["al"].get("picUrl"):
                cover = s["al"]["picUrl"]
            link = f"https://music.163.com/#/song?id={sid}"
            results.append(Song(id=sid, name=name, artist=artist, cover=cover, link=link))
        return results


def _lv_provider_from_platform(platform: Platform) -> Provider:
    if platform == "qq":
        return "tencent"
    if platform == "wangyiyun":
        return "netease"
    mcfg = cfg_music()
    pd = str(mcfg.get("provider_default") or "tencent").lower()
    return "netease" if pd == "netease" else "tencent"


async def _lv_search_songs(platform: Platform, keyword: str) -> List[Song]:
    mcfg = cfg_music()
    atime = cfg_api_timeouts()
    api_base = str(mcfg.get("api_base") or "https://api.vkeys.cn").rstrip("/")
    num = int(mcfg.get("search_num") or 20)
    prov = _lv_provider_from_platform(platform)
    timeout_sec = float(atime.get("music_api_timeout") or 15)
    timeout = httpx.Timeout(timeout_sec, connect=timeout_sec)
    async with httpx.AsyncClient(timeout=timeout) as client:
        url = f"{api_base}/v2/music/{prov}?word={quote_plus(keyword)}&num={num}"
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        items = data.get("data")
        if isinstance(items, dict):
            items = [items]
        items = items or []
        results: List[Song] = []
        for item in items:
            name = item.get("song") or "未知歌曲"
            artist = item.get("singer") or "未知歌手"
            mid = item.get("mid")
            sid = item.get("id")
            cover = item.get("cover")
            link = item.get("link")
            if not link:
                if prov == "tencent" and mid:
                    link = f"https://i.y.qq.com/v8/playsong.html?songmid={mid}"
                elif prov == "netease" and sid:
                    link = f"https://music.163.com/#/song?id={sid}"
            results.append(Song(id=str(sid or mid or name), name=str(name), artist=str(artist), cover=cover, link=link, mid=mid))
        return results


async def _lv_resolve_audio_url(platform: Platform, song: Song) -> Optional[str]:
    mcfg = cfg_music()
    atime = cfg_api_timeouts()
    api_base = str(mcfg.get("api_base") or "https://api.vkeys.cn").rstrip("/")
    prov = _lv_provider_from_platform(platform)
    quality = int(mcfg.get("quality") or 4)
    if prov == "netease":
        quality = max(1, min(9, quality))
    else:
        quality = max(0, min(16, quality))
    timeout_sec = float(atime.get("music_api_timeout") or 15)
    timeout = httpx.Timeout(timeout_sec, connect=timeout_sec)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            params = f"quality={quality}"
            if prov == "tencent":
                if song.mid:
                    url = f"{api_base}/v2/music/{prov}?mid={quote_plus(song.mid)}&{params}"
                else:
                    url = f"{api_base}/v2/music/{prov}?id={quote_plus(song.id)}&{params}"
            else:
                url = f"{api_base}/v2/music/{prov}?id={quote_plus(song.id)}&{params}"
            r = await client.get(url)
            r.raise_for_status()
            j = r.json()
            data = j.get("data") or {}
            audio_url = data.get("url")
            if audio_url:
                return audio_url
            return data.get("link")
        except Exception:
            logger.exception("resolve audio url failed")
            return None

async def _resolve_audio_url(platform: Platform, song: Song) -> Optional[str]:
    timeout = httpx.Timeout(10.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if platform == "wangyiyun":
                # Prefer public NCM API endpoint if available
                try:
                    r = await client.get(
                        f"http://datukuai.top:3000/song/url?id={song.id}"
                    )
                    if r.status_code == 200:
                        j = r.json()
                        data = (j.get("data") or [{}])[0]
                        url = data.get("url")
                        if url:
                            return url
                except Exception:
                    pass

                # Fallback to official API (requires cookie), optional via env var
                wy_ck = os.getenv("MUSIC_WYY_COOKIE", "")
                payload = {
                    "ids": f"[{song.id}]",
                    "level": "standard",
                    "encodeType": "mp3",
                }
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; Build/SKQ1.211230.001)",
                }
                if wy_ck:
                    headers["Cookie"] = f"MUSIC_U={wy_ck}"
                r = await client.post(
                    "https://music.163.com/api/song/enhance/player/url/v1",
                    data="&".join(f"{k}={v}" for k, v in payload.items()),
                    headers=headers,
                )
                if r.status_code == 200:
                    j = r.json()
                    data = (j.get("data") or [{}])[0]
                    return data.get("url")
                # Final fallback for NCM: public outer URL (may redirect)
                return f"http://music.163.com/song/media/outer/url?id={song.id}"

            if platform == "qq":
                url = (
                    "http://datukuai.top:1450/djs/API/QQ_Music/api.php"
                    f"?msg={quote_plus(song.name)}&n=1&q=7"
                )
                r = await client.get(url)
                r.raise_for_status()
                j = r.json()
                audio = (j.get("data") or {}).get("music")
                if audio:
                    return audio
                # Fallback: try using QQ mid when available
                if song.mid:
                    try:
                        r2 = await client.get(
                            "http://datukuai.top:1450/djs/API/QQ_Music/api.php"
                            f"?msg={quote_plus(song.mid)}&n=1&q=7"
                        )
                        r2.raise_for_status()
                        j2 = r2.json()
                        audio2 = (j2.get("data") or {}).get("music")
                        if audio2:
                            return audio2
                    except Exception:
                        pass
                return None

            if platform == "kugou":
                url = (
                    "https://wenxin110.top/api/kugou_music"
                    f"?msg={quote_plus(song.name)}&n=1"
                )
                r = await client.get(url)
                r.raise_for_status()
                text = r.text
                # The API returns a messy text; try to extract lines
                cleaned = (
                    text.replace("±", "")
                    .replace("\\", "")
                    .replace("img=", "")
                    .replace("播放地址", "")
                    .replace("\r", "")
                )
                parts = [p for p in cleaned.split("\n") if p.strip()]
                # Heuristic: expect [pic, name, artist, url]
                if len(parts) >= 4:
                    return parts[3].strip()
                return None
        except Exception as e:  # pragma: no cover - network errors
            logger.warning(f"resolve audio url failed: {e}")
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
    # 通用化的输出目录：默认使用项目下 data/temp/musicshare，可通过环境变量覆盖
    host_base_path = Path(os.getenv("NPE_MUSIC_VOICE_DIR") or (Path.cwd() / "data" / "temp" / "musicshare"))
    container_base_env = os.getenv("NPE_CONTAINER_VOICE_DIR")
    container_base_path: Optional[Path] = Path(container_base_env) if container_base_env else None

    try:
        # 确保主机上的临时目录存在
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
        # 输出 MP3 并设置采样率/码率
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
            if container_base_path:
                container_return_path = container_base_path / host_out_path.name
                logger.success(
                    f"FFmpeg created file {host_out_path}, returning container path {container_return_path}"
                )
                return container_return_path
            else:
                logger.success(
                    f"FFmpeg created file {host_out_path}, returning host path"
                )
                return host_out_path
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
    """Load only the bundled `font.ttf` from this plugin's resources.

    No fallback. If loading fails, raises an error explicitly.
    """
    res_dir = Path(__file__).parent / "resource"
    font_path = res_dir / "font.ttf"
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception as e:
        raise RuntimeError(
            f"Failed to load bundled font at {font_path}. Ensure 'font.ttf' exists and is valid. Error: {e}"
        )


def _make_song_list_image_grid(platform: Platform, keyword: str, songs: List[Song]) -> bytes:
    """A cleaner two-column song list image without covers."""
    title = f"为你在{_platform_name_human(platform)}找到以下歌曲"
    subtitle = f"关键词: {keyword}"

    # Layout settings
    pad_x, pad_y = 28, 24
    grid_gap_x, grid_gap_y = 18, 12
    bg_color = (246, 248, 251)
    fg_color = (34, 34, 34)
    accent_color = (80, 120, 200)
    card_bg = (255, 255, 255)
    card_border = (230, 234, 240)

    font_title = _load_font(30)
    font_subtitle = _load_font(20)
    font_item = _load_font(22)
    font_footer = _load_font(18)

    max_items = min(20, len(songs))

    # Measurement helpers
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)

    def text_size(text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    title_w, title_h = text_size(title, font_title)
    sub_w, sub_h = text_size(subtitle, font_subtitle)

    columns = 2
    col_min_width = 420
    grid_width = max(columns * col_min_width + (columns - 1) * grid_gap_x, title_w, sub_w)
    footer_text = "回复序号点歌，例如：1 或 #1"
    footer_w, footer_h = text_size(footer_text, font_footer)
    grid_width = max(grid_width, footer_w)

    # Wrap to fit column
    def wrap_to_width(text: str, font: ImageFont.ImageFont, max_w: int) -> str:
        if text_size(text, font)[0] <= max_w:
            return text
        ell = "…"
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi) // 2
            t = text[:mid] + ell
            if text_size(t, font)[0] <= max_w:
                lo = mid + 1
            else:
                hi = mid
        mid = max(1, lo - 1)
        return text[:mid] + ell

    card_inner_pad = 12
    badge_r = 12
    text_left_offset = badge_r * 2 + 10
    col_width = (grid_width - (columns - 1) * grid_gap_x) // columns

    # pre-measure cards
    card_height = 48
    rendered = []
    for i in range(max_items):
        line = f"{i+1}. {songs[i].name} - {songs[i].artist}"
        wrapped = wrap_to_width(line, font_item, col_width - card_inner_pad * 2 - text_left_offset)
        w, h = text_size(wrapped, font_item)
        card_height = max(card_height, h + card_inner_pad * 2)
        rendered.append((wrapped, w, h))

    rows = (max_items + columns - 1) // columns
    width = pad_x * 2 + grid_width
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

        # card
        d.rounded_rectangle([(x0, y0), (x1, y1)], radius=10, fill=card_bg, outline=card_border)

        # badge
        cx = x0 + card_inner_pad + badge_r
        cy = y0 + card_height // 2
        d.ellipse([(cx - badge_r, cy - badge_r), (cx + badge_r, cy + badge_r)], fill=accent_color)
        num_text = str(idx + 1)
        tw, th = text_size(num_text, font_footer)
        d.text((cx - tw / 2, cy - th / 2), num_text, fill=(255, 255, 255), font=font_footer)

        # text
        text_x = x0 + card_inner_pad + text_left_offset
        text_y = y0 + (card_height - rendered[idx][2]) // 2
        d.text((text_x, text_y), rendered[idx][0], fill=fg_color, font=font_item)

    # footer
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
        songs = await _lv_search_songs(platform, keyword)
    except Exception:
        logger.exception("search songs failed")
        await matcher.finish("搜索歌曲时发生错误，请稍后再试。")
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
        await matcher.finish("无效的歌曲序号，请检查后重试。")
        return

    platform, songs = USER_RESULTS[user_id]
    if index < 0 or index >= len(songs):
        await matcher.finish("无效的歌曲序号，请检查后重试。")
        return

    song = songs[index]
    await matcher.send(f"正在获取：{song.name} - {song.artist}，请稍等...")

    # 先尝试返回直链（若失败则后续返回跳转链接）
    audio_url = await _lv_resolve_audio_url(platform, song)

    # 若已转码并生成可用文件，直接 finish 发送，终止后续流程
    if audio_url:
        # 优先尝试通过远程直链发送语音（由适配器下载处理）
        try:
            await matcher.finish(MessageSegment.record(str(audio_url)))
        except FinishedException:
            raise
        except Exception as e:
            logger.warning(f"远程语音发送失败，尝试本地转码: {e}")
        try:
            local_path = await _download_audio_via_ffmpeg(
                audio_url, f"{song.name}-{song.artist}"
            )
            if local_path:
                await matcher.finish(
                    MessageSegment.record(local_path.resolve().as_uri())
                )
        except FinishedException:
            # 上层已经 finish，继续抛出
            raise
        except Exception as ee:
            logger.warning(f"本地转码发送失败: {ee}")

    # 最后返回 URL（平台直链或平台页）
    fallback = audio_url or song.link
    if fallback:
        await matcher.finish(f"{song.name} - {song.artist}\n{fallback}")
    else:
        await matcher.finish("播放失败：未能获取歌曲播放地址。")
