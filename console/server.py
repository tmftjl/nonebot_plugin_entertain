from __future__ import annotations

from datetime import datetime, timezone
import asyncio
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from nonebot import get_app, get_bots
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.log import logger

from ..core.system_config import load_cfg, save_cfg
from .membership_service import (
    _add_duration,
    _now_utc,
    _read_data,
    _write_data,
    _days_remaining,
    _format_cn,
    generate_unique_code,
    _ensure_generated_codes,
    UNITS,
)


def _extract_token(request: Request) -> str:
    """从请求中提取访问令牌：query/header/cookie."""
    try:
        qp = request.query_params or {}
        token_q = qp.get("token") if hasattr(qp, "get") else None
    except Exception:
        token_q = None
    try:
        auth = request.headers.get("Authorization") if request and request.headers else None
        token_h = None
        if auth and isinstance(auth, str) and auth.lower().startswith("bearer "):
            token_h = auth.split(" ", 1)[1].strip()
    except Exception:
        token_h = None
    try:
        token_c = request.cookies.get("mr_token") if request and request.cookies else None
    except Exception:
        token_c = None
    return (token_q or token_h or token_c or "").strip()


def _validate_token(token: str, *, window_seconds: int = 600) -> bool:
    """校验令牌：匹配最近 window_seconds 秒内时间戳的后 6 位。

    与“今汐登录”命令的令牌生成逻辑保持一致（最后 6 位）。
    """
    try:
        token = str(token or "").strip()
        if not token:
            return False
        now = int(_now_utc().timestamp())
        start = max(0, now - max(0, int(window_seconds)))
        for t in range(start, now + 1):
            if str(t)[-6:] == token:
                return True
        return False
    except Exception:
        return False


