from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple
from urllib.parse import quote_plus

import httpx
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup
from nonebot.exception import FinishedException
from PIL import Image, ImageDraw, ImageFont

from ...core.api import Plugin, KeyValueCache
from ...core.http import get_shared_async_client
from ...core.constants import DEFAULT_HTTP_TIMEOUT
from .config import cfg_music

try:
    from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
except Exception:
    MessageEvent = object  # type: ignore
    class _Dummy:
        @staticmethod
        def image(_): return None
        @staticmethod
        def record(_): return None
    MessageSegment = _Dummy  # type: ignore

Platform = Literal["qq", "netease"]

@dataclass
class Song:
    id: int
    mid: Optional[str]
    vid: str
    song: str
    subtitle: str
    album: str
    singer: str
    cover: str
    pay: str
    time: str
    type: int
    bpm: int
    quality: str
    grp: List['Song']
    link: Optional[str] = None
    interval: Optional[str] = None
    size: Optional[str] = None
    kbps: Optional[str] = None
    url: Optional[str] = None

USER_RESULTS = KeyValueCache(ttl=600)

P = Plugin(name="entertain", display_name="娱乐")

search_matcher = P.on_regex(
    r"^#点歌(?:(qq|网易云|netease))?\s*(.*)$",
    name="search",
    display_name="点歌",
    priority=5,
    block=True
)

select_matcher = P.on_regex(
    r"^#(\d+)$",
    name="select",
    display_name="选择歌"
)

def _normalize_platform(alias: Optional[str]) -> Platform:
    if not alias:
        return "netease"
    a = alias.lower()
    if a in {"qq"}:
        return "qq"
    return "netease"

def _platform_name_cn(p: Platform) -> str:
    return {"qq": "QQ音乐", "netease": "网易云音乐"}[p]

async def _search_songs_api(platform: Platform, keyword: str) -> List[Song]:
    mcfg = cfg_music()
    api_base = str(mcfg.get("api_base") or "https://api.vkeys.cn").rstrip("/")
    num = int(mcfg.get("search_num") or 10)

    if platform == "qq":
        url = f"{api_base}/v2/music/tencent/search/song"
    else:
        url = f"{api_base}/v2/music/netease"

    params = {
        "word": keyword,
        "num": num
    }

    client = await get_shared_async_client()
    resp = await client.get(url, params=params, timeout=DEFAULT_HTTP_TIMEOUT)
    resp.raise_for_status()

    data = resp.json()

    if data.get("code") != 200:
        error_msg = data.get("message", "API返回错误")
        logger.error(f"API错误 - 平台: {platform}, URL: {url}, 参数: {params}, 响应码: {data.get('code')}, 消息: {error_msg}")
        raise Exception(f"{error_msg}（{platform}音乐服务可能暂时不可用）")

    items = data.get("data", [])
    if isinstance(items, dict):
        items = [items]

    results = []
    for item in items:
        song_id = item.get("id", 0)
        mid = item.get("mid")
        vid = item.get("vid", "")
        song_name = item.get("song", "未知歌曲")
        subtitle = item.get("subtitle", "")
        album = item.get("album", "")
        singer = item.get("singer", "未知歌手")
        cover = item.get("cover", "")
        pay = item.get("pay", "")
        song_time = item.get("time", "")
        song_type = item.get("type", 0)
        bpm = item.get("bpm", 0)
        quality = item.get("quality", "")

        link = item.get("link")
        if not link:
            if platform == "qq" and mid:
                link = f"https://i.y.qq.com/v8/playsong.html?songmid={mid}&type={song_type}"
            elif platform == "netease" and song_id:
                link = f"https://music.163.com/#/song?id={song_id}"

        grp_list = []
        for grp_item in item.get("grp", []):
            grp_song = Song(
                id=grp_item.get("id", 0),
                mid=grp_item.get("mid"),
                vid=grp_item.get("vid", ""),
                song=grp_item.get("song", ""),
                subtitle=grp_item.get("subtitle", ""),
                album=grp_item.get("album", ""),
                singer=grp_item.get("singer", ""),
                cover=grp_item.get("cover", ""),
                pay=grp_item.get("pay", ""),
                time=grp_item.get("time", ""),
                type=grp_item.get("type", 0),
                bpm=grp_item.get("bpm", 0),
                quality=grp_item.get("quality", ""),
                grp=[]
            )
            grp_list.append(grp_song)

        results.append(Song(
            id=song_id,
            mid=mid,
            vid=vid,
            song=song_name,
            subtitle=subtitle,
            album=album,
            singer=singer,
            cover=cover,
            pay=pay,
            time=song_time,
            type=song_type,
            bpm=bpm,
            quality=quality,
            grp=grp_list,
            link=link
        ))

    return results

