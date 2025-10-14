import io
import random
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import emoji

from ...utils import plugin_resource_dir


FONT_SIZE = 35
TEXT_PADDING = 10
AVATAR_SIZE = None
BORDER_THICKNESS = 10
BORDER_COLOR_RANGE = (64, 255)
CORNER_RADIUS = 30


def _resolve_font_paths() -> tuple[Path, Path]:
    res_dir = plugin_resource_dir("entertain")
    # Prefer cute font filename; fall back to font.ttf
    cute = res_dir / "可爱字体.ttf"
    if not cute.exists():
        cute = res_dir / "font.ttf"
    emoji_font = res_dir / "NotoColorEmoji.ttf"
    return cute, emoji_font


def _load_fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    cute_path, emoji_path = _resolve_font_paths()
    try:
        cute_font = ImageFont.truetype(str(cute_path), FONT_SIZE)
    except Exception:
        cute_font = ImageFont.load_default()
    try:
        emoji_font = ImageFont.truetype(str(emoji_path), FONT_SIZE)
    except Exception:
        emoji_font = ImageFont.load_default()
    return cute_font, emoji_font


def create_image(avatar: bytes, reply: list) -> bytes:
    cute_font, emoji_font = _load_fonts()
    reply_str = "\n".join(reply)
    temp_img = Image.new("RGBA", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    no_emoji_reply = "".join(
        "一" if getattr(emoji, "is_emoji", lambda c: c in getattr(emoji, "EMOJI_DATA", {}))(c) else c
        for c in reply_str
    )
    text_bbox = temp_draw.textbbox((0, 0), no_emoji_reply, font=cute_font)
    text_width, text_height = (
        int(text_bbox[2] - text_bbox[0]),
        int(text_bbox[3] - text_bbox[1]),
    )
    img_height = text_height + 2 * TEXT_PADDING

    avatar_img = Image.open(BytesIO(avatar))
    avatar_size = AVATAR_SIZE if AVATAR_SIZE else text_height
    avatar_img = avatar_img.resize((avatar_size, avatar_size))
    img_width = avatar_img.width + text_width + 2 * TEXT_PADDING

    img = Image.new("RGBA", (img_width, img_height), color=(255, 255, 255, 255))
    mask = Image.new("L", (avatar_size, avatar_size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (avatar_size, avatar_size)], CORNER_RADIUS, fill=255)
    avatar_img.putalpha(mask)
    img.paste(avatar_img, (0, (img_height - avatar_size) // 2), mask)

    _draw_multi(img, reply_str, cute_font, emoji_font, avatar_img.width + TEXT_PADDING, TEXT_PADDING)

    border_color = (
        random.randint(*BORDER_COLOR_RANGE),
        random.randint(*BORDER_COLOR_RANGE),
        random.randint(*BORDER_COLOR_RANGE),
    )
    border_img = Image.new(
        mode="RGBA",
        size=(img_width + BORDER_THICKNESS * 2, img_height + BORDER_THICKNESS * 2),
        color=border_color,
    )
    border_img.paste(img, (BORDER_THICKNESS, BORDER_THICKNESS))

    img_byte_arr = io.BytesIO()
    border_img.save(img_byte_arr, format="PNG")
    img_byte_arr = img_byte_arr.getvalue()
    return img_byte_arr


def _draw_multi(img, text, cute_font, emoji_font, text_x=10, text_y=10):
    lines = text.split("\n")
    current_y = text_y
    draw = ImageDraw.Draw(img)
    line_color = (
        random.randint(0, 128),
        random.randint(0, 128),
        random.randint(0, 128),
        random.randint(240, 255),
    )
    for line in lines:
        current_x = text_x
        for char in line:
            if char in getattr(emoji, "EMOJI_DATA", {}):
                draw.text((current_x, current_y + 10), char, font=emoji_font, fill=line_color)
                bbox = emoji_font.getbbox(char)
            else:
                draw.text((current_x, current_y), char, font=cute_font, fill=line_color)
                bbox = cute_font.getbbox(char)
            current_x += bbox[2] - bbox[0]
        current_y += 40
    return img

