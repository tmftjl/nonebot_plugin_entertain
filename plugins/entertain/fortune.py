from __future__ import annotations

import base64
import io
import json
import math
import random
from datetime import datetime
from typing import Any, Dict, List, Tuple

import aiofiles
import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.matcher import Matcher

from ...core.api import Plugin
from ...core.api import register_namespaced_config
from ...core.api import plugin_data_dir, plugin_resource_dir


DATA_DIR = plugin_data_dir("entertain")
JRYS_DEFS_FILE = DATA_DIR / "jrys_data.json"
USER_DATA_FILE = DATA_DIR / "user_fortunes.json"

_JRYS_DATA: List[Dict[str, Any]] = []
_USER_FORTUNES: Dict[str, Dict[str, Any]] = {}


P = Plugin(name="entertain")
_CFG = register_namespaced_config("entertain", "fortune", {})


def _load_fonts():
    def _load(size: int) -> ImageFont.FreeTypeFont:
        try:
            pres = plugin_resource_dir("entertain") / "font.ttf"
            if pres.is_file():
                return ImageFont.truetype(str(pres), size)
        except Exception:
            pass
        return ImageFont.load_default()

    font_main = _load(48)
    font_large = _load(90)
    font_medium = _load(32)
    font_small = _load(26)
    font_tiny = _load(22)
    return font_main, font_large, font_medium, font_small, font_tiny


FONT_MAIN, FONT_LARGE, FONT_MEDIUM, FONT_SMALL, FONT_TINY = _load_fonts()


async def _load_fortune_defs() -> None:
    global _JRYS_DATA
    if JRYS_DEFS_FILE.exists():
        try:
            async with aiofiles.open(JRYS_DEFS_FILE, "r", encoding="utf-8") as f:
                text = await f.read()
                _JRYS_DATA = json.loads(text)
        except Exception:
            _JRYS_DATA = []


async def _load_user_fortunes() -> None:
    global _USER_FORTUNES
    if USER_DATA_FILE.exists():
        try:
            async with aiofiles.open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                text = await f.read()
                _USER_FORTUNES = json.loads(text)
        except Exception:
            _USER_FORTUNES = {}


async def _save_user_fortunes() -> None:
    try:
        async with aiofiles.open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps(_USER_FORTUNES, ensure_ascii=False, indent=2))
    except Exception:
        pass


driver = get_driver()


@driver.on_startup
async def _on_startup():
    await _load_fortune_defs()
    await _load_user_fortunes()


@driver.on_shutdown
async def _on_shutdown():
    await _save_user_fortunes()


