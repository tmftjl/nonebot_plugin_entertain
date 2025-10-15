from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import RegexGroup

from ...core.api import Plugin
from ...core.api import register_namespaced_config


DEFAULT_CFG: Dict[str, Any] = {
    "api_url": "http://127.0.0.1:8899/stats/api",
    "username": "",
    "password": "",
    "timeout": 20,
}


REG = register_namespaced_config("useful", "taffy", DEFAULT_CFG)


def _load_cfg() -> Dict[str, Any]:
    return REG.load()

# 模块加载时写入默认配置，避免 config/useful/config.json 为空
try:
    _ = _load_cfg()
except Exception:
    pass


def _fmt_bytes(b: Optional[int]) -> str:
    try:
        if b is None:
            return "0 B"
        b = int(b)
        unit = 1024
        if b < unit:
            return "{} B".format(b)
        exp = 0
        v = float(b)
        while v >= unit and exp < 6:
            v /= unit
            exp += 1
        suffix = ("KMGTPE"[exp - 1] + "iB") if exp > 0 else "B"
        return "{:.2f} {}".format(v, suffix)
    except Exception:
        return str(b)


P = Plugin(name="useful")
taffy_cmd = P.on_regex(r"^#?查询流量\s*(.*)$", name="query", block=True, priority=13)


@taffy_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent, groups: tuple = RegexGroup()):
    cfg = _load_cfg()
    api_url = str(cfg.get("api_url") or "").strip()
    if not api_url:
        await matcher.finish("未配置 Taffy API 地址，请在 config/useful/config.json 写入 api_url")

    try:
        query_user = (groups[0] or "").strip() if groups else ""
    except Exception:
        query_user = ""
    url = api_url
    if query_user:
        from urllib.parse import urlencode
        url += ("?" + urlencode({"user": query_user}))

    headers = {"User-Agent": "NoneBot Taffy-Plugin"}
    username = str(cfg.get("username") or "").strip()
    password = str(cfg.get("password") or "").strip()
    if username and password:
        import base64
        raw = "{}:{}".format(username, password)
        auth = base64.b64encode(raw.encode()).decode()
        headers["Authorization"] = "Basic {}".format(auth)

    timeout = int(cfg.get("timeout") or 20)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        await matcher.finish("请求API失败: {}".format(e))
        return
    except Exception:
        await matcher.finish("查询失败：无法连接到服务器或数据格式异常")
        return

    lines = ["--- 代理服务状态 ---"]
    if query_user:
        found = bool(data.get("found"))
        user = data.get("single_user") or {}
        if found and isinstance(user, dict):
            up = user.get("upstream_bytes")
            down = user.get("downstream_bytes")
            total = (up or 0) + (down or 0)
            lines.append("[用户名: {}]".format(user.get("username", "")))
            lines.append("已请求次数: {}".format(user.get("total_requests", 0)))
            lines.append("上行流量: {}".format(_fmt_bytes(up)))
            lines.append("下行流量: {}".format(_fmt_bytes(down)))
            lines.append("累计流量: {}".format(_fmt_bytes(total)))
        else:
            lines.append("未找到用户[{}] 的统计信息".format(query_user))
    else:
        lines.append("[所有用户]")
        users = data.get("all_users") or []
        if isinstance(users, list) and users:
            for u in users:
                try:
                    up = u.get("upstream_bytes")
                    down = u.get("downstream_bytes")
                    total = (up or 0) + (down or 0)
                    lines.append("[{}] 流量 {}".format(u.get("username", ""), _fmt_bytes(total)))
                except Exception:
                    continue
        else:
            lines.append("无用户数据")

    lines.append("")
    lines.append("--- 全局状态 ---")
    lines.append("服务启动时长: {}".format(data.get("global_uptime", "")))
    lines.append("去广告API调用: {}".format(data.get("global_dmdaili_api_calls", "")))
    lines.append("当前代理IP: {}".format(data.get("cached_proxy_ip", "")))
    lines.append("缓存剩余时长: {}".format(data.get("cache_expires_in", "")))
    lines.append("当前黑名单IP数: {}".format(data.get("current_blacklist_size", "")))
    lines.append("累计拉黑IP数: {}".format(data.get("global_blacklist_events", "")))

    await matcher.finish("\n".join([str(x) for x in lines if x is not None]))