async def _get_song_url_api(platform: Platform, song: Song) -> Optional[str]:
    mcfg = cfg_music()
    api_base = str(mcfg.get("api_base") or "https://api.vkeys.cn").rstrip("/")
    quality = int(mcfg.get("quality") or 14)

    if platform == "qq":
        url = f"{api_base}/v2/music/tencent/geturl"
        params = {"quality": quality, "type": song.type}
        if song.mid:
            params["mid"] = song.mid
        else:
            params["id"] = song.id
    else:
        url = f"{api_base}/v2/music/netease"
        params = {"id": song.id, "quality": quality}

    client = await get_shared_async_client()
    try:
        resp = await client.get(url, params=params, timeout=DEFAULT_HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 200:
            logger.error(f"获取播放链接失败 - 平台: {platform}, 歌曲: {song.song}, 响应码: {data.get('code')}, 消息: {data.get('message')}")
            return None

        result = data.get("data", {})
        return result.get("url")
    except Exception as e:
        logger.error(f"获取音乐链接失败: {e}")
        return None

def _load_font(size: int):
    from pathlib import Path
    try:
        font_path = Path(__file__).parent / "resource" / "font.ttf"
        return ImageFont.truetype(str(font_path), size)
    except Exception:
        return ImageFont.load_default()

def _draw_music_list(platform: Platform, keyword: str, songs: List[Song]) -> bytes:
    BG_COLOR = (240, 242, 245)
    HEADER_COLOR = (64, 84, 180)
    CARD_BG = (255, 255, 255)
    TEXT_MAIN = (30, 30, 30)
    TEXT_SUB = (100, 100, 100)
    ACCENT = (64, 84, 180)

    PADDING = 30
    COLUMNS = 2
    GAP_X = 20
    GAP_Y = 15
    CARD_H = 70
    COL_W = 400

    font_title = _load_font(36)
    font_sub = _load_font(22)
    font_song = _load_font(26)
    font_artist = _load_font(20)
    font_badge = _load_font(20)
    font_footer = _load_font(18)

    count = min(len(songs), 20)
    rows = (count + COLUMNS - 1) // COLUMNS

    header_h = 120
    list_h = rows * CARD_H + (rows - 1) * GAP_Y
    footer_h = 50

    w = PADDING * 2 + COL_W * COLUMNS + GAP_X * (COLUMNS - 1)
    h = header_h + list_h + footer_h + PADDING

    im = Image.new("RGB", (w, h), BG_COLOR)
    draw = ImageDraw.Draw(im)

    draw.rectangle([(0, 0), (w, header_h)], fill=HEADER_COLOR)
    draw.text((PADDING, 25), f"搜索结果: {keyword}", font=font_title, fill=(255, 255, 255))

    plat_name = _platform_name_cn(platform)
    draw.text((PADDING, 75), f"来源: {plat_name} | 共找到 {len(songs)} 首歌曲", font=font_sub, fill=(220, 220, 255))

    start_y = header_h + 20

    for i in range(count):
        song = songs[i]
        row = i // COLUMNS
        col = i % COLUMNS

        x = PADDING + col * (COL_W + GAP_X)
        y = start_y + row * (CARD_H + GAP_Y)

        draw.rounded_rectangle([(x, y), (x + COL_W, y + CARD_H)], radius=8, fill=CARD_BG)

        badge_size = 36
        bx = x + 15
        by = y + (CARD_H - badge_size) // 2
        draw.ellipse([(bx, by), (bx + badge_size, by + badge_size)], fill=BG_COLOR)

        idx_str = str(i + 1)
        bbox = draw.textbbox((0, 0), idx_str, font=font_badge)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((bx + (badge_size - tw) / 2, by + (badge_size - th) / 2 - 2), idx_str, fill=ACCENT, font=font_badge)

        text_x = bx + badge_size + 15
        content_w = COL_W - (text_x - x) - 10

        song_name = song.song
        while draw.textlength(song_name, font=font_song) > content_w and len(song_name) > 1:
            song_name = song_name[:-2] + "…"

        draw.text((text_x, y + 12), song_name, fill=TEXT_MAIN, font=font_song)
        draw.text((text_x, y + 42), f"{song.singer}", fill=TEXT_SUB, font=font_artist)

    footer_text = "发送 #序号 (如 #1) 即可播放"
    bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    fw = bbox[2] - bbox[0]
    draw.text(((w - fw) / 2, h - 30), footer_text, fill=(150, 150, 150), font=font_footer)

    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()

@search_matcher.handle()
async def _(matcher: Matcher, event: MessageEvent, groups: Tuple[Optional[str], str] = RegexGroup()) -> None:
    alias, keyword = groups
    keyword = (keyword or "").strip()
    if not keyword:
        await matcher.finish("请提供关键词，例如：#点歌 晴天")

    platform = _normalize_platform(alias)

    try:
        songs = await _search_songs_api(platform, keyword)
    except Exception as e:
        logger.exception("搜索失败")
        await matcher.finish(f"搜索出错: {e}")
        return

    if not songs:
        await matcher.finish(f"在 {_platform_name_cn(platform)} 未找到相关歌曲。")

    USER_RESULTS.set(event.get_user_id(), (platform, songs))

    try:
        img_bytes = _draw_music_list(platform, keyword, songs)
        b64 = base64.b64encode(img_bytes).decode()
        await matcher.finish(MessageSegment.image(f"base64://{b64}"))
    except FinishedException:
        raise
    except Exception as e:
        logger.exception("图片生成失败")
        await matcher.finish("图片生成失败，请查看后台日志。")

@select_matcher.handle()
async def _(matcher: Matcher, event: MessageEvent, groups: Tuple[str] = RegexGroup()) -> None:
    user_id = event.get_user_id()
    cached = USER_RESULTS.get(user_id)
    if not cached:
        await matcher.finish("点歌会话已过期，请重新搜索。")
        return

    platform, songs = cached
    try:
        index = int(groups[0]) - 1
    except ValueError:
        await matcher.finish("序号无效。")
        return

    if not (0 <= index < len(songs)):
        await matcher.finish("序号超出范围。")
        return

    song = songs[index]
    await matcher.send(f"正在解析：{song.song} - {song.singer}...")

    audio_url = await _get_song_url_api(platform, song)

    if audio_url:
        try:
            await matcher.finish(MessageSegment.record(audio_url))
        except FinishedException:
            raise
        except Exception as e:
            logger.warning(f"语音发送失败: {e}")

    fallback_link = audio_url or song.link
    if fallback_link:
        await matcher.finish(f"播放失败，请点击链接收听：\n{song.song}\n{fallback_link}")
    else:
        await matcher.finish("无法获取该歌曲的播放地址。")
