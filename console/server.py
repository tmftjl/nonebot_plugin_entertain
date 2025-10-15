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

from ..core.system_config import load_cfg, save_cfg
from .membership_service import (
    _add_duration,
    _now_utc,
    _read_data,
    _write_data,
    generate_unique_code,
    _ensure_generated_codes,
    UNITS,
)


def _auth(request: Request) -> dict:
    """极简认证（仅示例）。"""
    ip = request.client.host if request and request.client else ""
    return {"role": "admin", "token_tail": "", "ip": ip, "request": request}


def _contact_suffix() -> str:
    cfg = load_cfg()
    return str(cfg.get("member_renewal_contact_suffix", " 咨询/加入交流QQ群：757463664 联系群管") or "")


def setup_web_console() -> None:
    """挂载 Web 控制台与接口（中文注释，UTF-8）。"""
    try:
        if not bool(load_cfg().get("member_renewal_console_enable", False)):
            return

        app = get_app()
        router = APIRouter(prefix="/membership", tags=["core"])

        # 提醒群聊
        @router.post("/remind_multi")
        async def api_remind_multi(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"参数错误: {e}")
            content = str(payload.get("content") or "本群会员即将到期，请尽快续费")
            suf = _contact_suffix().strip()
            if suf and suf not in content:
                content = content + suf
            live = get_bots()
            bot = next(iter(live.values()), None)
            if not bot:
                raise HTTPException(500, "没有可用的 Bot 可发送提醒")
            try:
                await bot.send_group_msg(group_id=gid, message=Message(content))
            except Exception as e:
                logger.debug(f"remind_multi send failed: {e}")
                raise HTTPException(500, f"发送提醒失败: {e}")
            return {"sent": 1}

        # 退群
        @router.post("/leave_multi")
        async def api_leave_multi(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"参数错误: {e}")
            live = get_bots()
            bot = next(iter(live.values()), None)
            if not bot:
                raise HTTPException(500, "没有可用的 Bot 可退群")
            try:
                await bot.set_group_leave(group_id=gid, is_dismiss=False)
            except Exception as e:
                logger.debug(f"leave_multi failed: {e}")
                raise HTTPException(500, f"退出失败: {e}")
            # 删除记录（可选）
            try:
                data = _read_data()
                data.pop(str(gid), None)
                _write_data(data)
            except Exception as e:
                logger.debug(f"web console leave_multi: remove record failed: {e}")
            return {"left": 1}

        # 统计：转发到统计服务 API
        @router.get("/stats/today")
        async def api_stats_today():
            stats_api_url = str(load_cfg().get("member_renewal_stats_api_url", "http://127.0.0.1:8000") or "http://127.0.0.1:8000").rstrip("/")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{stats_api_url}/stats/today", timeout=10.0)
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                logger.error(f"获取统计失败: {e}")
                raise HTTPException(500, f"获取统计失败: {e}")

        # 权限读取
        @router.get("/permissions")
        async def api_get_permissions():
            from ..framework.config import load_permissions
            return load_permissions()

        # 权限更新
        @router.put("/permissions")
        async def api_update_permissions(payload: Dict[str, Any]):
            from ..framework.config import save_permissions
            try:
                save_permissions(payload)
                return {"success": True, "message": "权限配置已更新（需手动重载生效）"}
            except Exception as e:
                raise HTTPException(500, f"更新权限失败: {e}")

        # 优化权限文件（排序、规范化）
        @router.post("/permissions/optimize")
        async def api_optimize_permissions():
            from ..framework.config import optimize_permissions
            try:
                changed, new_data = optimize_permissions()
                return {"success": True, "changed": bool(changed), "data": new_data}
            except Exception as e:
                raise HTTPException(500, f"优化失败: {e}")

        # 配置读取
        @router.get("/config")
        async def api_get_config():
            return load_cfg()

        # 配置更新
        @router.put("/config")
        async def api_update_config(payload: Dict[str, Any]):
            try:
                save_cfg(payload)
                return {"success": True, "message": "配置已更新"}
            except Exception as e:
                raise HTTPException(500, f"更新配置失败: {e}")

        # 数据读取
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
            cfg = load_cfg()
            max_use = int(payload.get("max_use") or cfg.get("member_renewal_code_max_use", 1) or 1)
            rec["max_use"] = max_use
            rec["used_count"] = 0
            expire_days = int(payload.get("expire_days") or cfg.get("member_renewal_code_expire_days", 0) or 0)
            if expire_days > 0:
                rec["expire_at"] = _add_duration(_now_utc(), expire_days, UNITS[0]).isoformat()
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

        # 运行定时任务（调用内部检查逻辑）
        @router.post("/job/run")
        async def api_run_job(_: dict = Depends(_auth)):
            try:
                from ..core.commands.membership.membership import _check_and_process  # type: ignore
                r, l = await _check_and_process()
                return {"reminded": r, "left": l}
            except Exception as e:
                raise HTTPException(500, f"执行失败: {e}")

        # 静态资源与控制台页面（使用 console/web 目录）
        static_dir = Path(__file__).parent / "web"
        if not static_dir.exists():
            static_dir = Path(__file__).resolve().parents[2] / "console" / "web"
        app.mount("/membership/static", StaticFiles(directory=str(static_dir)), name="core_static")

        @router.get("/console")
        async def console(_: dict = Depends(_auth)):
            path = static_dir / "console.html"
            return FileResponse(path, media_type="text/html")

        app.include_router(router)
        logger.info("core Web 控制台已挂载 /membership")
    except Exception as e:
        logger.warning(f"membership Web 控制台挂载失败: {e}")
