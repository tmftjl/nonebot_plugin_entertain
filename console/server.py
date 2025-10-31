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

# === AI Chat personas (file-based) ===
try:
    # 寤惰繜瀵煎叆锛岄伩鍏嶅湪鏈畨瑁?鏈惎鐢?ai_chat 鎻掍欢鏃舵姤閿?
    from ..plugins.ai_chat.config import (
        get_personas as ai_get_personas,
        get_personas_dir as ai_get_personas_dir,
        reload_all as ai_reload_ai_configs,
    )
except Exception:
    ai_get_personas = None  # type: ignore
    ai_get_personas_dir = None  # type: ignore
    ai_reload_ai_configs = None  # type: ignore


def _extract_token(request: Request) -> str:
    """浠庤姹備腑鎻愬彇璁块棶浠ょ墝锛歲uery/header/cookie."""
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


def _validate_token(token: str) -> bool:
    """鏍￠獙浠ょ墝锛氫笌绯荤粺閰嶇疆涓繚瀛樼殑鎺у埗鍙颁护鐗屽畬鍏ㄥ尮閰嶃€?

    浠ょ墝涓嶈杩囨湡锛屼粎鍦ㄦ瘡娆♀€滀粖姹愮櫥褰曗€濇椂閲嶇疆銆?
    """
    try:
        provided = str(token or "").strip()
        if not provided:
            return False
        cfg = load_cfg()
        saved = str(cfg.get("member_renewal_console_token") or "").strip()
        return bool(saved) and (provided == saved)
    except Exception:
        return False


