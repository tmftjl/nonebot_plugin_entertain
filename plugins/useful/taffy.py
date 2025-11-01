from __future__ import annotations
from ...core.constants import DEFAULT_HTTP_TIMEOUT


from typing import Any, Dict, Optional

import httpx
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import RegexGroup
from ...core.api import Plugin
from .config import cfg_taffy




def _load_cfg() -> Dict[str, Any]:
    return cfg_taffy()

# 瑙﹀彂涓€娆＄紦瀛樿鍙栵紝淇濊瘉妯″潡鍔犺浇鏃堕粯璁ら厤缃凡灏变綅
_ = _load_cfg()


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


P = Plugin(name="useful", display_name="鏈夌敤鐨?)
taffy_cmd = P.on_regex(r"^#?鏌ヨ娴侀噺\s*(.*)$", name="query",display_name="鏌ヨ娴侀噺", block=True, priority=5)


@taffy_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent, groups: tuple = RegexGroup()):
    cfg = _load_cfg()
    api_url = str(cfg.get("api_url") or "").strip()
    if not api_url:
        await matcher.finish("鏈厤缃?Taffy API 鍦板潃锛岃鍦?config/useful/config.json 鍐欏叆 api_url")

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
        headers["Authorization"] = "Basic {}".format(auth)`n
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        await matcher.finish("璇锋眰API澶辫触: {}".format(e))
        return
    except Exception:
        await matcher.finish("鏌ヨ澶辫触锛氭棤娉曡繛鎺ュ埌鏈嶅姟鍣ㄦ垨鏁版嵁鏍煎紡寮傚父")
        return

    lines = ["--- 浠ｇ悊鏈嶅姟鐘舵€?---"]
    if query_user:
        found = bool(data.get("found"))
        user = data.get("single_user") or {}
        if found and isinstance(user, dict):
            up = user.get("upstream_bytes")
            down = user.get("downstream_bytes")
            total = (up or 0) + (down or 0)
            lines.append("[鐢ㄦ埛鍚? {}]".format(user.get("username", "")))
            lines.append("宸茶姹傛鏁? {}".format(user.get("total_requests", 0)))
            lines.append("涓婅娴侀噺: {}".format(_fmt_bytes(up)))
            lines.append("涓嬭娴侀噺: {}".format(_fmt_bytes(down)))
            lines.append("绱娴侀噺: {}".format(_fmt_bytes(total)))
        else:
            lines.append("鏈壘鍒扮敤鎴穂{}] 鐨勭粺璁′俊鎭?.format(query_user))
    else:
        lines.append("[鎵€鏈夌敤鎴穄")
        users = data.get("all_users") or []
        if isinstance(users, list) and users:
            for u in users:
                try:
                    up = u.get("upstream_bytes")
                    down = u.get("downstream_bytes")
                    total = (up or 0) + (down or 0)
                    lines.append("[{}] 娴侀噺 {}".format(u.get("username", ""), _fmt_bytes(total)))
                except Exception:
                    continue
        else:
            lines.append("鏃犵敤鎴锋暟鎹?)

    lines.append("")
    lines.append("--- 鍏ㄥ眬鐘舵€?---")
    lines.append("鏈嶅姟鍚姩鏃堕暱: {}".format(data.get("global_uptime", "")))
    lines.append("鍘诲箍鍛夾PI璋冪敤: {}".format(data.get("global_dmdaili_api_calls", "")))
    lines.append("褰撳墠浠ｇ悊IP: {}".format(data.get("cached_proxy_ip", "")))
    lines.append("缂撳瓨鍓╀綑鏃堕暱: {}".format(data.get("cache_expires_in", "")))
    lines.append("褰撳墠榛戝悕鍗旾P鏁? {}".format(data.get("current_blacklist_size", "")))
    lines.append("绱鎷夐粦IP鏁? {}".format(data.get("global_blacklist_events", "")))

    await matcher.finish("\n".join([str(x) for x in lines if x is not None]))



