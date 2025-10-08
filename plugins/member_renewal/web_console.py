from __future__ import annotations

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

CONTACT_SUFFIX = " 购买/续费请加群 757463664 联系。"

def setup_web_console() -> None:
    """Mount optional FastAPI console and APIs if enabled in config."""
    try:
        if not getattr(config, "member_renewal_console_enable", False):
            return

        app = get_app()
        router = APIRouter(prefix="/member_renewal", tags=["member_renewal"])

        # 认证拦截器：从 Authorization Bearer 或 query 参数 token 中获取令牌
        # 校验失败返回 401 未授权
        def _auth(request: Request) -> None:
            token = ""
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
            if not token:
                token = request.query_params.get("token", "")
            if not config.member_renewal_console_token or token != config.member_renewal_console_token:
                raise HTTPException(status_code=401, detail="未授权或令牌无效")

        # 接口：获取全部数据
        # 方法：GET /member_renewal/data
        # 认证：需要有效令牌（Bearer 或 ?token=）
        # 请求：无
        # 返回：整个数据存储字典
        # 错误：401 未授权
        @router.get("/data")
        async def get_all(_: None = Depends(_auth)):
            return _read_data()

        # 接口：生成一个新的兑换码
        # 方法：POST /member_renewal/generate
        # 认证：需要有效令牌
        # 请求体：{"length": int, "unit": str(必须为 UNITS 之一)}
        # 返回：{"code": str}
        # 错误：400 参数无效，401 未授权
        @router.post("/generate")
        async def api_generate(payload: Dict[str, Any], _: None = Depends(_auth)):
            try:
                length = int(payload.get("length"))
                unit = str(payload.get("unit"))
                if unit not in UNITS:
                    raise ValueError("单位无效")
            except Exception as e:
                raise HTTPException(400, f"参数无效：{e}")
            data = _ensure_generated_codes(_read_data())
            code = generate_unique_code(length, unit)
            data["generatedCodes"][code] = {
                "length": length,
                "unit": unit,
                "generated_time": _now_utc().isoformat(),
            }
            _write_data(data)
            return {"code": code}

        # 接口：按时长续期（在当前或到期时间基础上增加时长）
        # 方法：POST /member_renewal/extend
        # 认证：需要有效令牌
        # 请求体：{"group_id": str, "length": int, "unit": str}
        # 返回：{"group_id": str, "expiry": ISO8601 str}
        # 错误：400 参数无效，401 未授权
        @router.post("/extend")
        async def api_extend(payload: Dict[str, Any], _: None = Depends(_auth)):
            try:
                gid = str(payload.get("group_id"))
                length = int(payload.get("length"))
                unit = str(payload.get("unit"))
                if unit not in UNITS:
                    raise ValueError("单位无效")
            except Exception as e:
                raise HTTPException(400, f"参数无效：{e}")
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
            return {"group_id": gid, "expiry": new_expiry.isoformat()}

        # 接口：设置绝对到期时间（覆盖原到期时间）
        # 方法：POST /member_renewal/set_expiry
        # 认证：需要有效令牌
        # 请求体：{"group_id": str, "expiry": ISO8601 str（可无 tz，默认 UTC）}
        # 返回：{"group_id": str, "expiry": ISO8601 str}
        # 错误：400 参数无效，401 未授权
        @router.post("/set_expiry")
        async def api_set_expiry(payload: Dict[str, Any], _: None = Depends(_auth)):
            try:
                gid = str(payload.get("group_id"))
                expiry = datetime.fromisoformat(str(payload.get("expiry")))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
            except Exception as e:
                raise HTTPException(400, f"参数无效：{e}")
            data = _read_data()
            rec = data.get(gid) or {}
            rec.update({"group_id": gid, "expiry": expiry.isoformat()})
            data[gid] = rec
            _write_data(data)
            return {"group_id": gid, "expiry": expiry.isoformat()}

        # 接口：机器人退出指定群聊
        # 方法：POST /member_renewal/leave
        # 认证：需要有效令牌
        # 请求体：{"group_id": int, "bot_id": str?（可选，优先使用该 bot）}
        # 返回：{"status": "ok"}
        # 错误：400 group_id 无效；500 所有机器人均退群失败；401 未授权
        @router.post("/leave")
        async def api_leave(payload: Dict[str, Any], _: None = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"无效的 group_id：{e}")
            preferred = str(payload.get("bot_id") or "")
            ok = False
            for bot in _choose_bots(preferred or None):
                try:
                    await bot.set_group_leave(group_id=gid, is_dismiss=False)
                    ok = True
                    break
                except Exception as e:
                    logger.debug(f"通过机器人退群失败：{e}")
                    continue
            if not ok:
                raise HTTPException(500, "所有机器人退群均失败")
            # 成功退群后，从配置中删除记录
            try:
                data = _read_data()
                data.pop(str(gid), None)
                _write_data(data)
            except Exception as e:
                logger.debug(f"控制台退群后删除记录失败：{e}")
            return {"status": "ok"}

        # 接口：在群内发送续费提醒
        # 方法：POST /member_renewal/remind
        # 认证：需要有效令牌
        # 请求体：{"group_id": int, "content": str?（可选），"bot_id": str?（可选）}
        #        若未提供 content，将采用默认提醒文案，并追加联系方式后缀
        # 返回：{"status": "ok"}
        # 错误：400 group_id 无效；500 所有机器人发送失败；401 未授权
        @router.post("/remind")
        async def api_remind(payload: Dict[str, Any], _: None = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"无效的 group_id：{e}")
            content = str(payload.get("content") or "本群会员即将到期，请尽快续费")
            if not payload.get("content"):
                content = "群成员会员即将到期，请尽快续费。"
            if "757463664" not in content:
                content = content + " 咨询/加入交流群 757463664 请联系管理员"
            preferred = str(payload.get("bot_id") or "")
            ok = False
            for bot in _choose_bots(preferred or None):
                try:
                    await bot.send_group_msg(group_id=gid, message=Message(content))
                    ok = True
                    break
                except Exception as e:
                    logger.debug(f"通过机器人发送提醒失败：{e}")
                    continue
            if not ok:
                raise HTTPException(500, "所有机器人发送失败")
            return {"status": "ok"}

        # 静态资源挂载：控制台前端静态文件
        static_dir = Path(__file__).parent / "web"
        app.mount(
            "/member_renewal/static",
            StaticFiles(directory=str(static_dir)),
            name="member_renewal_static",
        )

        # 接口：控制台页面（HTML）
        # 方法：GET /member_renewal/console
        # 认证：需要有效令牌
        # 返回：控制台网页 HTML
        @router.get("/console")
        async def console(_: None = Depends(_auth)):
            path = Path(__file__).parent / "web" / "console.html"
            return FileResponse(path, media_type="text/html")

        app.include_router(router)
        logger.info("member_renewal Web 控制台已挂载到 /member_renewal")
    except Exception as e:
        logger.warning(f"member_renewal 控制台已禁用或不可用：{e}")
