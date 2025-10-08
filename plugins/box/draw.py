import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import emoji


RESOURCE_DIR: Path = Path(__file__).resolve().parent / "resource"
FONT_PATH: Path = RESOURCE_DIR / "可爱字体.ttf"
EMOJI_FONT_PATH: Path = RESOURCE_DIR / "NotoColorEmoji.ttf"

FONT_SIZE = 35  # 字体大小
TEXT_PADDING = 10  # 文本与边框的间距
AVATAR_SIZE = None  # 头像大小（None 表示与文本高度一致）
BORDER_THICKNESS = 10  # 边框厚度
BORDER_COLOR_RANGE = (64, 255)  # 边框颜色范围
CORNER_RADIUS = 30  # 圆角大小

cute_font = ImageFont.truetype(str(FONT_PATH), FONT_SIZE)
emoji_font = ImageFont.truetype(str(EMOJI_FONT_PATH), FONT_SIZE)


def create_image(avatar: bytes, reply: list) -> bytes:
    reply_str = "\n".join(reply)
    # 创建临时图片计算文本的宽高，得到最图片高度
    temp_img = Image.new("RGBA", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    no_emoji_reply = "".join(
        "一"
        if getattr(emoji, "is_emoji", lambda c: c in getattr(emoji, "EMOJI_DATA", {}))(c)
        else c
        for c in reply_str
    )
    text_bbox = temp_draw.textbbox((0, 0), no_emoji_reply, font=cute_font)
    text_width, text_height = (
        int(text_bbox[2] - text_bbox[0]),
        int(text_bbox[3] - text_bbox[1]),
    )
    img_height = text_height + 2 * TEXT_PADDING
    # 调整头像为与文本高度相同的大小，得到图片的宽度   
    avatar_img = Image.open(BytesIO(avatar))
    avatar_size = AVATAR_SIZE if AVATAR_SIZE else text_height
    avatar_img = avatar_img.resize((avatar_size, avatar_size))
    img_width = avatar_img.width + text_width + 2 * TEXT_PADDING
    # 头像圆角后粘贴到图片左侧,垂直居中
    img = Image.new("RGBA", (img_width, img_height), color=(255, 255, 255, 255))
    mask = Image.new("L", (avatar_size, avatar_size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        [(0, 0), (avatar_size, avatar_size)], CORNER_RADIUS, fill=255
    )
    avatar_img.putalpha(mask)
    img.paste(avatar_img, (0, (img_height - avatar_size) // 2), mask)
    # 绘制文本到图片右�?    _draw_multi(img, reply_str, avatar_img.width + TEXT_PADDING, TEXT_PADDING)
    # 绘制一个随机颜色的边框
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


def _draw_multi(img, text, text_x=10, text_y=10):
    """在图片上绘制多语言文本（支持中英文、Emoji、符号和换行符）"""
    lines = text.split("\n")  # 按换行符分割文本
    current_y = text_y
    draw = ImageDraw.Draw(img)
    line_color = (
        random.randint(0, 128),
        random.randint(0, 128),
        random.randint(0, 128),
        random.randint(240, 255),
    )
    current_x = text_x
    for char in line:
        if char in getattr(emoji, "EMOJI_DATA", {}):
            draw.text(
                (current_x, current_y + 10),
                char,
                font=emoji_font,
                fill=line_color,
            )
            bbox = emoji_font.getbbox(char)
        else:
            draw.text(
                (current_x, current_y), char, font=cute_font, fill=line_color
            )
            bbox = cute_font.getbbox(char)
        current_x += bbox[2] - bbox[0]
    current_y += 40
    return img

