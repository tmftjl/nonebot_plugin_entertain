from __future__ import annotations

from datetime import datetime, timezone
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


def _auth(request: Request) -> dict:
    ip = request.client.host if request and request.client else ""
    return {"role": "admin", "token_tail": "", "ip": ip, "request": request}


def _contact_suffix() -> str:
    cfg = load_cfg()
    return str(cfg.get("member_renewal_contact_suffix", " 鍜ㄨ/鍔犲叆浜ゆ祦QQ缇?757463664 鑱旂郴缇ょ") or "")


def setup_web_console() -> None:
    try:
        if not bool(load_cfg().get("member_renewal_console_enable", False)):
            return

        app = get_app()
        router = APIRouter(prefix="/member_renewal", tags=["member_renewal"])

        # 鍐呴儴锛氭牴鎹郴缁熼厤缃噸缃?绉婚櫎浼氬憳妫€鏌ュ畾鏃朵换鍔?
        async def _membership_job():
            try:
                from ..commands.membership.membership import _check_and_process  # type: ignore

                r, l = await _check_and_process()
                logger.info(f"[membership] 瀹氭椂妫€鏌ュ畬鎴愶紝鎻愰啋={r}锛岄€€鍑?{l}")
            except Exception as e:
                logger.exception(f"[membership] 瀹氭椂妫€鏌ュけ璐? {e}")

        def _reschedule_membership_job() -> None:
            try:
                # 鍙€変緷璧栵細鏈畨瑁呭垯璺宠繃
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
                # 浣跨敤涓庢彃浠剁浉鍚岀殑浠诲姟 ID锛岄伩鍏嶉噸澶嶏紱瀛樺湪鍒欐浛鎹?
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
                    f"[membership] 瀹氭椂浠诲姟宸查噸杞戒负 {hour:02d}:{minute:02d}:{second:02d}"
                )
            except Exception:
                # 鏈畨瑁呰皟搴﹀櫒鎴栬繍琛岀幆澧冧笉鏀寔鏃堕潤榛樿烦杩?
                pass

        # 鎻愰啋缇わ紙涓嶅啀闇€瑕?bot_ids锛?
        @router.post("/remind_multi")
        async def api_remind_multi(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"鍙傛暟閿欒: {e}")
            # 鏋勯€犳彁閱掑唴瀹癸細浼樺厛浣跨敤 payload.content锛屽惁鍒欎娇鐢ㄩ厤缃ā鏉?
            cfg = load_cfg()
            tmpl = str(
                cfg.get(
                    "member_renewal_remind_template",
                    "鏈兢浼氬憳灏嗗湪 {days} 澶╁悗鍒版湡锛坽expiry}锛夛紝璇峰敖蹇仈绯荤鐞嗗憳缁垂",
                )
                or "鏈兢浼氬憳灏嗗湪 {days} 澶╁悗鍒版湡锛坽expiry}锛夛紝璇峰敖蹇仈绯荤鐞嗗憳缁垂"
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
                    content = "鏈兢浼氬憳鍗冲皢鍒版湡锛岃灏藉揩缁垂"
            # 鎸夎姹傜Щ闄ゅ熬娉紝涓嶅啀杩藉姞鑱旂郴鏂瑰紡鍚庣紑
            live = get_bots()
            bot = next(iter(live.values()), None)
            if not bot:
                raise HTTPException(500, "鏃犲彲鐢?Bot 鍙彂閫佹彁閱?)
            try:
                await bot.send_group_msg(group_id=gid, message=Message(content))
            except Exception as e:
                logger.debug(f"remind_multi send failed: {e}")
                raise HTTPException(500, f"鍙戦€佹彁閱掑け璐? {e}")
            return {"sent": 1}

        # 鑷畾涔夐€氱煡锛氭敮鎸佹枃鏈笌鍥剧墖锛坆ase64:// 鎴?URL锛夛紝鎵归噺缇ゅ彂
        @router.post("/notify")
        async def api_notify(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                raw_ids = payload.get("group_ids")
                if isinstance(raw_ids, (list, tuple)):
                    group_ids = [int(x) for x in raw_ids if str(x).strip()]
                else:
                    raise ValueError("group_ids 蹇呴』涓烘暟缁?)
            except Exception as e:
                raise HTTPException(400, f"鍙傛暟鏃犳晥: {e}")

            text = str(payload.get("text") or "")
            imgs = payload.get("images") or []
            if not group_ids:
                raise HTTPException(400, "鏈寚瀹氫换浣曠兢缁?)

            def _norm_img(u: object) -> str:
                try:
                    s = str(u or "")
                except Exception:
                    return ""
                if not s:
                    return ""
                # 鏀寔 data:image/*;base64,xxx
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

            # 鍙栦竴涓彲鐢ㄧ殑 Bot
            live = get_bots()
            bot = next(iter(live.values()), None)
            if not bot:
                raise HTTPException(500, "鏃犲彲鐢?Bot 鍙彂閫侀€氱煡")

            sent = 0
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
            return {"sent": sent}

        # 閫€缇わ紙涓嶅啀闇€瑕?bot_ids锛?
        @router.post("/leave_multi")
        async def api_leave_multi(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"鍙傛暟閿欒: {e}")
            live = get_bots()
            bot = next(iter(live.values()), None)
            if not bot:
                raise HTTPException(500, "鏃犲彲鐢?Bot 鍙€€缇?)
            try:
                await bot.set_group_leave(group_id=gid, is_dismiss=False)
            except Exception as e:
                logger.debug(f"leave_multi failed: {e}")
                raise HTTPException(500, f"閫€鍑哄け璐? {e}")
            # 鍒犻櫎璁板綍锛堝彲閫夛級
            try:
                data = await _read_data()
                data.pop(str(gid), None)
                await _write_data(data)
            except Exception as e:
                logger.debug(f"web console leave_multi: remove record failed: {e}")
            return {"left": 1}

        # 缁熻锛氳浆鍙戝埌缁熻鏈嶅姟 API
        @router.get("/stats/today")
        async def api_stats_today():
            stats_api_url = str(load_cfg().get("member_renewal_stats_api_url", "http://127.0.0.1:8000") or "http://127.0.0.1:8000").rstrip("/")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{stats_api_url}/stats/today", timeout=10.0)
                    resp.raise_for_status()
                    return resp.json()
            except Exception as e:
                logger.error(f"鑾峰彇缁熻澶辫触: {e}")
                raise HTTPException(500, f"鑾峰彇缁熻澶辫触: {e}")
        # 鏉冮檺
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
                # 瑙勮寖鍖栧苟绔嬪嵆閲嶈浇鍒板唴瀛?
                try:
                    optimize_permissions()
                except Exception:
                    pass
                try:
                    reload_permissions()
                except Exception:
                    pass
                return {"success": True, "message": "鏉冮檺閰嶇疆宸叉洿鏂板苟鐢熸晥"}
            except Exception as e:
                raise HTTPException(500, f"鏇存柊鏉冮檺澶辫触: {e}")

        # 閰嶇疆 - 鑾峰彇鎵€鏈夋彃浠堕厤缃?
        @router.get("/config")
        async def api_get_config():
            """鑾峰彇鎵€鏈夋彃浠剁殑閰嶇疆锛堜粠鍐呭瓨缂撳瓨涓級"""
            from ..core.framework.config import get_all_plugin_configs
            return get_all_plugin_configs()

        @router.put("/config")
        async def api_update_config(payload: Dict[str, Any]):
            """鏇存柊閰嶇疆 - 鏀寔鍗曚釜鎻掍欢鎴栨壒閲忔洿鏂帮紝鑷姩閲嶈浇鍒板唴瀛樼紦瀛?""
            try:
                from ..core.framework.config import save_all_plugin_configs, reload_all_configs

                # 妫€鏌ayload鏄惁鍖呭惈澶氫釜鎻掍欢閰嶇疆
                if "system" in payload or len(payload) > 1:
                    # 鎵归噺鏇存柊妯″紡
                    success, errors = save_all_plugin_configs(payload)
                    if not success:
                        raise HTTPException(500, f"閮ㄥ垎閰嶇疆鏇存柊澶辫触: {errors}")
                else:
                    # 鍚戝悗鍏煎锛氬崟涓猻ystem閰嶇疆鏇存柊
                    save_cfg(payload)

                # 淇濆瓨鎴愬姛鍚庯紝绔嬪嵆閲嶈浇鎵€鏈夐厤缃埌鍐呭瓨缂撳瓨
                ok, details = reload_all_configs()
                if not ok:
                    logger.warning(f"閰嶇疆閲嶈浇閮ㄥ垎澶辫触: {details}")

                # 閲嶈浇瀹氭椂浠诲姟锛堣嫢鏇存柊浜唖ystem閰嶇疆锛?
                if "system" in payload:
                    _reschedule_membership_job()

                return {"success": True, "message": "閰嶇疆宸叉洿鏂板苟閲嶈浇鍒板唴瀛?}
            except Exception as e:
                raise HTTPException(500, f"鏇存柊閰嶇疆澶辫触: {e}")

        # 鎻掍欢鏄剧ず鍚嶏紙涓枃锛?
        @router.get("/plugins")
        async def api_get_plugins():
            try:
                from ..core.api import get_plugin_display_names
                return get_plugin_display_names()
            except Exception as e:
                raise HTTPException(500, f"鑾峰彇鎻掍欢淇℃伅澶辫触: {e}")

        # 鍛戒护鏄剧ず鍚嶏紙涓枃锛?
        @router.get("/commands")
        async def api_get_commands():
            try:
                from ..core.api import get_command_display_names
                return get_command_display_names()
            except Exception as e:
                raise HTTPException(500, f"鑾峰彇鍛戒护淇℃伅澶辫触: {e}")

        # 閰嶇疆 Schema - 鍓嶇娓叉煋鎵€闇€鍏冧俊鎭紙涓枃鍚?鎻忚堪/绫诲瀷/鍒嗙粍绛夛級
        @router.get("/config_schema")
        async def api_get_config_schema():
            try:
                from ..core.framework.config import get_all_plugin_schemas
                return get_all_plugin_schemas()
            except Exception as e:
                raise HTTPException(500, f"鑾峰彇閰嶇疆Schema澶辫触: {e}")

        # 鏁版嵁
        @router.get("/data")
        async def api_get_all(_: dict = Depends(_auth)):
            return await _read_data()

        # Bot 鍒楄〃锛堢敤浜庡墠绔笅鎷夐€夋嫨绠＄悊Bot锛?        @router.get("/bots")
        async def api_get_bots(_: dict = Depends(_auth)):
            try:
                bots_map = get_bots()
                # 杩斿洖 self_id 鍒楄〃
                ids = list(bots_map.keys())
                return {"bots": ids}
            except Exception as e:
                logger.debug(f"/bots error: {e}")
                return {"bots": []}

        # 鐢熸垚缁垂鐮?
        @router.post("/generate")
        async def api_generate(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                length = int(payload.get("length"))
                unit = str(payload.get("unit"))
                if unit not in UNITS:
                    raise ValueError("鍗曚綅鏃犳晥")
            except Exception as e:
                raise HTTPException(400, f"鍙傛暟鏃犳晥: {e}")
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
                # 浣跨敤 UNITS[0] 瀵瑰簲鐨勫崟浣嶏紙閫氬父涓衡€滃ぉ鈥濓級
                rec["expire_at"] = _add_duration(_now_utc(), expire_days, UNITS[0]).isoformat()
            data["generatedCodes"][code] = rec
            await _write_data(data)
            return {"code": code}

        # 寤堕暱鍒版湡
        @router.post("/extend")
        async def api_extend(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = str(payload.get("group_id"))
                length = int(payload.get("length"))
                unit = str(payload.get("unit"))
                if unit not in UNITS:
                    raise ValueError("鍗曚綅鏃犳晥")
            except Exception as e:
                raise HTTPException(400, f"鍙傛暟鏃犳晥: {e}")
            now = _now_utc()
            data = await _read_data()
            # 鑻ヤ紶鍏?id锛屽垯鎸夎褰曚富閿繘琛屼慨鏀癸紙閫夋嫨缇ょ殑鎯呭喌锛?            rid_raw = payload.get("id")
            if rid_raw is not None and str(rid_raw).strip() != "":
                try:
                    rid = int(rid_raw)
                except Exception:
                    raise HTTPException(400, "id 鏃犳晥")

                # 鍦ㄦ暟鎹揩鐓т腑瀹氫綅璇?id 鎵€瀵瑰簲鐨?group_id
                target_gid = None
                rec = None
                for k, v in data.items():
                    if k == "generatedCodes" or not isinstance(v, dict):
                        continue
                    try:
                        if int(v.get("id") or -1) == rid:
                            target_gid = str(k)
                            rec = v
                            break
                    except Exception:
                        continue
                if not target_gid:
                    raise HTTPException(404, "\u672A\u627E\u5230\u5BF9\u5E94\u8BB0\u5F55")

                current = now
                cur = (rec or {}).get("expiry")
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

                rec = rec or {}
                rec.update(updates)
                data[target_gid] = rec
                await _write_data(data)
                return {"id": rid, "group_id": target_gid, "expiry": new_expiry.isoformat()}
            # 鏂板璺緞浠呭厑璁稿綋鏈€夋嫨璁板綍鏃朵娇鐢紝涓旇姹傛湁鏁堢殑 group_id
            # 鑻ュ凡瀛樺湪璇ョ兢璁板綍锛屽垯涓嶅厑璁搁€氳繃缇ゅ彿杩涜淇敼
            if not gid or gid.strip() == "" or gid.strip().lower() == "none":
                raise HTTPException(400, "缂哄皯鎴栨棤鏁堢殑 group_id")
            if isinstance(data.get(gid), dict):
                raise HTTPException(400, "\u8BE5\u7FA4\u5DF2\u5B58\u5728\u8BB0\u5F55\uFF0C\u8BF7\u5728\u5217\u8868\u4E2D\u9009\u62E9\u540E\u8FDB\u884C\u4FEE\u6539/\u7EED\u8D39")

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
            # 闄勫姞鍙€変俊鎭細绠＄悊Bot銆佺画璐逛汉銆佸娉?            managed_by_bot = str(payload.get("managed_by_bot") or "").strip()
            renewed_by = str(payload.get("renewed_by") or "").strip()

            updates: Dict[str, Any] = {
                "group_id": gid,
                "expiry": new_expiry.isoformat(),
                "status": "active",
            }
            if managed_by_bot:
                updates["managed_by_bot"] = managed_by_bot
            if renewed_by:
                # 涓庝娇鐢ㄧ画璐圭爜閫昏緫淇濇寔涓€鑷村瓧娈靛悕
                updates["last_renewed_by"] = renewed_by
            # 'remark' 鏆備笉鎸佷箙鍖栵紙妯″瀷鏈寘鍚瀛楁锛?
            rec.update(updates)
            data[gid] = rec
            await _write_data(data)
            return {"group_id": gid, "expiry": new_expiry.isoformat()}

        # 鍒楀嚭鐢熸垚鐨勭画璐圭爜
        @router.get("/codes")
        async def api_codes(_: dict = Depends(_auth)):
            data = _ensure_generated_codes(await _read_data())
            return data.get("generatedCodes", {})

        # 杩愯瀹氭椂浠诲姟
        @router.post("/job/run")
        async def api_run_job(_: dict = Depends(_auth)):
            try:
                from ..commands.membership.membership import _check_and_process  # type: ignore
                r, l = await _check_and_process()
                return {"reminded": r, "left": l}
            except Exception as e:
                raise HTTPException(500, f"鎵ц澶辫触: {e}")

        # 闈欐€佽祫婧愪笌鎺у埗鍙伴〉闈?
        static_dir = Path(__file__).parent / "web"
        app.mount("/member_renewal/static", StaticFiles(directory=str(static_dir)), name="member_renewal_static")

        @router.get("/console")
        async def console(_: dict = Depends(_auth)):
            path = Path(__file__).parent / "web" / "console.html"
            return FileResponse(path, media_type="text/html")

        app.include_router(router)
        logger.info("member_renewal Web 鎺у埗鍙板凡鎸傝浇 /member_renewal")
    except Exception as e:
        logger.warning(f"member_renewal Web 鎺у埗鍙版寕杞藉け璐? {e}")