def _auth(request: Request) -> dict:
    """绠€鍗曢壌鏉冿細瑕佹眰鎻愪緵鏈夋晥 token 鎵嶈兘璁块棶鎺у埗鍙版帴鍙ｃ€?""
    ip = request.client.host if request and request.client else ""
    token = _extract_token(request)
    if not _validate_token(token):
        raise HTTPException(401, "鏈巿鏉冿細缂哄皯鎴栨棤鏁堢殑璁块棶浠ょ墝")
    return {"role": "admin", "token_tail": token[-2:] if token else "", "ip": ip, "request": request}

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

        # 閫€缇わ紙涓嶅啀闇€瑕?bot_ids锛?
        @router.post("/leave_multi")
        async def api_leave_multi(payload: Dict[str, Any], request: Request, ctx: dict = Depends(_auth)):
            try:
                gid = int(payload.get("group_id"))
            except Exception as e:
                raise HTTPException(400, f"鍙傛暟閿欒: {e}")

            # 璇诲彇閫€缇ゆā寮忛厤缃?
            cfg = load_cfg()

            live = get_bots()
            bot = next(iter(live.values()), None)
            if not bot:
                raise HTTPException(500, "鏃犲彲鐢?Bot 鍙€€缇?)
            try:
                await bot.set_group_leave(group_id=gid)
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
        async def api_stats_today(_: dict = Depends(_auth)):
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
        async def api_get_permissions(_: dict = Depends(_auth)):
            from ..core.framework.config import load_permissions
            return load_permissions()

        @router.put("/permissions")
        async def api_update_permissions(payload: Dict[str, Any], _: dict = Depends(_auth)):
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
        async def api_get_config(_: dict = Depends(_auth)):
            """鑾峰彇鎵€鏈夋彃浠剁殑閰嶇疆锛堜粠鍐呭瓨缂撳瓨涓級"""
            from ..core.framework.config import get_all_plugin_configs
            return get_all_plugin_configs()

        @router.put("/config")
        async def api_update_config(payload: Dict[str, Any], _: dict = Depends(_auth)):
            """鏇存柊閰嶇疆 - 鏀寔鍗曚釜鎻掍欢鎴栨壒閲忔洿鏂帮紝鑷姩閲嶈浇鍒板唴瀛樼紦瀛?""
            try:
                from ..core.framework.config import save_all_plugin_configs, reload_all_configs
                # 鍒ゆ柇鏄惁涓衡€滄壒閲忔彃浠堕厤缃€濆舰鎬侊細褰㈠ { plugin: { ... }, ... }
                is_batch = isinstance(payload, dict) and all(isinstance(v, dict) for v in payload.values())
                success: bool = True
                errors: Dict[str, str] = {}
                if not is_batch:
                    raise HTTPException(400, "閰嶇疆鏍煎紡鏃犳晥锛氬繀椤讳负 {plugin: {...}} 缁撴瀯锛堝凡寮冪敤鏃ф牸寮忥級")

                # 鎵归噺鏇存柊锛歱ayload 涓?{ plugin: { ... }, ... }
                if is_batch:
                    # 鎵归噺鏇存柊妯″紡锛氫繚鎶ゆ帶鍒跺彴浠ょ墝涓嶈瑕嗙洊/涓㈠け
                    try:
                        if "system" in payload and isinstance(payload.get("system"), dict):
                            existing = load_cfg()
                            sys_in = payload.get("system") or {}
                            if isinstance(existing, dict) and isinstance(sys_in, dict):
                                if "member_renewal_console_token" in existing and "member_renewal_console_token" not in sys_in:
                                    sys_in["member_renewal_console_token"] = existing["member_renewal_console_token"]
                                if "member_renewal_console_token_updated_at" in existing and "member_renewal_console_token_updated_at" not in sys_in:
                                    sys_in["member_renewal_console_token_updated_at"] = existing["member_renewal_console_token_updated_at"]
                                payload["system"] = sys_in
                    except Exception:
                        pass
                    success, errors = save_all_plugin_configs(payload)
                if not success:
                    raise HTTPException(500, f"閮ㄥ垎閰嶇疆鏇存柊澶辫触: {errors}")
                elif not is_batch and False:
                    # 鍚戝悗鍏煎锛氬崟涓猻ystem閰嶇疆鏇存柊锛堝悎骞朵互淇濈暀浠ょ墝锛?
                    try:
                        existing = load_cfg()
                        if not isinstance(existing, dict):
                            existing = {}
                    except Exception:
                        existing = {}
                    try:
                        merged = dict(existing)
                        for k, v in (payload or {}).items():
                            merged[k] = v
                        # 鑻ユ彁浜や腑缂哄皯浠ょ墝瀛楁锛屼娇鐢ㄥ凡鏈夊€?
                        if "member_renewal_console_token" not in merged and "member_renewal_console_token" in existing:
                            merged["member_renewal_console_token"] = existing["member_renewal_console_token"]
                        if "member_renewal_console_token_updated_at" not in merged and "member_renewal_console_token_updated_at" in existing:
                            merged["member_renewal_console_token_updated_at"] = existing["member_renewal_console_token_updated_at"]
                    except Exception:
                        merged = payload
                    save_cfg(merged)

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
        async def api_get_plugins(_: dict = Depends(_auth)):
            try:
                from ..core.api import get_plugin_display_names
                return get_plugin_display_names()
            except Exception as e:
                raise HTTPException(500, f"鑾峰彇鎻掍欢淇℃伅澶辫触: {e}")

        # 鍛戒护鏄剧ず鍚嶏紙涓枃锛?
        @router.get("/commands")
        async def api_get_commands(_: dict = Depends(_auth)):
            try:
                from ..core.api import get_command_display_names
                return get_command_display_names()
            except Exception as e:
                raise HTTPException(500, f"鑾峰彇鍛戒护淇℃伅澶辫触: {e}")

        # 閰嶇疆 Schema - 鍓嶇娓叉煋鎵€闇€鍏冧俊鎭紙涓枃鍚?鎻忚堪/绫诲瀷/鍒嗙粍绛夛級
        @router.get("/config_schema")
        async def api_get_config_schema(_: dict = Depends(_auth)):
            try:
                from ..core.framework.config import get_all_plugin_schemas
                return get_all_plugin_schemas()
            except Exception as e:
                raise HTTPException(500, f"鑾峰彇閰嶇疆Schema澶辫触: {e}")

        # ==================== AI 瀵硅瘽锛氫汉鏍肩鐞?====================
        @router.get("/ai_chat/personas")
        async def api_ai_personas(_: dict = Depends(_auth)):
            if not ai_get_personas:
                raise HTTPException(500, "鏈壘鍒?AI 瀵硅瘽妯″潡锛屾棤娉曡鍙栦汉鏍?)
            try:
                personas = ai_get_personas() or {}
                # 搴忓垪鍖?
                data: Dict[str, Dict[str, str]] = {}
                for k, p in personas.items():
                    try:
                        # 浠呰繑鍥炲悕瀛椾笌璇︽儏锛堣鎯呮部鐢?system_prompt 鍐呭锛?                        data[k] = {
                            "name": getattr(p, "name", "") or "",
                            "details": getattr(p, "system_prompt", "") or "",
                        }
                    except Exception:
                        continue
                return {"personas": data}
            except Exception as e:
                raise HTTPException(500, f"璇诲彇浜烘牸澶辫触: {e}")

        def _sanitize_persona_key(key: str) -> str:
            s = (key or "").strip()
            if not s:
                raise HTTPException(400, "鍚嶇О涓嶈兘涓虹┖")
            if s in {".", ".."}:
                raise HTTPException(400, "鍚嶇О闈炴硶")
            invalid = set('<>":/\\|?*')
            if any(ch in invalid for ch in s):
                raise HTTPException(400, "鍚嶇О鍖呭惈闈炴硶瀛楃")
            if s.endswith(" ") or s.endswith("."):
                raise HTTPException(400, "鍚嶇О涓嶅厑璁镐互绌烘牸鎴栫偣缁撳熬")
            return s

        def _write_persona_file(dir_path: Path, key: str, name: str, details: str) -> None:
            # 鍐欏叆 Markdown锛堝甫 front matter锛?
            content = (
                f"---\nname: {name}\ndescription: {description}\n---\n\n{system_prompt}\n"
            )
            fp = dir_path / f"{key}.md"
            fp.write_text(content, encoding="utf-8")

        def _remove_persona_files(dir_path: Path, key: str) -> int:
            removed = 0
            for ext in (".md", ".txt", ".docx"):
                p = dir_path / f"{key}{ext}"
                try:
                    if p.exists():
                        p.unlink()
                        removed += 1
                except Exception:
                    continue
            return removed

        # 瑕嗗啓鍐欏叆鍑芥暟锛氫粎鍐欏叆璇︽儏锛堟鏂囷級锛屾枃浠跺悕=浜烘牸鍚嶅瓧
        def _write_persona_file(dir_path: Path, key: str, name: str, details: str) -> None:  # type: ignore[no-redef]
            content = f"{details}\n"
            fp = dir_path / f"{key}.md"
            fp.write_text(content, encoding="utf-8")

        @router.post("/ai_chat/persona")
        async def api_ai_persona_create(payload: Dict[str, Any], _: dict = Depends(_auth)):
            if not ai_get_personas_dir or not ai_reload_ai_configs:
                raise HTTPException(500, "鏈壘鍒?AI 瀵硅瘽妯″潡锛屾棤娉曞垱寤轰汉鏍?)
            name_raw = str(payload.get("name") or "").strip()
            details = str(payload.get("details") or "").strip()
            if not name_raw:
                raise HTTPException(400, "鍚嶇О涓嶈兘涓虹┖")
            if not details:
                raise HTTPException(400, "鎻忚堪涓嶈兘涓虹┖")
            key = _sanitize_persona_key(name_raw)
            name = name_raw
            # details 鍗充负鏂囦欢姝ｆ枃

            dir_path = ai_get_personas_dir()
            # 涓嶅厑璁歌鐩栧凡鏈夊悓鍚嶏紙浠绘剰鍚庣紑锛?
            for ext in (".md", ".txt", ".docx"):
                if (dir_path / f"{key}{ext}").exists():
                    raise HTTPException(400, "璇ュ悕绉板凡瀛樺湪")

            try:
                _write_persona_file(dir_path, key, name, details)
                # 閲嶈浇鍒板唴瀛?
                ai_reload_ai_configs()
                return {"success": True}
            except Exception as e:
                raise HTTPException(500, f"鍒涘缓澶辫触: {e}")

        @router.put("/ai_chat/persona/{key}")
        async def api_ai_persona_update(key: str, payload: Dict[str, Any], _: dict = Depends(_auth)):
            if not ai_get_personas_dir or not ai_reload_ai_configs:
                raise HTTPException(500, "鏈壘鍒?AI 瀵硅瘽妯″潡锛屾棤娉曟洿鏂颁汉鏍?)
            old_key = _sanitize_persona_key(key)
            name_raw = str(payload.get("name") or "").strip()
            details = str(payload.get("details") or "").strip()
            if not name_raw:
                raise HTTPException(400, "鍚嶇О涓嶈兘涓虹┖")
            if not details:
                raise HTTPException(400, "鎻忚堪涓嶈兘涓虹┖")
            new_key = _sanitize_persona_key(name_raw)
            name = name_raw

            dir_path = ai_get_personas_dir()

            # 鑻ラ噸鍛藉悕锛岀‘淇濈洰鏍囦笉瀛樺湪
            if new_key != old_key:
                for ext in (".md", ".txt", ".docx"):
                    if (dir_path / f"{new_key}{ext}").exists():
                        raise HTTPException(400, "鐩爣浜烘牸浠ｅ彿宸插瓨鍦?)

            # 鍏堝垹闄ゆ棫鐨勪换鎰忓悗缂€鏂囦欢锛岄伩鍏嶅悓 stem 閲嶅
            _remove_persona_files(dir_path, old_key)
            # 鍐欏叆鏂版枃浠?
            try:
                _write_persona_file(dir_path, new_key, name, details)
                ai_reload_ai_configs()
                return {"success": True, "key": new_key}
            except Exception as e:
                raise HTTPException(500, f"鏇存柊澶辫触: {e}")

        @router.delete("/ai_chat/persona/{key}")
        async def api_ai_persona_delete(key: str, _: dict = Depends(_auth)):
            if not ai_get_personas_dir or not ai_reload_ai_configs:
                raise HTTPException(500, "鏈壘鍒?AI 瀵硅瘽妯″潡锛屾棤娉曞垹闄や汉鏍?)
            k = _sanitize_persona_key(key)
            dir_path = ai_get_personas_dir()

            try:
                removed = _remove_persona_files(dir_path, k)
                if removed <= 0:
                    raise HTTPException(404, "鏈壘鍒板搴斾汉鏍兼枃浠?)
                ai_reload_ai_configs()
                return {"success": True}
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(500, f"鍒犻櫎澶辫触: {e}")

        # 鏁版嵁
        @router.get("/data")
        async def api_get_all(_: dict = Depends(_auth)):
            return await _read_data()

        # Bot 鍒楄〃锛堢敤浜庡墠绔笅鎷夐€夋嫨绠＄悊Bot锛?
        @router.get("/bots")
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
                    raise HTTPException(400, "length 鏃犳晥")
            if payload.get("unit") is not None:
                unit = str(payload.get("unit"))
                if unit not in UNITS:
                    raise HTTPException(400, "鍗曚綅鏃犳晥")

            # expiry optional
            expiry_dt = None
            expiry_raw = payload.get("expiry")
            if isinstance(expiry_raw, str) and expiry_raw.strip():
                try:
                    expiry_dt = datetime.fromisoformat(expiry_raw)
                    if expiry_dt.tzinfo is None:
                        expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    raise HTTPException(400, "expiry 鏃犳晥")

            # Determine target record: by id, or by existing group_id, or create new
            rec: Dict[str, Any] | None = None
            target_gid: str | None = None

            rid_raw = payload.get("id")
            if rid_raw is not None and str(rid_raw).strip() != "":
                # Edit by id
                try:
                    rid = int(rid_raw)
                except Exception:
                    raise HTTPException(400, "id 鏃犳晥")
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
                    raise HTTPException(404, "鏈壘鍒板搴旇褰?)

                # Allow renaming group_id when provided and unused
                if gid and gid != target_gid:
                    if isinstance(data.get(gid), dict):
                        raise HTTPException(400, "鐩爣缇ゅ凡瀛樺湪璁板綍")
                    # Move key later by updating target_gid and removing old
                    data.pop(target_gid, None)
                    target_gid = gid
            else:
                # Only allow create when group_id not exists; editing requires id
                if not gid or gid.lower() == "none":
                    raise HTTPException(400, "缂哄皯鎴栨棤鏁堢殑 group_id")
                if isinstance(data.get(gid), dict):
                    raise HTTPException(400, "璇ョ兢宸插瓨鍦ㄨ褰曪紝璇峰湪鍒楄〃涓€夋嫨鍚庤繘琛屼慨鏀?缁垂")
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
                raise HTTPException(400, "缂哄皯缁垂淇℃伅锛氶渶鎻愪緵 length+unit 鎴?expiry")

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


