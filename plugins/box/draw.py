import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import emoji

from ...utils import plugin_resource_dir

_RES_PLUGIN: Path = plugin_resource_dir("box")


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        res = _RES_PLUGIN.joinpath(name)
        if res.is_file():
            return ImageFont.truetype(str(res), size)
    except Exception:
        pass
    return ImageFont.load_default()


def _pick_cute_font_name() -> str:
    # Prefer general font.ttf for readability (Chinese coverage)
    if _RES_PLUGIN.joinpath("font.ttf").is_file():
        return "font.ttf"
    # Then try 可爱字体.ttf
    if _RES_PLUGIN.joinpath("可爱字体.ttf").is_file():
        return "可爱字体.ttf"
    # Else pick any other ttf except emoji
    try:
        for p in list(_RES_PLUGIN.iterdir()):
            try:
                if p.suffix.lower() != ".ttf":
                    continue
                name = p.name.lower()
                if "notocoloremoji" in name:
                    continue
                return p.name
            except Exception:
                continue
    except Exception:
        pass
    return "font.ttf"

FONT_SIZE = 35  # 字体大小
TEXT_PADDING = 10  # 文本与边框的间距
AVATAR_SIZE = None  # 头像大小（None 表示与文本高度一致）
BORDER_THICKNESS = 10  # 边框厚度
BORDER_COLOR_RANGE = (64, 255)  # 边框颜色范围
CORNER_RADIUS = 30  # 圆角大小

_CUTE_FONT_NAME = _pick_cute_font_name()
cute_font = _load_font(_CUTE_FONT_NAME, FONT_SIZE)
emoji_font = _load_font("NotoColorEmoji.ttf", FONT_SIZE)


def create_image(avatar: bytes, reply: list) -> bytes:
    reply_str = "\n".join(reply)
    # 计算文本尺寸
    temp_img = Image.new("RGBA", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    no_emoji_reply = "".join("一" if (c in getattr(emoji, "EMOJI_DATA", {})) else c for c in reply_str)
    text_bbox = temp_draw.textbbox((0, 0), no_emoji_reply, font=cute_font)
    text_width, text_height = (
        int(text_bbox[2] - text_bbox[0]),
        int(text_bbox[3] - text_bbox[1]),
    )
    img_height = text_height + 2 * TEXT_PADDING

    # 头像与整体宽度
    avatar_img = Image.open(BytesIO(avatar))
    avatar_size = AVATAR_SIZE if AVATAR_SIZE else text_height
    avatar_img = avatar_img.resize((avatar_size, avatar_size))
    img_width = avatar_img.width + text_width + 2 * TEXT_PADDING

    # 合成图
    img = Image.new("RGBA", (img_width, img_height), color=(255, 255, 255, 255))
    mask = Image.new("L", (avatar_size, avatar_size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (avatar_size, avatar_size)], CORNER_RADIUS, fill=255)
    avatar_img.putalpha(mask)
    img.paste(avatar_img, (0, (img_height - avatar_size) // 2), mask)

    # 文本
    _draw_multi(img, reply_str, avatar_img.width + TEXT_PADDING, TEXT_PADDING)

    # 边框
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
    return img_byte_arr.getvalue()


def _draw_multi(img, text, text_x=10, text_y=10):
    """
    在图片上绘制多语言文本（支持中英文、Emoji、符号和换行符）
    """
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
            if char in getattr(emoji, "EMOJI_DATA", {}):
                draw.text((current_x, current_y + 10), char, font=emoji_font, fill=line_color)
                bbox = emoji_font.getbbox(char)
            else:
                draw.text((current_x, current_y), char, font=cute_font, fill=line_color)
                bbox = cute_font.getbbox(char)
            current_x += bbox[2] - bbox[0]
        current_y += 40
    return img
