from __future__ import annotations
from ...core.constants import DEFAULT_HTTP_TIMEOUT


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
from .config import cfg_music


try:
    from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
except Exception:  # pragma: no cover - allow import without adapter during static analysis
    MessageEvent = object  # type: ignore

    class _Dummy:  # type: ignore
        @staticmethod
        def image(_: str):
            return None

        @staticmethod
        def record(_: str):
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


# In-memory search cache per user
USER_RESULTS: Dict[str, Tuple[Platform, List[Song]]] = {}


# Regex definitions
P = Plugin(name="entertain", display_name="濞变箰")
search_matcher = P.on_regex(
    r"^#鐐规瓕(?:(qq|閰风嫍|缃戞槗浜憒wyy|kugou|netease))?\s*(.*)$",
    name="search",
    display_name="鐐规瓕",
    priority=5,
    block=True,
    flags=0,
)

select_matcher = P.on_regex(r"^#(\d+)$", name="select",display_name="閫夋嫨姝?, flags=0)


def _platform_alias_to_key(alias: Optional[str]) -> Platform:
    if not alias:
        return "wangyiyun"
    a = alias.lower()
    if a in {"qq"}:
        return "qq"
    if a in {"閰风嫍", "kugou"}:
        return "kugou"
    if a in {"缃戞槗浜?, "wyy", "netease"}:
        return "wangyiyun"
    return "wangyiyun"


def _platform_name_human(p: Platform) -> str:
    return {"qq": "QQ闊充箰", "kugou": "閰风嫍闊充箰", "wangyiyun": "缃戞槗浜戦煶涔?}[p]


async def _search_songs(platform: Platform, keyword: str) -> List[Song]:
    return await _lv_search_songs(platform, keyword)


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
    api_base = str(mcfg.get("api_base") or "https://api.vkeys.cn").rstrip("/")
    num = int(mcfg.get("search_num") or 20)
    prov = _lv_provider_from_platform(platform)
    async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
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
            name = item.get("song") or "鏈煡姝屾洸"
            artist = item.get("singer") or "鏈煡姝屾墜"
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
    api_base = str(mcfg.get("api_base") or "https://api.vkeys.cn").rstrip("/")
    prov = _lv_provider_from_platform(platform)
    quality = int(mcfg.get("quality") or 4)
    if prov == "netease":
        quality = max(1, min(9, quality))
    else:
        quality = max(0, min(16, quality))
    async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
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
    return await _lv_resolve_audio_url(platform, song)


def _ffmpeg_path() -> Optional[str]:
    """Locate ffmpeg executable via env var or PATH."""
    env_bin = os.getenv("FFMPEG_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin
    which = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    return which


async def _download_audio_via_ffmpeg(url: str, name_hint: str) -> Optional[Path]:
    """
    涓嬭浇闊抽/杞爜涓?mp3锛屽苟杩斿洖 NapCat 瀹瑰櫒鍐呭彲鐢ㄧ殑璺緞
    """
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        logger.error("FFmpeg not found in PATH and FFMPEG_BIN not set; cannot download locally.")
        return None
    logger.info(f"Found ffmpeg executable at: {ffmpeg}")
    # 閫氱敤鍖栫殑杈撳嚭鐩綍锛氶粯璁や娇鐢ㄩ」鐩笅 data/temp/musicshare锛屽彲閫氳繃鐜鍙橀噺瑕嗙洊
    host_base_path = Path(os.getenv("NPE_MUSIC_VOICE_DIR") or (Path.cwd() / "data" / "temp" / "musicshare"))
    container_base_env = os.getenv("NPE_CONTAINER_VOICE_DIR")
    container_base_path: Optional[Path] = Path(container_base_env) if container_base_env else None

    try:
        # 纭繚涓绘満涓婄殑涓存椂鐩綍瀛樺湪
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
        # 杈撳嚭 MP3 骞惰缃噰鏍风巼/鐮佺巼
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
    title = f"涓轰綘鍦▄_platform_name_human(platform)}鎵惧埌浠ヤ笅姝屾洸"
    subtitle = f"鍏抽敭璇? {keyword}"

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
    footer_text = "鍥炲搴忓彿鐐规瓕锛屼緥濡傦細1 鎴?#1"
    footer_w, footer_h = text_size(footer_text, font_footer)
    grid_width = max(grid_width, footer_w)

    # Wrap to fit column
    def wrap_to_width(text: str, font: ImageFont.ImageFont, max_w: int) -> str:
        if text_size(text, font)[0] <= max_w:
            return text
        ell = "鈥?
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
        await matcher.finish("璇疯緭鍏ヨ鎼滅储鐨勬瓕鏇插悕锛屼緥濡傦細#鐐规瓕 鏅村ぉ")

    platform = _platform_alias_to_key(alias)
    try:
        songs = await _lv_search_songs(platform, keyword)
    except Exception:
        logger.exception("search songs failed")
        await matcher.finish("鎼滅储姝屾洸鏃跺彂鐢熼敊璇紝璇风◢鍚庡啀璇曘€?)
        return

    if not songs:
        await matcher.finish(
            f"鍦ㄢ€渰_platform_name_human(platform)}鈥濇湭鎵惧埌鈥渰keyword}鈥濈浉鍏崇殑姝屾洸"
        )
        return

    USER_RESULTS[event.get_user_id()] = (platform, songs)
    prov = _lv_provider_from_platform(platform)
    platform_for_display: Platform = "qq" if prov == "tencent" else "wangyiyun"
    img_bytes = _make_song_list_image_grid(platform_for_display, keyword, songs)
    b64 = base64.b64encode(img_bytes).decode()
    await matcher.finish(MessageSegment.image(f"base64://{b64}"))


@select_matcher.handle()
async def _(matcher: Matcher, event: MessageEvent, groups: Tuple[str] = RegexGroup()) -> None:
    user_id = event.get_user_id()
    if user_id not in USER_RESULTS:
        await matcher.finish("鎮ㄧ殑鐐规瓕璁板綍宸茶繃鏈燂紝璇峰厛鎼滅储姝屾洸銆備緥濡傦細#鐐规瓕 鏅村ぉ")
        return

    index_str = groups[0]
    try:
        index = int(index_str) - 1
    except Exception:
        await matcher.finish("鏃犳晥鐨勬瓕鏇插簭鍙凤紝璇锋鏌ュ悗閲嶈瘯銆?)
        return

    platform, songs = USER_RESULTS[user_id]
    if index < 0 or index >= len(songs):
        await matcher.finish("鏃犳晥鐨勬瓕鏇插簭鍙凤紝璇锋鏌ュ悗閲嶈瘯銆?)
        return

    song = songs[index]
    await matcher.send(f"姝ｅ湪鑾峰彇锛歿song.name} - {song.artist}锛岃绋嶇瓑...")

    # 鍏堝皾璇曡繑鍥炵洿閾撅紙鑻ュけ璐ュ垯鍚庣画杩斿洖璺宠浆閾炬帴锛?
    audio_url = await _lv_resolve_audio_url(platform, song)

    # 鑻ュ凡杞爜骞剁敓鎴愬彲鐢ㄦ枃浠讹紝鐩存帴 finish 鍙戦€侊紝缁堟鍚庣画娴佺▼
    if audio_url:
        # 浼樺厛灏濊瘯閫氳繃杩滅▼鐩撮摼鍙戦€佽闊筹紙鐢遍€傞厤鍣ㄤ笅杞藉鐞嗭級
        try:
            await matcher.finish(MessageSegment.record(str(audio_url)))
        except FinishedException:
            raise
        except Exception as e:
            logger.warning(f"杩滅▼璇煶鍙戦€佸け璐ワ紝灏濊瘯鏈湴杞爜: {e}")
        try:
            local_path = await _download_audio_via_ffmpeg(
                audio_url, f"{song.name}-{song.artist}"
            )
            if local_path:
                await matcher.finish(
                    MessageSegment.record(local_path.resolve().as_uri())
                )
        except FinishedException:
            # 涓婂眰宸茬粡 finish锛岀户缁姏鍑?
            raise
        except Exception as ee:
            logger.warning(f"鏈湴杞爜鍙戦€佸け璐? {ee}")

    # 鏈€鍚庤繑鍥?URL锛堝钩鍙扮洿閾炬垨骞冲彴椤碉級
    fallback = audio_url or song.link
    if fallback:
        await matcher.finish(f"{song.name} - {song.artist}\n{fallback}")
    else:
        await matcher.finish("鎾斁澶辫触锛氭湭鑳借幏鍙栨瓕鏇叉挱鏀惧湴鍧€銆?)









