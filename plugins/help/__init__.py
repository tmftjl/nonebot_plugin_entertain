from __future__ import annotations

from typing import Dict, Any, Optional
from pathlib import Path

from nonebot.params import RegexGroup
from nonebot.plugin import PluginMetadata
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageSegment

from ...registry import Plugin

# Reuse core logic from bundled nonebot_plugin_help package
from plugins.help.config import (
    load_help_config,
    resolve_help_config,
    help_config_filename,
    CFG_DIR,
)
try:
    from plugins.help.renderer import render_help_image  # type: ignore
except Exception:  # pragma: no cover
    render_help_image = None  # type: ignore


__plugin_meta__ = PluginMetadata(
    name="帮助",
    description="帮助图片（带 Playwright 渲染，内置兜底）",
    usage="发送：<关键词><帮助|菜单|功能>，如：群管帮助 / 娱乐帮助",
    type="application",
)

P = Plugin(enabled=True, level="all", scene="all")

# 触发：<关键词>(帮助|菜单|功能)
matcher = P.on_regex(r"^(?:#|/)?(.*?)\s*(帮助|菜单|功能)$", name="help", priority=12, block=True, enabled=True, level="all", scene="all")


@matcher.handle()
async def _(m: Matcher, groups: tuple = RegexGroup()):  # type: ignore[assignment]
    # groups: [keyword, suffix]
    cfg_input: Optional[str] = None
    if groups and len(groups) >= 1 and groups[0]:
        cfg_input = str(groups[0]).strip()

    resolved_name = resolve_help_config(cfg_input)
    if (cfg_input and str(cfg_input).strip()) and resolved_name is None:
        await m.skip()

    conf: Dict[str, Any] = load_help_config(resolved_name)
    title = conf.get("title") or "帮助"
    sub_title = conf.get("sub_title") or (cfg_input or "")
    footer = conf.get("footer")
    col_count = int(conf.get("col_count", 3))
    groups_data = conf.get("groups", []) or []

    # Cache to temp directory by config name
    tmp_dir = Path(__file__).parent / "temp"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    cfg_filename = help_config_filename(resolved_name)
    cache_name = cfg_filename.replace(".json", ".png")
    cache_file = tmp_dir / cache_name

    # Determine cache validity
    cfg_path = CFG_DIR / cfg_filename
    try:
        cache_mtime = cache_file.stat().st_mtime if cache_file.exists() else 0
        cfg_mtime = cfg_path.stat().st_mtime if cfg_path.exists() else 0
        # Invalidate cache when core code changes
        # Invalidate cache when core code changes
        code_files = [Path(__file__), Path(__file__).parent / 'renderer.py', Path(__file__).parent / 'config.py']
        code_mtime = max((p.stat().st_mtime for p in code_files if p.exists()), default=0)
        cache_valid = cache_file.exists() and cache_mtime >= max(cfg_mtime, code_mtime)
    except Exception:
        cache_valid = False

    img_bytes: bytes = b""
    if cache_valid:
        try:
            img_bytes = cache_file.read_bytes()
        except Exception:
            img_bytes = b""

    if not img_bytes:
        if render_help_image is not None:
            try:
                img_bytes = await render_help_image(
                    title=title,
                    sub_title=sub_title,
                    groups=groups_data,
                    col_count=col_count,
                    footer=footer,
                )
                try:
                    cache_file.write_bytes(img_bytes)
                except Exception:
                    pass
            except Exception:
                img_bytes = b""
        # Fallback when Playwright is unavailable or failed
        if not img_bytes:
            # Build a minimal text-based image using PIL
            try:
                from PIL import Image, ImageDraw, ImageFont
                text = f"{title}\n{sub_title}\n\n" + "\n".join(
                    f"【{g.get('group','')}】 " + ", ".join(str(it.get('title','')) for it in (g.get('list') or []))
                    for g in groups_data
                )
                font = None
                try:
                    font = ImageFont.truetype("arial.ttf", 22)
                except Exception:
                    font = ImageFont.load_default()
                lines = text.split("\n")
                w = max((len(l) for l in lines), default=20) * 22 // 2 + 40
                h = 30 + len(lines) * 28 + 30
                img = Image.new("RGB", (max(w, 480), max(h, 320)), (255, 255, 255))
                d = ImageDraw.Draw(img)
                y = 20
                for l in lines:
                    d.text((20, y), l, font=font, fill=(32, 32, 32))
                    y += 28
                from io import BytesIO
                buf = BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
            except Exception:
                pass

    if not img_bytes:
        await m.finish("帮助图片已生成但输出失败，或缺少 Playwright 运行环境。")
    await m.finish(MessageSegment.image(img_bytes))


