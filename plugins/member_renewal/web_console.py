from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from nonebot import get_app, get_bots
from nonebot.adapters.onebot.v11 import Message
from nonebot.log import logger

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


CONTACT_SUFFIX = getattr(config, "member_renewal_contact_suffix", " 咨询/加入交流群 757463664 联系群管")


def _auth(request: Request) -> dict:
    ip = request.client.host if request and request.client else ""
    return {"role": "admin", "token_tail": "", "ip": ip, "request": request}


def setup_web_console() -> None:
    try:
        if not getattr(config, "member_renewal_console_enable", False):
            return

        app = get_app()
        router = APIRouter(prefix="/member_renewal", tags=["member_renewal"])

        # Bots 配置列表
        @router.get("/bots/config")
        async def api_get_bots_from_config():
            cfg_bots = getattr(config, "member_renewal_bots", []) or []
            live_map = get_bots()
            online_ids = {str(k) for k in live_map.keys()}
            out = []
            for b in cfg_bots:
                try:
                    if not isinstance(b, dict):
                        continue
                    bid = str(b.get("bot_id") or "").strip()
                    if not bid:
                        continue
                    out.append(
                        {
                            "bot_id": bid,
                            "bot_name": str(b.get("bot_name") or f"Bot {bid}"),
                            "is_online": bid in online_ids,
                            "self_id": bid,
                        }
                    )
                except Exception:
                    continue
            if not out and live_map:
                for bot_id in live_map.keys():
                    bid = str(bot_id)
                    out.append({"bot_id": bid, "bot_name": f"Bot {bid}", "is_online": True, "self_id": bid})
            return {"bots": out}

        # 指定多个机器人提醒群
        @router.post("/remind_multi")
        async def api_remind_multi(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
                bot_ids = payload.get("bot_ids") or []
                if not isinstance(bot_ids, list) or not bot_ids:
                    raise ValueError("bot_ids 不能为空")
            except Exception as e:
                raise HTTPException(400, f"参数错误: {e}")
            content = str(payload.get("content") or "本群会员即将到期，请尽快续费")
            if CONTACT_SUFFIX and CONTACT_SUFFIX.strip() and CONTACT_SUFFIX.strip() not in content:
                content = content + CONTACT_SUFFIX
            live = get_bots()
            sent = 0
            for bid in [str(x) for x in bot_ids if x is not None]:
                b = live.get(bid)
                if not b:
                    continue
                try:
                    await b.send_group_msg(group_id=gid, message=Message(content))
                    sent += 1
                except Exception as e:
                    logger.debug(f"remind_multi failed via bot {bid}: {e}")
            if sent <= 0:
                raise HTTPException(500, "所选 Bot 均未能发送提醒")
            return {"sent": sent}

        # 指定多个机器人退群
        @router.post("/leave_multi")
        async def api_leave_multi(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
                bot_ids = payload.get("bot_ids") or []
                if not isinstance(bot_ids, list) or not bot_ids:
                    raise ValueError("bot_ids 不能为空")
            except Exception as e:
                raise HTTPException(400, f"参数错误: {e}")
            live = get_bots()
            done = 0
            for bid in [str(x) for x in bot_ids if x is not None]:
                b = live.get(bid)
                if not b:
                    continue
                try:
                    await b.set_group_leave(group_id=gid, is_dismiss=False)
                    done += 1
                except Exception as e:
                    logger.debug(f"leave_multi failed via bot {bid}: {e}")
            if done <= 0:
                raise HTTPException(500, "所选 Bot 均未能退出该群")
            # 删除记录（可选）
            try:
                data = _read_data()
                data.pop(str(gid), None)
                _write_data(data)
            except Exception as e:
                logger.debug(f"web console leave_multi: remove record failed: {e}")
            return {"left": done}

        # 今日统计（外部 napcat-stats-api）
        @router.get("/stats/today")
        async def api_stats_today():
            stats_api_url = getattr(config, "member_renewal_stats_api_url", "http://127.0.0.1:8000")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{stats_api_url}/stats/today", timeout=10.0)
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                logger.error(f"获取统计失败: {e}")
                raise HTTPException(500, f"获取统计失败: {e}")

        # 权限
        @router.get("/permissions")
        async def api_get_permissions():
            from ...config import load_permissions
            return load_permissions()

        @router.put("/permissions")
        async def api_update_permissions(payload: Dict[str, Any]):
            from ...config import save_permissions
            try:
                save_permissions(payload)
                return {"success": True, "message": "权限配置已更新"}
            except Exception as e:
                raise HTTPException(500, f"更新权限失败: {e}")

        # 配置
        @router.get("/config")
        async def api_get_config():
            return config.to_dict()

        @router.put("/config")
        async def api_update_config(payload: Dict[str, Any]):
            try:
                config.save(payload)
                config.reload()
                return {"success": True, "message": "配置已更新"}
            except Exception as e:
                raise HTTPException(500, f"更新配置失败: {e}")

        # 数据
        @router.get("/data")
        async def api_get_all(_: dict = Depends(_auth)):
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
            max_use = int(payload.get("max_use") or getattr(config, "member_renewal_code_max_use", 1) or 1)
            rec["max_use"] = max_use
            rec["used_count"] = 0
            expire_days = int(payload.get("expire_days") or getattr(config, "member_renewal_code_expire_days", 0) or 0)
            if expire_days > 0:
                rec["expire_at"] = _add_duration(_now_utc(), expire_days, "天").isoformat()
            data["generatedCodes"][code] = rec
            _write_data(data)
            return {"code": code}

        # 延长到期
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
            rec.update({"group_id": gid, "expiry": new_expiry.isoformat(), "status": "active"})
            data[gid] = rec
            _write_data(data)
            return {"group_id": gid, "expiry": new_expiry.isoformat()}

        # 列出生成的续费码
        @router.get("/codes")
        async def api_codes(_: dict = Depends(_auth)):
            data = _ensure_generated_codes(_read_data())
            return data.get("generatedCodes", {})

        # 运行定时任务
        @router.post("/job/run")
        async def api_run_job(_: dict = Depends(_auth)):
            try:
                from .commands import _check_and_process  # type: ignore

                r, l = await _check_and_process()
                return {"reminded": r, "left": l}
            except Exception as e:
                raise HTTPException(500, f"执行失败: {e}")

        # 静态资源
        static_dir = Path(__file__).parent / "web"
        app.mount("/member_renewal/static", StaticFiles(directory=str(static_dir)), name="member_renewal_static")

        # 控制台页面
        @router.get("/console")
        async def console(_: dict = Depends(_auth)):
            path = Path(__file__).parent / "web" / "console.html"
            return FileResponse(path, media_type="text/html")

        app.include_router(router)
        logger.info("member_renewal Web 控制台已挂载于 /member_renewal")
    except Exception as e:
        logger.warning(f"member_renewal Web 控制台挂载失败: {e}")