def _auth(request: Request) -> dict:
    """简单鉴权：要求提供有效 token 才能访问控制台接口。"""
    ip = request.client.host if request and request.client else ""
    token = _extract_token(request)
    if not _validate_token(token):
        raise HTTPException(401, "未授权：缺少或无效的访问令牌")
    return {"role": "admin", "token_tail": token[-2:] if token else "", "ip": ip, "request": request}

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
            # 构造提醒内容：优先使用 payload.content，否则使用配置模板
            cfg = load_cfg()
            tmpl = str(
                cfg.get(
                    "member_renewal_remind_template",
                    "本群会员将在 {days} 天后到期（{expiry}），请尽快联系管理员续费",
                )
                or "本群会员将在 {days} 天后到期（{expiry}），请尽快联系管理员续费"
            )
            content_payload = str(payload.get("content") or "").strip()
            if content_payload:
                content = content_payload
            else:
                data = await _read_data()
                rec = data.get(str(gid)) or {}
                expiry_str = rec.get("expiry")
                days = 0
                expiry_cn = ""
                try:
                    if isinstance(expiry_str, str) and expiry_str:
                        dt = datetime.fromisoformat(expiry_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        days = _days_remaining(dt)
                        expiry_cn = _format_cn(dt)
                except Exception:
                    pass
                try:
                    content = tmpl.format(days=days, expiry=expiry_cn or "-")
                except Exception:
                    content = "本群会员即将到期，请尽快续费"
            # 按要求移除尾注，不再追加联系方式后缀
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

        # 自定义通知：支持文本与图片（base64:// 或 URL），批量群发
        @router.post("/notify")
        async def api_notify(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                raw_ids = payload.get("group_ids")
                if isinstance(raw_ids, (list, tuple)):
                    group_ids = [int(x) for x in raw_ids if str(x).strip()]
                else:
                    raise ValueError("group_ids 必须为数组")
            except Exception as e:
                raise HTTPException(400, f"参数无效: {e}")

            text = str(payload.get("text") or "")
            imgs = payload.get("images") or []
            if not group_ids:
                raise HTTPException(400, "未指定任何群组")

            def _norm_img(u: object) -> str:
                try:
                    s = str(u or "")
                except Exception:
                    return ""
                if not s:
                    return ""
                # 支持 data:image/*;base64,xxx
                if s.startswith("data:") and "," in s:
                    try:
                        b64 = s.split(",", 1)[1]
                        return "base64://" + b64
                    except Exception:
                        return s
                return s

            images: list[str] = []
            if isinstance(imgs, (list, tuple)):
                for it in imgs:
                    v = _norm_img(it)
                    if v:
                        images.append(v)

            # 取一个可用的 Bot
            live = get_bots()
            bot = next(iter(live.values()), None)
            if not bot:
                raise HTTPException(500, "无可用 Bot 可发送通知")

            sent = 0
            delay = 0.0
            try:
                delay = float(load_cfg().get("member_renewal_batch_delay_seconds", 0) or 0.0)
                if delay < 0:
                    delay = 0.0
            except Exception:
                delay = 0.0
            for gid in group_ids:
                segs = []
                if text:
                    segs.append(MessageSegment.text(text))
                for img in images:
                    try:
                        segs.append(MessageSegment.image(img))
                    except Exception:
                        continue
                if not segs:
                    continue
                try:
                    await bot.send_group_msg(group_id=int(gid), message=Message(segs))
                    sent += 1
                except Exception as e:
                    logger.debug(f"notify failed for {gid}: {e}")
                    continue
                # throttle between batch operations to avoid risk control
                if delay > 0:
                    try:
                        await asyncio.sleep(delay)
                    except Exception:
                        pass
            return {"sent": sent}

        # 退群（不再需要 bot_ids）
        @router.post("/leave_multi")
        async def api_leave_multi(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"参数错误: {e}")

            # 读取退群模式配置
            cfg = load_cfg()

            live = get_bots()
            bot = next(iter(live.values()), None)
            if not bot:
                raise HTTPException(500, "无可用 Bot 可退群")
            try:
                await bot.set_group_leave(group_id=gid)
            except Exception as e:
                logger.debug(f"leave_multi failed: {e}")
                raise HTTPException(500, f"退出失败: {e}")
            # 删除记录（可选）
            try:
                data = await _read_data()
                data.pop(str(gid), None)
                await _write_data(data)
            except Exception as e:
                logger.debug(f"web console leave_multi: remove record failed: {e}")
            return {"left": 1}

        # 统计：转发到统计服务 API
        @router.get("/stats/today")
        async def api_stats_today(_: dict = Depends(_auth)):
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
        async def api_get_permissions(_: dict = Depends(_auth)):
            from ..core.framework.config import load_permissions
            return load_permissions()

        @router.put("/permissions")
        async def api_update_permissions(payload: Dict[str, Any], _: dict = Depends(_auth)):
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
        async def api_get_config(_: dict = Depends(_auth)):
            """获取所有插件的配置（从内存缓存中）"""
            from ..core.framework.config import get_all_plugin_configs
            return get_all_plugin_configs()

        @router.put("/config")
        async def api_update_config(payload: Dict[str, Any], _: dict = Depends(_auth)):
            """更新配置 - 支持单个插件或批量更新，自动重载到内存缓存"""
            try:
                from ..core.framework.config import save_all_plugin_configs, reload_all_configs

                # 检查payload是否包含多个插件配置
                if "system" in payload or len(payload) > 1:
                    # 批量更新模式
                    success, errors = save_all_plugin_configs(payload)
                    if not success:
                        raise HTTPException(500, f"部分配置更新失败: {errors}")
                else:
                    # 向后兼容：单个system配置更新
                    save_cfg(payload)

                # 保存成功后，立即重载所有配置到内存缓存
                ok, details = reload_all_configs()
                if not ok:
                    logger.warning(f"配置重载部分失败: {details}")

                # 重载定时任务（若更新了system配置）
                if "system" in payload:
                    _reschedule_membership_job()

                return {"success": True, "message": "配置已更新并重载到内存"}
            except Exception as e:
                raise HTTPException(500, f"更新配置失败: {e}")

        # 插件显示名（中文）
        @router.get("/plugins")
        async def api_get_plugins(_: dict = Depends(_auth)):
            try:
                from ..core.api import get_plugin_display_names
                return get_plugin_display_names()
            except Exception as e:
                raise HTTPException(500, f"获取插件信息失败: {e}")

        # 命令显示名（中文）
        @router.get("/commands")
        async def api_get_commands(_: dict = Depends(_auth)):
            try:
                from ..core.api import get_command_display_names
                return get_command_display_names()
            except Exception as e:
                raise HTTPException(500, f"获取命令信息失败: {e}")

        # 配置 Schema - 前端渲染所需元信息（中文名/描述/类型/分组等）
        @router.get("/config_schema")
        async def api_get_config_schema(_: dict = Depends(_auth)):
            try:
                from ..core.framework.config import get_all_plugin_schemas
                return get_all_plugin_schemas()
            except Exception as e:
                raise HTTPException(500, f"获取配置Schema失败: {e}")

        # 数据
        @router.get("/data")
        async def api_get_all(_: dict = Depends(_auth)):
            return await _read_data()

        # Bot 列表（用于前端下拉选择管理Bot）
        @router.get("/bots")
        async def api_get_bots(_: dict = Depends(_auth)):
            try:
                bots_map = get_bots()
                # 返回 self_id 列表
                ids = list(bots_map.keys())
                return {"bots": ids}
            except Exception as e:
                logger.debug(f"/bots error: {e}")
                return {"bots": []}

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
            data = _ensure_generated_codes(await _read_data())
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
            await _write_data(data)
            return {"code": code}

        # 延长到期
        @router.post("/extend")
        async def api_extend(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            """Extend or set expiry for a group membership.

            Supports three modes:
            - Edit by id: payload contains `id`, optionally `group_id` to rename, and either `length+unit` or `expiry`.
            - Edit by group_id: payload contains existing `group_id` (no `id`), and either `length+unit` or `expiry`.
            - Create: payload contains new `group_id` and either `length+unit` or `expiry`.
            """

            now = _now_utc()
            data = await _read_data()

            # Parse optional fields
            gid_raw = payload.get("group_id")
            gid = str(gid_raw).strip() if gid_raw is not None else ""

            # length/unit optional (only validate when provided)
            length: int | None = None
            unit: str | None = None
            if payload.get("length") is not None:
                try:
                    length = int(payload.get("length"))
                except Exception:
                    raise HTTPException(400, "length 无效")
            if payload.get("unit") is not None:
                unit = str(payload.get("unit"))
                if unit not in UNITS:
                    raise HTTPException(400, "单位无效")

            # expiry optional
            expiry_dt = None
            expiry_raw = payload.get("expiry")
            if isinstance(expiry_raw, str) and expiry_raw.strip():
                try:
                    expiry_dt = datetime.fromisoformat(expiry_raw)
                    if expiry_dt.tzinfo is None:
                        expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    raise HTTPException(400, "expiry 无效")

            # Determine target record: by id, or by existing group_id, or create new
            rec: Dict[str, Any] | None = None
            target_gid: str | None = None

            rid_raw = payload.get("id")
            if rid_raw is not None and str(rid_raw).strip() != "":
                # Edit by id
                try:
                    rid = int(rid_raw)
                except Exception:
                    raise HTTPException(400, "id 无效")
                for k, v in data.items():
                    if k == "generatedCodes" or not isinstance(v, dict):
                        continue
                    try:
                        if int(v.get("id") or -1) == rid:
                            target_gid = str(k)
                            rec = dict(v)
                            break
                    except Exception:
                        continue
                if not target_gid:
                    raise HTTPException(404, "未找到对应记录")

                # Allow renaming group_id when provided and unused
                if gid and gid != target_gid:
                    if isinstance(data.get(gid), dict):
                        raise HTTPException(400, "目标群已存在记录")
                    # Move key later by updating target_gid and removing old
                    data.pop(target_gid, None)
                    target_gid = gid
            else:
                # Only allow create when group_id not exists; editing requires id
                if not gid or gid.lower() == "none":
                    raise HTTPException(400, "缺少或无效的 group_id")
                if isinstance(data.get(gid), dict):
                    raise HTTPException(400, "该群已存在记录，请在列表中选择后进行修改/续费")
                target_gid = gid
                rec = {}

            # Calculate new expiry
            assert target_gid is not None
            rec = rec or {}

            new_expiry: datetime | None = None
            if length is not None and length > 0 and unit:
                # Add duration from current (or now if past/empty)
                current = now
                cur = rec.get("expiry")
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
            elif expiry_dt is not None:
                new_expiry = expiry_dt
            else:
                raise HTTPException(400, "缺少续费信息：需提供 length+unit 或 expiry")

            # Optional fields
            managed_by_bot = str(payload.get("managed_by_bot") or "").strip()
            renewed_by = str(payload.get("renewed_by") or "").strip()

            updates: Dict[str, Any] = {
                "group_id": target_gid,
                "expiry": new_expiry.isoformat(),
                "status": "active",
            }
            if managed_by_bot:
                updates["managed_by_bot"] = managed_by_bot
            if renewed_by:
                updates["last_renewed_by"] = renewed_by

            rec.update(updates)
            data[target_gid] = rec
            await _write_data(data)

            resp: Dict[str, Any] = {"group_id": target_gid, "expiry": new_expiry.isoformat()}
            if rid_raw is not None and str(rid_raw).strip() != "":
                try:
                    resp["id"] = int(rid_raw)
                except Exception:
                    pass
            return resp

        # 列出生成的续费码
        @router.get("/codes")
        async def api_codes(_: dict = Depends(_auth)):
            data = _ensure_generated_codes(await _read_data())
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
