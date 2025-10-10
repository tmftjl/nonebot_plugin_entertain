from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from nonebot import get_app
from nonebot.log import logger

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import config
from .common import (
    _add_duration,
    _choose_bots,
    _now_utc,
    _read_data,
    _write_data,
    generate_unique_code,
    _ensure_generated_codes,
    UNITS,
)
from nonebot.adapters.onebot.v11 import Message


# UI strings
CONTACT_SUFFIX = getattr(config, "member_renewal_contact_suffix", " 咨询/加入交流群 757463664 联系群管")


# In-memory rate-limit bucket {(ip, window): count}
_RL_BUCKET: Dict[tuple[str, int], int] = {}


def _rate_limited(ip: str) -> bool:
    try:
        limit = getattr(config, "member_renewal_rate_limit", {"window_sec": 15, "max": 120})
        w = int(limit.get("window_sec", 15))
        m = int(limit.get("max", 120))
    except Exception:
        w, m = 15, 120
    from time import time

    now = int(time())
    win = now // max(1, w)
    key = (ip or "", win)
    cnt = _RL_BUCKET.get(key, 0) + 1
    _RL_BUCKET[key] = cnt
    # best-effort cleanup
    for k in list(_RL_BUCKET.keys()):
        if isinstance(k, tuple) and len(k) == 2 and k[1] != win:
            _RL_BUCKET.pop(k, None)
    return cnt > max(1, m)


