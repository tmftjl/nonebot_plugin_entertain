from __future__ import annotations

import io
import random
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    import emoji  # type: ignore
except Exception:  # pragma: no cover
    emoji = None  # type: ignore


RESOURCE_DIR: Path = Path(__file__).resolve().parent / "resource"
FONT_PATH: Path = RESOURCE_DIR / "可爱字体.ttf"
EMOJI_FONT_PATH: Path = RESOURCE_DIR / "NotoColorEmoji.ttf"

FONT_SIZE = 35
TEXT_PADDING = 10
AVATAR_SIZE = None  # use text height
BORDER_THICKNESS = 10
BORDER_COLOR_RANGE = (64, 255)
CORNER_RADIUS = 30


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.load_default()


cute_font = _load_font(FONT_PATH, FONT_SIZE)
emoji_font = _load_font(EMOJI_FONT_PATH, FONT_SIZE)


def create_image(avatar: bytes, reply: list[str]) -> bytes:
    reply_str = "\n".join(reply)

    # measure text using a temporary image
    temp_img = Image.new("RGBA", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)

    # Replace emoji with placeholder of same advance for measurement when emoji lib present
    if emoji is not None:
        no_emoji_reply = "".join("一" if getattr(emoji, "is_emoji", None) and emoji.is_emoji(c) else c for c in reply_str)
    else:
        no_emoji_reply = reply_str

    text_bbox = temp_draw.textbbox((0, 0), no_emoji_reply, font=cute_font)
    text_width = int(text_bbox[2] - text_bbox[0])
    text_height = int(text_bbox[3] - text_bbox[1])
    img_height = text_height + 2 * TEXT_PADDING

    # avatar sizing
    avatar_img = Image.open(BytesIO(avatar)).convert("RGBA")
    avatar_size = AVATAR_SIZE if AVATAR_SIZE else text_height
    avatar_img = avatar_img.resize((max(1, avatar_size), max(1, avatar_size)))

    img_width = avatar_img.width + text_width + 2 * TEXT_PADDING

    # compose base image
    img = Image.new("RGBA", (img_width, img_height), color=(255, 255, 255, 255))

    # rounded avatar mask
    mask = Image.new("L", (avatar_img.width, avatar_img.height), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle(
        [(0, 0), (avatar_img.width, avatar_img.height)], CORNER_RADIUS, fill=255
    )
    avatar_img.putalpha(mask)
    img.paste(avatar_img, (0, (img_height - avatar_img.height) // 2), mask)

    # render text to the right of avatar
    _draw_multi(img, reply_str, avatar_img.width + TEXT_PADDING, TEXT_PADDING)

    # border with random color
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

    buf = io.BytesIO()
    border_img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_multi(img: Image.Image, text: str, text_x: int = 10, text_y: int = 10) -> Image.Image:
    lines = text.split("\n")
    current_y = text_y
    draw = ImageDraw.Draw(img)

    for line in lines:
        line_color = (
            random.randint(0, 128),
            random.randint(0, 128),
            random.randint(0, 128),
            random.randint(240, 255),
        )
        current_x = text_x
        for char in line:
            is_emoji = False
            if emoji is not None:
                try:
                    # emoji.EMOJI_DATA exists in emoji>=2.0
                    is_emoji = char in getattr(emoji, "EMOJI_DATA", {})
                except Exception:
                    is_emoji = False
            if is_emoji:
                draw.text((current_x, current_y + 10), char, font=emoji_font, fill=line_color)
                bbox = emoji_font.getbbox(char)
            else:
                draw.text((current_x, current_y), char, font=cute_font, fill=line_color)
                bbox = cute_font.getbbox(char)
            current_x += (bbox[2] - bbox[0])
        current_y += 40
    return img

