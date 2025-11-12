from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import asyncio

from nonebot import get_driver
from nonebot.log import logger
from playwright.async_api import async_playwright, Browser


RES_DIR = Path(__file__).parent / "resources"

# Global Playwright resources (lazy)
_PW = None  # type: ignore[var-annotated]
_BROWSER: Optional[Browser] = None
_RENDER_SEM = asyncio.Semaphore(2)


def _data_uri(path: Path, mime: str) -> str:
    b = path.read_bytes()
    import base64

    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


def _inline_css() -> str:
    # Load common + help css and inline required assets as data URIs
    common_css = (RES_DIR / "common" / "common.css").read_text(encoding="utf-8")
    help_css = (RES_DIR / "help" / "index.css").read_text(encoding="utf-8")

    # Fonts
    fzb_woff = _data_uri(RES_DIR / "common" / "font" / "FZB.woff", "font/woff")
    fzb_ttf = _data_uri(RES_DIR / "common" / "font" / "FZB.ttf", "font/ttf")
    nzbz_woff = _data_uri(RES_DIR / "common" / "font" / "NZBZ.woff", "font/woff")
    nzbz_ttf = _data_uri(RES_DIR / "common" / "font" / "NZBZ.ttf", "font/ttf")
    common_css = (
        common_css.replace("./font/FZB.woff", fzb_woff)
        .replace("./font/FZB.ttf", fzb_ttf)
        .replace("./font/NZBZ.woff", nzbz_woff)
        .replace("./font/NZBZ.ttf", nzbz_ttf)
    )

    # Icon sprite
    icon_uri = _data_uri(RES_DIR / "help" / "icon.png", "image/png")
    help_css = help_css.replace("icon.png", icon_uri)

    return f"<style>{common_css}\n{help_css}</style>"


def _build_html(
    title: str,
    sub_title: str,
    groups: List[Dict[str, Any]],
    col_count: int,
    bg_file: str,
    footer: Optional[str] = None,
) -> str:
    def icon_css(idx: int) -> str:
        if not idx:
            return "display:none"
        x = (idx - 1) % 10
        y = (idx - x - 1) // 10
        return f"background-position:-{x * 50}px -{y * 50}px"

    def render_group(g: Dict[str, Any]) -> str:
        items = g.get("list", []) or []
        rows: List[str] = []
        step = max(col_count, 1)
        for i in range(0, len(items), step):
            chunk = items[i : i + step]
            tds: List[str] = []
            for it in chunk:
                css = icon_css(int(it.get("icon") or 0))
                tds.append(
                    f"<div class='td'><span class='help-icon' style='{css}'></span>"
                    f"<strong class='help-title'>{it.get('title','')}</strong>"
                    f"<span class='help-desc'>{it.get('desc','')}</span></div>"
                )
            while len(tds) < step:
                tds.append("<div class='td'></div>")
            rows.append(f"<div class='tr'>{''.join(tds)}</div>")
        table = f"<div class='help-table'>{''.join(rows)}</div>" if rows else ""
        return f"<div class='cont-box'><div class='help-group'>{g.get('group','')}</div>{table}</div>"

    groups_html = "".join(render_group(g) for g in groups)

    # Background inline
    bg_path = RES_DIR / "help" / "imgs" / bg_file
    ext = bg_path.suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    bg_uri = _data_uri(bg_path, mime)
    style_container_bg = f".container {{ background: url('{bg_uri}') center !important; background-size: cover !important; }}"

    footer_text = (
        footer
        if (footer is not None and str(footer).strip() != "")
        else "Created by dggb | Rendered by Playwright"
    )

    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset='utf-8'/>
        {_inline_css()}
        <style>{style_container_bg}</style>
      </head>
      <body>
        <div class='container'>
          <div class='info-box'>
            <div class='head-box'>
              <div class='title'>{title}</div>
              <div class='label'>{sub_title}</div>
            </div>
          </div>
          {groups_html}
          <div class='copyright'>{footer_text}</div>
        </div>
      </body>
    </html>
    """
    return html


async def render_help_image(
    title: str,
    sub_title: str,
    groups: List[Dict[str, Any]],
    col_count: int = 3,
    scale: float = 1.2,
    footer: Optional[str] = None,
) -> bytes:
    # Pick a background from imgs folder if multiple
    img_dir = RES_DIR / "help" / "imgs"
    bg = "default.jpg"
    try:
        imgs = [p.name for p in img_dir.iterdir() if p.is_file()]
        if imgs:
            import random
            bg = random.choice(imgs)
    except Exception:
        pass

    html = _build_html(title=title, sub_title=sub_title, groups=groups, col_count=col_count, bg_file=bg, footer=footer)

    # Ensure singleton browser
    async def _ensure_browser() -> Browser:
        global _PW, _BROWSER
        if _BROWSER is not None:
            return _BROWSER
        _PW = await async_playwright().start()
        _BROWSER = await _PW.chromium.launch()
        return _BROWSER

    try:
        async with _RENDER_SEM:
            browser = await _ensure_browser()
            page = await browser.new_page(device_scale_factor=scale)
            try:
                await asyncio.wait_for(page.set_content(html, wait_until="load"), timeout=15.0)
                el = await page.query_selector(".container")
                if el:
                    buf = await asyncio.wait_for(el.screenshot(type="png"), timeout=15.0)
                else:
                    buf = await asyncio.wait_for(page.screenshot(type="png", full_page=True), timeout=15.0)
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
        return buf
    except Exception as e:
        logger.warning(f"[help][renderer] Playwright 渲染失败，回退到 PIL: {e}")
        # Minimal fallback: render a simple text image
        try:
            from PIL import Image, ImageDraw, ImageFont

            W, H = 1200, 800
            im = Image.new("RGB", (W, H), (245, 247, 250))
            draw = ImageDraw.Draw(im)
            try:
                font_title = ImageFont.truetype(str(RES_DIR / "common" / "font" / "FZB.ttf"), 48)
                font_sub = ImageFont.truetype(str(RES_DIR / "common" / "font" / "FZB.ttf"), 28)
            except Exception:
                font_title = ImageFont.load_default()
                font_sub = ImageFont.load_default()
            draw.text((50, 60), title, fill=(30, 30, 30), font=font_title)
            draw.text((50, 120), sub_title, fill=(80, 80, 80), font=font_sub)
            y = 180
            for g in groups[:10]:
                name = str(g.get("group", ""))
                draw.text((50, y), f"- {name}", fill=(40, 40, 40), font=font_sub)
                y += 40
            import io as _io
            buf = _io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            # Last resort
            return b""


# Cleanup on bot shutdown
_driver = get_driver()


@_driver.on_shutdown
async def _shutdown_renderer() -> None:
    global _PW, _BROWSER
    try:
        if _BROWSER is not None:
            await _BROWSER.close()
    except Exception:
        pass
    finally:
        _BROWSER = None
    try:
        if _PW is not None:
            await _PW.stop()  # type: ignore[attr-defined]
    except Exception:
        pass
    finally:
        _PW = None
