from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import RegexGroup

from ...registry import Plugin
from ...config import register_plugin_config


DEFAULT_CFG: Dict[str, Any] = {
    "api_url": "http://127.0.0.1:8899/stats/api",
    "username": "",
    "password": "",
    "timeout": 20,
}

def _validate_cfg(cfg: Dict[str, Any]) -> None:
    if "api_url" in cfg and not isinstance(cfg["api_url"], str):
        raise ValueError("api_url must be str")
    for k in ("username", "password"):
        if k in cfg and not isinstance(cfg[k], str):
            raise ValueError(f"{k} must be str")
    if "timeout" in cfg:
        try:
            t = int(cfg["timeout"])  # accept int-like
            if t <= 0:
                raise ValueError
        except Exception:
            raise ValueError("timeout must be positive int")

REG = register_plugin_config("taffy", DEFAULT_CFG, validator=_validate_cfg)


def _load_cfg() -> Dict[str, Any]:
    return REG.load()


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


P = Plugin()
taffy_cmd = P.on_regex(r"^#?查询流量\s*(.*)$", name="query", block=True, priority=100)


@taffy_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent, groups: tuple = RegexGroup()):
    cfg = _load_cfg()
    api_url = str(cfg.get("api_url") or "").strip()
    if not api_url:
        await matcher.finish("未配置 Taffy API 地址，请在 config/taffy/config.json 中设置 api_url")

    # query user if provided
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
        await matcher.finish("请求API失败：{}".format(e))
        return
    except Exception:
        await matcher.finish("查询失败，无法连接到服务或解析数据出错")
        return

    lines = ["--- 塔菲服务状态 ---"]
    if query_user:
        found = bool(data.get("found"))
        user = data.get("single_user") or {}
        if found and isinstance(user, dict):
            up = user.get("upstream_bytes")
            down = user.get("downstream_bytes")
            total = (up or 0) + (down or 0)
            lines.append("[用户详情: {}]".format(user.get("username", "")))
            lines.append("已处理请求数: {}".format(user.get("total_requests", 0)))
            lines.append("上行流量: {}".format(_fmt_bytes(up)))
            lines.append("下行流量: {}".format(_fmt_bytes(down)))
            lines.append("总计费流量: {}".format(_fmt_bytes(total)))
        else:
            lines.append("未找到用户[{}] 的统计信息".format(query_user))
    else:
        lines.append("[所有用户总览]")
        users = data.get("all_users") or []
        if isinstance(users, list) and users:
            for u in users:
                try:
                    up = u.get("upstream_bytes")
                    down = u.get("downstream_bytes")
                    total = (up or 0) + (down or 0)
                    lines.append("[{}] 总流量 {}".format(u.get("username", ""), _fmt_bytes(total)))
                except Exception:
                    continue
        else:
            lines.append("暂无用户数据")

    lines.append("")
    lines.append("--- 全局状态 ---")
    lines.append("服务运行时间: {}".format(data.get("global_uptime", "")))
    lines.append("请求上游API次数: {}".format(data.get("global_dmdaili_api_calls", "")))
    lines.append("当前缓存IP: {}".format(data.get("cached_proxy_ip", "")))
    lines.append("缓存过期时间: {}".format(data.get("cache_expires_in", "")))
    lines.append("当前黑名单IP数: {}".format(data.get("current_blacklist_size", "")))
    lines.append("累计拉黑IP次数: {}".format(data.get("global_blacklist_events", "")))

    await matcher.finish("\n".join([str(x) for x in lines if x is not None]))


