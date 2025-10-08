from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright


RES_DIR = Path(__file__).parent / "resources"


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
        else "Created by TRSS-Yunzai & (style) Yenai-Plugin | Rendered by Playwright"
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

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(device_scale_factor=scale)
        await page.set_content(html, wait_until="load")
        el = await page.query_selector(".container")
        if el:
            buf = await el.screenshot(type="png")
        else:
            buf = await page.screenshot(type="png", full_page=True)
        await browser.close()
    return buf