def _audit(action: str, request: Request, token_tail: str, role: str, ok: bool, params: dict | None = None, error: str | None = None) -> None:
    try:
        from ...utils import config_dir as _cfgd

        path = _cfgd("member_renewal") / "audit.log"
        data = {
            "time": _now_utc().isoformat(),
            "ip": request.client.host if request and request.client else "",
            "token_tail": token_tail,
            "role": role,
            "action": action,
            "ok": ok,
            "params": {k: v for k, v in (params or {}).items() if k not in {"token", "Authorization"}},
            "error": error or "",
        }
        text = json.dumps(data, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass


def setup_web_console() -> None:
    """Mount optional FastAPI console and APIs if enabled in config."""
    try:
        if not getattr(config, "member_renewal_console_enable", False):
            return

        app = get_app()
        router = APIRouter(prefix="/member_renewal", tags=["member_renewal"])

        # 简易鉴权：Header Bearer 或 query.token；支持多 Token 角色
        def _auth(request: Request) -> dict:
            token = ""
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
            if not token:
                token = request.query_params.get("token", "") or ""
            ip = request.client.host if request and request.client else ""

            # IP allowlist check (if configured)
            allow = getattr(config, "member_renewal_console_ip_allowlist", []) or []
            if allow and ip and ip not in set(allow):
                raise HTTPException(status_code=403, detail="IP 不在允许列表内")

            # rl
            if _rate_limited(ip or ""):
                raise HTTPException(status_code=429, detail="请求过于频繁")

            # accept legacy single token
            if getattr(config, "member_renewal_console_token", "") and token == config.member_renewal_console_token:
                return {"role": "admin", "token_tail": token[-4:], "ip": ip}

            # multi token
            for t in getattr(config, "member_renewal_console_tokens", []) or []:
                if not isinstance(t, dict) or t.get("disabled"):
                    continue
                if token and t.get("token") == token:
                    return {"role": str(t.get("role") or "viewer"), "token_tail": token[-4:], "ip": ip}
            raise HTTPException(status_code=401, detail="未授权或令牌无效")

        # 数据：读取完整 memberships
        @router.get("/data")
        async def get_all(ctx: dict = Depends(_auth)):
            _audit("data", ctx.get("request") if False else None, ctx.get("token_tail", ""), ctx.get("role", ""), True, {})  # noqa
            return _read_data()

        # 生成续费码
        @router.post("/generate")
        async def api_generate(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                length = int(payload.get("length"))
                unit = str(payload.get("unit"))
                if unit not in UNITS:
                    raise ValueError("单位无效")
            except Exception as e:
                raise HTTPException(400, f"参数无效: {e}")
            data = _ensure_generated_codes(_read_data())
            code = generate_unique_code(length, unit)
            rec = {
                "length": length,
                "unit": unit,
                "generated_time": _now_utc().isoformat(),
            }
            # optional: expiry & max_use
            try:
                max_use = int(payload.get("max_use", 0) or 0)
            except Exception:
                max_use = 0
            if max_use <= 0:
                max_use = int(getattr(config, "member_renewal_code_max_use", 1) or 1)
            rec["max_use"] = max_use
            rec["used_count"] = 0
            try:
                expire_days = int(payload.get("expire_days", 0) or 0)
            except Exception:
                expire_days = 0
            if expire_days <= 0:
                expire_days = int(getattr(config, "member_renewal_code_expire_days", 0) or 0)
            if expire_days > 0:
                rec["expire_at"] = _add_duration(_now_utc(), expire_days, "天").isoformat()
            data["generatedCodes"][code] = rec
            _write_data(data)
            _audit("generate", request, ctx.get("token_tail", ""), ctx.get("role", ""), True, {"length": length, "unit": unit})
            return {"code": code}

        # 延长到期时间（基于当前或 now）
        @router.post("/extend")
        async def api_extend(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = str(payload.get("group_id"))
                length = int(payload.get("length"))
                unit = str(payload.get("unit"))
                if unit not in UNITS:
                    raise ValueError("单位无效")
            except Exception as e:
                raise HTTPException(400, f"参数无效: {e}")
            now = _now_utc()
            data = _read_data()
            current = now
            cur = (data.get(gid) or {}).get("expiry")
            if cur:
                try:
                    current = datetime.fromisoformat(cur)
                    if current.tzinfo is None:
                        current = current.replace(tzinfo=timezone.utc)
                except Exception:
                    current = now
            if current < now:
                current = now
            new_expiry = _add_duration(current, length, unit)
            rec = data.get(gid) or {}
            rec.update(
                {
                    "group_id": gid,
                    "expiry": new_expiry.isoformat(),
                    "status": "active",
                }
            )
            data[gid] = rec
            _write_data(data)
            _audit("extend", request, ctx.get("token_tail", ""), ctx.get("role", ""), True, {"group_id": gid, "length": length, "unit": unit})
            return {"group_id": gid, "expiry": new_expiry.isoformat()}

        # 设置到期时间（覆盖）
        @router.post("/set_expiry")
        async def api_set_expiry(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = str(payload.get("group_id"))
                expiry = datetime.fromisoformat(str(payload.get("expiry")))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
            except Exception as e:
                raise HTTPException(400, f"参数无效: {e}")
            data = _read_data()
            rec = data.get(gid) or {}
            rec.update({"group_id": gid, "expiry": expiry.isoformat()})
            data[gid] = rec
            _write_data(data)
            _audit("set_expiry", request, ctx.get("token_tail", ""), ctx.get("role", ""), True, {"group_id": gid, "expiry": expiry.isoformat()})
            return {"group_id": gid, "expiry": expiry.isoformat()}

        # 指定群退群
        @router.post("/leave")
        async def api_leave(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"无效的 group_id: {e}")
            preferred = str(payload.get("bot_id") or "")
            ok = False
            for bot in _choose_bots(preferred or None):
                try:
                    await bot.set_group_leave(group_id=gid, is_dismiss=False)
                    ok = True
                    break
                except Exception as e:
                    logger.debug(f"leave group failed via bot: {e}")
                    continue
            if not ok:
                raise HTTPException(500, "切换所有 Bot 退出群失败")
            # 移除记录（忽略失败）
            try:
                data = _read_data()
                data.pop(str(gid), None)
                _write_data(data)
            except Exception as e:
                logger.debug(f"web console leave: remove record failed: {e}")
            _audit("leave", request, ctx.get("token_tail", ""), ctx.get("role", ""), True, {"group_id": gid})
            return {"status": "ok"}

        # 群内提醒
        @router.post("/remind")
        async def api_remind(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"无效的 group_id: {e}")
            content = str(payload.get("content") or "本群会员即将到期，请尽快续费")
            if CONTACT_SUFFIX and CONTACT_SUFFIX.strip() and CONTACT_SUFFIX.strip() not in content:
                content = content + CONTACT_SUFFIX
            preferred = str(payload.get("bot_id") or "")
            ok = False
            for bot in _choose_bots(preferred or None):
                try:
                    await bot.send_group_msg(group_id=gid, message=Message(content))
                    ok = True
                    break
                except Exception as e:
                    logger.debug(f"send reminder failed via bot: {e}")
                    continue
            if not ok:
                raise HTTPException(500, "切换所有 Bot 发送失败")
            _audit("remind", request, ctx.get("token_tail", ""), ctx.get("role", ""), True, {"group_id": gid})
            return {"status": "ok"}

        # 列出生成的续费码
        @router.get("/codes")
        async def api_codes(_: dict = Depends(_auth)):
            data = _ensure_generated_codes(_read_data())
            return data.get("generatedCodes", {})

        # 撤销续费码
        @router.post("/codes/revoke")
        async def api_codes_revoke(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            code = str(payload.get("code") or "")
            if not code:
                raise HTTPException(400, "缺少 code")
            data = _ensure_generated_codes(_read_data())
            if code in data["generatedCodes"]:
                data["generatedCodes"].pop(code, None)
                _write_data(data)
            _audit("revoke_code", request, ctx.get("token_tail", ""), ctx.get("role", ""), True, {"code_tail": code[-6:]})
            return {"status": "ok"}

        # 批量接口：延期/提醒/退群
        @router.post("/batch/extend")
        async def api_batch_extend(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            gids = payload.get("group_ids") or []
            length = int(payload.get("length") or 0)
            unit = str(payload.get("unit") or "天")
            if unit not in UNITS:
                raise HTTPException(400, "单位无效")
            ok = []
            for gid in [str(g) for g in gids if g]:
                try:
                    await api_extend({"group_id": gid, "length": length, "unit": unit}, request, ctx)
                    ok.append(gid)
                except Exception:
                    continue
            return {"count": len(ok), "ok": ok}

        # 立即执行一次定时任务
        @router.post("/job/run")
        async def api_run_job(_: dict = Depends(_auth)):
            try:
                from .commands import _check_and_process  # type: ignore

                r, l = await _check_and_process()
                return {"reminded": r, "left": l}
            except Exception as e:
                raise HTTPException(500, f"执行失败: {e}")

        @router.post("/batch/remind")
        async def api_batch_remind(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            gids = payload.get("group_ids") or []
            ok = []
            for gid in [str(g) for g in gids if g]:
                try:
                    await api_remind({"group_id": int(gid)}, request, ctx)
                    ok.append(gid)
                except Exception:
                    continue
            return {"count": len(ok), "ok": ok}

        @router.post("/batch/leave")
        async def api_batch_leave(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            gids = payload.get("group_ids") or []
            ok = []
            for gid in [str(g) for g in gids if g]:
                try:
                    await api_leave({"group_id": int(gid)}, request, ctx)
                    ok.append(gid)
                except Exception:
                    continue
            return {"count": len(ok), "ok": ok}

        # 静态资源：控制台前端
        static_dir = Path(__file__).parent / "web"
        app.mount(
            "/member_renewal/static",
            StaticFiles(directory=str(static_dir)),
            name="member_renewal_static",
        )

        # 控制台页面（HTML）
        @router.get("/console")
        async def console(_: dict = Depends(_auth)):
            path = Path(__file__).parent / "web" / "console.html"
            return FileResponse(path, media_type="text/html")

        app.include_router(router)
        logger.info("member_renewal Web 控制台已挂载 /member_renewal")
    except Exception as e:
        logger.warning(f"member_renewal 控制台已禁用或不可用: {e}")
