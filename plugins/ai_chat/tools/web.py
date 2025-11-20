from __future__ import annotations

import json
import os
import re
import html as _html
import random
from urllib.parse import quote_plus
from typing import Any, Dict, List

from nonebot.log import logger

from . import register_tool
from ..config import get_config

try:  # 可选依赖
    import aiohttp
except Exception:  # pragma: no cover
    aiohttp = None  # type: ignore


_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
]


async def _http_get_text(url: str, timeout: int = 10) -> str:
    if aiohttp is None:
        raise RuntimeError("aiohttp 未安装，请先安装 aiohttp 以使用联网功能")
    headers = {"User-Agent": random.choice(_USER_AGENTS)}
    async with aiohttp.ClientSession(trust_env=True) as sess:
        async with sess.get(url, headers=headers, timeout=timeout) as resp:
            return await resp.text(errors="ignore")


async def _http_post_json(url: str, json_body: dict, headers: dict | None = None, timeout: int = 12) -> dict:
    if aiohttp is None:
        raise RuntimeError("aiohttp 未安装，请先安装 aiohttp 以使用联网功能")
    async with aiohttp.ClientSession(trust_env=True) as sess:
        async with sess.post(url, json=json_body, headers=headers or {}, timeout=timeout) as resp:
            txt = await resp.text()
            try:
                return json.loads(txt)
            except Exception:
                raise RuntimeError(f"HTTP {resp.status}, 非 JSON 响应: {txt[:200]}")


def _strip_html_keep_text(html_text: str) -> str:
    # 去掉脚本/样式/不可见元素等，仅保留文本
    s = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html_text)
    s = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", s)
    s = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def _search_tavily(query: str, max_results: int = 5, depth: str = "basic") -> List[dict]:
    key = (getattr(getattr(get_config(), 'session', None), 'tavily_api_key', '') or '').strip()
    if not key:
        raise RuntimeError("缺少 TAVILY_API_KEY 环境变量")
    payload = {
        "query": query,
        "max_results": max(1, min(int(max_results or 5), 10)),
        "search_depth": depth if depth in ("basic", "advanced") else "basic",
    }
    headers = {"Authorization": f"Bearer {key}"}
    data = await _http_post_json("https://api.tavily.com/search", payload, headers=headers)
    results = []
    for i, item in enumerate(data.get("results", [])[: payload["max_results"]], 1):
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        snippet = (item.get("content") or item.get("snippet") or "").strip()
        results.append({"idx": i, "title": title, "url": url, "snippet": snippet})
    return results


async def _search_bing_html(query: str, max_results: int = 5) -> List[dict]:
    q = quote_plus(query)
    url = f"https://cn.bing.com/search?q={q}&setlang=zh-CN&FORM=QBLH"
    html_text = await _http_get_text(url)
    blocks = re.findall(r"<li class=\"b_algo\"[\s\S]*?</li>", html_text, flags=re.I)
    results = []
    for blk in blocks:
        m = re.search(r"<h2[\s\S]*?<a[^>]+href=\"([^\"]+)\"[^>]*>([\s\S]*?)</a>[\s\S]*?</h2>", blk, flags=re.I)
        if not m:
            continue
        link = _html.unescape(m.group(1))
        title_raw = m.group(2)
        title = re.sub(r"<[^>]+>", " ", title_raw)
        title = _html.unescape(re.sub(r"\s+", " ", title).strip())
        # 提取摘要
        sm = re.search(r"<p>([\s\S]*?)</p>", blk, flags=re.I)
        snippet = ""
        if sm:
            sn = re.sub(r"<[^>]+>", " ", sm.group(1))
            snippet = _html.unescape(re.sub(r"\s+", " ", sn).strip())
        if not snippet:
            cm = re.search(r"<div class=\"b_caption\">[\s\S]*?<p>([\s\S]*?)</p>", blk, flags=re.I)
            if cm:
                sn = re.sub(r"<[^>]+>", " ", cm.group(1))
                snippet = _html.unescape(re.sub(r"\s+", " ", sn).strip())
        results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= max_results:
            break
    return [{"idx": i + 1, **r} for i, r in enumerate(results)]


@register_tool(
    name="web_search",
    description="联网搜索（Tavily 密钥从 session.tavily_api_key 读取；否则使用 Bing HTML 抓取）",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "description": "结果条数(1-10)", "default": 5},
            "provider": {"type": "string", "description": "搜索提供方: tavily|bing"},
            "link": {"type": "boolean", "description": "是否包含链接", "default": True},
            "search_depth": {"type": "string", "description": "Tavily 搜索深度: basic|advanced", "default": "basic"}
        },
        "required": ["query"]
    }
)
async def tool_web_search(query: str, max_results: int = 5, provider: str | None = None, link: bool = True, search_depth: str = "basic") -> str:
    """联网搜索：优先使用 Tavily（需 TAVILY_API_KEY），否则回退到 Bing HTML 抓取"""
    try:
        max_results = max(1, min(int(max_results or 5), 10))
    except Exception:
        max_results = 5

    # 选择 provider
    if provider:
        provider = provider.lower().strip()
    else:
        provider = 'tavily' if (getattr(getattr(get_config(), 'session', None), 'tavily_api_key', '') or '').strip() else 'bing'

    try:
        if provider == "tavily":
            results = await _search_tavily(query, max_results=max_results, depth=search_depth)
        else:
            results = await _search_bing_html(query, max_results=max_results)
    except Exception as e:
        logger.error(f"[AI Chat] web_search 失败: {e}")
        return f"Error: web_search failed: {e}"

    if not results:
        return "Error: no search results"

    lines: List[str] = []
    for r in results:
        head = f"{r.get('idx', '-')}. {r.get('title','').strip()}"
        if link and r.get("url"):
            head += f"\nURL: {r['url']}"
        snippet = (r.get("snippet") or "").strip()
        if snippet:
            lines.append(f"{head}\n{snippet}")
        else:
            lines.append(head)
    return "\n\n".join(lines)


@register_tool(
    name="fetch_url",
    description="抓取网页文本（会去除脚本/样式/标签等，仅保留前 max_chars 字符）",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "目标 URL"},
            "max_chars": {"type": "integer", "description": "最大返回字符数", "default": 1200},
            "timeout": {"type": "integer", "description": "超时(秒)", "default": 10}
        },
        "required": ["url"]
    }
)
async def tool_fetch_url(url: str, max_chars: int = 1200, timeout: int = 10) -> str:
    try:
        html_text = await _http_get_text(url, timeout=timeout)
        text = _strip_html_keep_text(html_text)
        if not text:
            return "Error: empty content"
        text = text[: max(200, min(int(max_chars or 1200), 5000))]
        return text
    except Exception as e:
        logger.error(f"[AI Chat] fetch_url 失败: {e}")
        return f"Error: fetch_url failed: {e}"