def _num_to_chinese(num: int) -> str:
    digits = "零一二三四五六七八九"
    if 1 <= num <= 9:
        return digits[num]
    if num == 10:
        return "十"
    if 10 < num < 20:
        return "十" + digits[num % 10]
    if num % 10 == 0:
        return digits[num // 10] + "十"
    return digits[num // 10] + "十" + digits[num % 10]


async def _get_background_image() -> Image.Image | None:
    local_api_url = "http://127.0.0.1:1520/api/wuthering_waves/role_image/random"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(local_api_url, timeout=10.0)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception:
        return None


def _sanitize_stars(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch in {"★", "☆"})


def _draw_wrapped_text(text: str, max_chars: int) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: List[str] = []
    for paragraph in text.split("\n"):
        buf = ""
        for ch in paragraph:
            if len(buf) >= max_chars:
                lines.append(buf)
                buf = ch
            else:
                buf += ch
        if buf:
            lines.append(buf)
    return "\n".join(lines)


def _draw_star_rating(
    draw: ImageDraw.ImageDraw,
    center_x: float,
    y: float,
    rating_string: str,
    star_size: int = 30,
    spacing: int = 10,
    fill_color=(0, 0, 0, 220),
    stroke_color=(0, 0, 0, 220),
    stroke_width: int = 2,
):
    s = _sanitize_stars(rating_string)
    n = len(s)
    total_width = n * star_size + (n - 1) * spacing if n > 0 else 0
    start_x = center_x - total_width / 2
    current_x = start_x
    for ch in s:
        cx = current_x + star_size / 2
        vertices = []
        for i in range(10):
            ang = math.pi / 5 * i - math.pi / 2
            radius = star_size / 2 if i % 2 == 0 else star_size / 4
            vertices.append((cx + radius * math.cos(ang), y + radius * math.sin(ang)))
        if ch == "★":
            draw.polygon(vertices, fill=fill_color)
        else:
            draw.polygon(vertices, outline=stroke_color, width=stroke_width)
        current_x += star_size + spacing


def _generate_fortune_canvas(
    nickname: str, data: Dict[str, Any], background: Image.Image | None = None
) -> Image.Image:
    CANVAS_WIDTH, CANVAS_HEIGHT = 650, 1000
    if background is None:
        bg = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (255, 255, 255, 255))
    else:
        bg = ImageOps.fit(background, (CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS)

    overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (255, 255, 255, 180))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(bg)

    fortune = data.get("fortune", {})
    y = 80
    cx = CANVAS_WIDTH / 2
    color = (0, 0, 0, 220)

    day_str = _num_to_chinese(datetime.now().day)
    title = f"{nickname} 的{day_str}日运势"
    draw.text((cx, y), title, font=FONT_TINY, fill=color, anchor="mm")
    y += 80

    summary = fortune.get("fortuneSummary", "今日运势")
    draw.text((cx, y), summary, font=FONT_LARGE, fill=color, anchor="mm")
    y += 120

    lucky_star = fortune.get("luckyStar", "")
    if lucky_star:
        _draw_star_rating(draw, cx, y, lucky_star, star_size=30, spacing=10)
    y += 100

    sign_text = fortune.get("signText", "")
    if sign_text:
        draw.text((cx, y), sign_text, font=FONT_MEDIUM, fill=color, anchor="mm")
        y += 80

    draw.line([(cx - 150, y), (cx + 150, y)], fill=(0, 0, 0, 100), width=2)
    y += 60

    unsign_text = fortune.get("unsignText", "")
    wrapped = _draw_wrapped_text(unsign_text, 22)
    draw.multiline_text((cx, y), wrapped, font=FONT_SMALL, fill=color, anchor="ma", spacing=15, align="center")

    footer = "| 仅供参考，切勿拘泥 |"
    draw.text((cx, CANVAS_HEIGHT - 50), footer, font=FONT_TINY, fill=(0, 0, 0, 150), anchor="mm")

    return bg


def _pil_to_base64_image(pil_img: Image.Image) -> str:
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"base64://{b64}"


def _get_or_create_today_fortune(user_id: str) -> Tuple[Dict[str, Any], bool]:
    today = datetime.now().strftime("%Y-%m-%d")
    rec = _USER_FORTUNES.get(user_id)
    if rec and rec.get("time") == today:
        return rec, False
    if not _JRYS_DATA:
        raise ValueError("运势库为空，无法生成")
    new_data = {"fortune": random.choice(_JRYS_DATA), "time": today}
    _USER_FORTUNES[user_id] = new_data
    return new_data, True


fortune_cmd = P.on_regex(
    r"^(?:[/#])?(?:今日运势|运势|抽签)$",
    name="today",
    priority=5,
    block=True,
)


@fortune_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent):
    user_id = str(event.user_id)
    nickname = (
        getattr(event.sender, "card", None)
        or getattr(event.sender, "nickname", None)
        or f"用户{user_id}"
    )

    try:
        data, _ = _get_or_create_today_fortune(user_id)
    except Exception as e:
        await matcher.finish(f"生成失败：{e}")

    bg_img = await _get_background_image()
    final_img = _generate_fortune_canvas(nickname, data, background=bg_img)
    image_seg = MessageSegment.image(_pil_to_base64_image(final_img))
    await matcher.finish(Message(image_seg))
