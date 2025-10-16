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
    ip = request.client.host if request and request.client else ""
    return {"role": "admin", "token_tail": "", "ip": ip, "request": request}


def _contact_suffix() -> str:
    cfg = load_cfg()
    return str(cfg.get("member_renewal_contact_suffix", " 咨询/加入交流QQ群 757463664 联系群管") or "")


def setup_web_console() -> None:
    try:
        if not bool(load_cfg().get("member_renewal_console_enable", False)):
            return

        app = get_app()
        router = APIRouter(prefix="/member_renewal", tags=["member_renewal"])

        # 内部：根据系统配置重置/移除会员检查定时任务
        async def _membership_job():
            try:
                from ..commands.membership.membership import _check_and_process  # type: ignore

                r, l = await _check_and_process()
                logger.info(f"[membership] 定时检查完成，提醒={r}，退出={l}")
            except Exception as e:
                logger.exception(f"[membership] 定时检查失败: {e}")

        def _reschedule_membership_job() -> None:
            try:
                # 可选依赖：未安装则跳过
                from nonebot_plugin_apscheduler import scheduler  # type: ignore

                cfg = load_cfg()
                enable = bool(cfg.get("member_renewal_enable_scheduler", True))
                if not enable:
                    try:
                        scheduler.remove_job("membership_check")  # type: ignore
                    except Exception:
                        pass
                    return

                hour = int(cfg.get("member_renewal_schedule_hour", 12) or 12)
                minute = int(cfg.get("member_renewal_schedule_minute", 0) or 0)
                second = int(cfg.get("member_renewal_schedule_second", 0) or 0)
                # 使用与插件相同的任务 ID，避免重复；存在则替换
                scheduler.add_job(  # type: ignore
                    _membership_job,
                    trigger="cron",
                    hour=hour,
                    minute=minute,
                    second=second,
                    id="membership_check",
                    replace_existing=True,
                )
                logger.info(
                    f"[membership] 定时任务已重载为 {hour:02d}:{minute:02d}:{second:02d}"
                )
            except Exception:
                # 未安装调度器或运行环境不支持时静默跳过
                pass

        # 提醒群（不再需要 bot_ids）
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
                raise HTTPException(500, "无可用 Bot 可发送提醒")
            try:
                await bot.send_group_msg(group_id=gid, message=Message(content))
            except Exception as e:
                logger.debug(f"remind_multi send failed: {e}")
                raise HTTPException(500, f"发送提醒失败: {e}")
            return {"sent": 1}

        # 退群（不再需要 bot_ids）
        @router.post("/leave_multi")
        async def api_leave_multi(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"参数错误: {e}")
            live = get_bots()
            bot = next(iter(live.values()), None)
            if not bot:
                raise HTTPException(500, "无可用 Bot 可退群")
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
        # 权限
        @router.get("/permissions")
        async def api_get_permissions():
            from ..core.framework.config import load_permissions
            return load_permissions()

        @router.put("/permissions")
        async def api_update_permissions(payload: Dict[str, Any]):
            from ..core.framework.config import save_permissions, optimize_permissions
            from ..core.framework.perm import reload_permissions
            try:
                save_permissions(payload)
                # 规范化并立即重载到内存
                try:
                    optimize_permissions()
                except Exception:
                    pass
                try:
                    reload_permissions()
                except Exception:
                    pass
                return {"success": True, "message": "权限配置已更新并生效"}
            except Exception as e:
                raise HTTPException(500, f"更新权限失败: {e}")

        # 配置 - 获取所有插件配置
        @router.get("/config")
        async def api_get_config():
            """获取所有插件的配置（从内存缓存中）"""
            from ..core.framework.config import get_all_plugin_configs
            return get_all_plugin_configs()

        @router.put("/config")
        async def api_update_config(payload: Dict[str, Any]):
            """更新配置 - 支持单个插件或批量更新"""
            try:
                # 检查payload是否包含多个插件配置
                if "system" in payload or len(payload) > 1:
                    # 批量更新模式
                    from ..core.framework.config import save_all_plugin_configs
                    success, errors = save_all_plugin_configs(payload)
                    if not success:
                        raise HTTPException(500, f"部分配置更新失败: {errors}")
                    # 重载定时任务（若更新了system配置）
                    if "system" in payload:
                        _reschedule_membership_job()
                    return {"success": True, "message": "配置已更新并应用"}
                else:
                    # 向后兼容：单个system配置更新
                    save_cfg(payload)
                    _reschedule_membership_job()
                    return {"success": True, "message": "配置已更新并应用"}
            except Exception as e:
                raise HTTPException(500, f"更新配置失败: {e}")

        # 插件显示名（中文）
        @router.get("/plugins")
        async def api_get_plugins():
            try:
                from ..core.api import get_plugin_display_names
                return get_plugin_display_names()
            except Exception as e:
                raise HTTPException(500, f"获取插件信息失败: {e}")

        # 配置 Schema - 前端渲染所需元信息（中文名/描述/类型/分组等）
        @router.get("/config_schema")
        async def api_get_config_schema():
            try:
                from ..core.framework.config import get_all_plugin_schemas
                return get_all_plugin_schemas()
            except Exception as e:
                raise HTTPException(500, f"获取配置Schema失败: {e}")

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
            cfg = load_cfg()
            max_use = int(payload.get("max_use") or cfg.get("member_renewal_code_max_use", 1) or 1)
            rec["max_use"] = max_use
            rec["used_count"] = 0
            expire_days = int(payload.get("expire_days") or cfg.get("member_renewal_code_expire_days", 0) or 0)
            if expire_days > 0:
                # 使用 UNITS[0] 对应的单位（通常为“天”）
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

        # 运行定时任务
        @router.post("/job/run")
        async def api_run_job(_: dict = Depends(_auth)):
            try:
                from ..commands.membership.membership import _check_and_process  # type: ignore
                r, l = await _check_and_process()
                return {"reminded": r, "left": l}
            except Exception as e:
                raise HTTPException(500, f"执行失败: {e}")

        # 静态资源与控制台页面
        static_dir = Path(__file__).parent / "web"
        app.mount("/member_renewal/static", StaticFiles(directory=str(static_dir)), name="member_renewal_static")

        @router.get("/console")
        async def console(_: dict = Depends(_auth)):
            path = Path(__file__).parent / "web" / "console.html"
            return FileResponse(path, media_type="text/html")

        app.include_router(router)
        logger.info("member_renewal Web 控制台已挂载 /member_renewal")
    except Exception as e:
        logger.warning(f"member_renewal Web 控制台挂载失败: {e}")
