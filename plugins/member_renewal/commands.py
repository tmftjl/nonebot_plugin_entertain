from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Tuple

from nonebot import require
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import RegexMatched
from nonebot.permission import SUPERUSER

from ...registry import Plugin
from .config import load_cfg
from .common import (
    _add_duration,
    _choose_bots,
    _days_remaining,
    _format_cn,
    _now_utc,
    _read_data,
    _today_str,
    _write_data,
    generate_unique_code,
    _ensure_generated_codes,
)


P = Plugin(enabled=True, level="all", scene="all")


# 控制台登录
login_cmd = P.on_regex(
    r"^控制台登录$",
    name="console_login",
    priority=10,
    permission=SUPERUSER,
    enabled=True,
    level="superuser",
    scene="private",
)


@login_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if not isinstance(event, PrivateMessageEvent):
        await matcher.finish("请在私聊使用该命令")
    token = str(int(_now_utc().timestamp()))[-6:]
    cfg = load_cfg()
    console_host = str(cfg.get("member_renewal_console_host", "http://localhost:8080") or "http://localhost:8080")
    login_url = f"{console_host}/member_renewal/console?token={token}"
    await matcher.finish(Message(f"控制台登录地址：{login_url}"))


# 生成续费码（管理员）
gen_code_cmd = P.on_regex(
    r"^ww生成续费码(\d+)(天|月|年)?$",
    name="gen_code",
    priority=10,
    permission=SUPERUSER,
    enabled=True,
    level="superuser",
    scene="all",
)


@gen_code_cmd.handle()
async def _(matcher: Matcher, matched: str = RegexMatched()):
    m = re.match(r"^ww生成续费码(\d+)(天|月|年)?$", matched)
    if not m:
        await matcher.finish("格式错误，用法：ww生成续费码<时长><天|月|年>")
        return
    length = int(m.group(1))
    unit = m.group(2) or "天"
    if unit not in ("天", "月", "年"):
        await matcher.finish("单位仅支持 天/月/年")
        return
    data = _ensure_generated_codes(_read_data())
    code = generate_unique_code(length, unit)
    rec: Dict[str, Any] = {
        "length": length,
        "unit": unit,
        "generated_time": _now_utc().isoformat(),
        "used_count": 0,
    }
    cfg = load_cfg()
    rec["max_use"] = int(cfg.get("member_renewal_code_max_use", 1) or 1)
    expire_days = int(cfg.get("member_renewal_code_expire_days", 0) or 0)
    if expire_days > 0:
        rec["expire_at"] = _add_duration(_now_utc(), expire_days, "天").isoformat()
    data["generatedCodes"][code] = rec
    _write_data(data)
    await matcher.finish(Message(f"续费码已生成：{code}"))


# 使用续费码（群内）
redeem_cmd = P.on_regex(
    r"^ww续费(\d+)(天|月|年)-([A-Za-z0-9_]+)$",
    name="redeem",
    priority=12,
    block=True,
    enabled=True,
    level="all",
    scene="group",
)


@redeem_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent, matched: str = RegexMatched()):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("请在群内使用续费码")
    m = re.match(r"^ww续费(\d+)(天|月|年)-([A-Za-z0-9_]+)$", matched)
    if not m:
        await matcher.finish("格式错误，用法：ww续费<时长><天|月|年>-<随机码>")
        return
    length = int(m.group(1))
    unit = m.group(2)
    code = f"ww续费{length}{unit}-{m.group(3)}"
    gid = str(getattr(event, "group_id", ""))

    data = _ensure_generated_codes(_read_data())
    codes = data.get("generatedCodes", {})
    rec = codes.get(code)
    if not isinstance(rec, dict):
        await matcher.finish("续费码不存在或已被使用")
        return
    # 过期检查
    expire_at = rec.get("expire_at")
    if expire_at:
        try:
            dt = datetime.fromisoformat(str(expire_at))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < _now_utc():
                await matcher.finish("续费码已过期")
                return
        except Exception:
            pass
    # 使用次数检查
    used = int(rec.get("used_count", 0) or 0)
    max_use = int(rec.get("max_use", 1) or 1)
    if used >= max_use:
        await matcher.finish("续费码已达使用上限")
        return

    now = _now_utc()
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

    data[gid] = {
        "group_id": gid,
        "expiry": new_expiry.isoformat(),
        "last_renewed_by": str(getattr(event, "user_id", "")),
        "renewal_code_used": code,
        "managed_by_bot": str(getattr(event, "self_id", "")),
        "status": "active",
        "last_reminder_on": None,
    }
    rec["used_count"] = used + 1
    if rec["used_count"] >= max_use:
        codes.pop(code, None)
    else:
        codes[code] = rec
    data["generatedCodes"] = codes
    _write_data(data)

    await matcher.finish(Message(f"本群会员已成功续期 {length}{unit}，到期时间：{_format_cn(new_expiry)}"))


# 手动检查
manual_check = P.on_regex(
    r"^ww检查会员$",
    name="manual_check",
    priority=10,
    permission=P.permission_cmd("manual_check"),
    enabled=True,
    level="superuser",
    scene="all",
)


@manual_check.handle()
async def _(_: Matcher):
    r, l = await _check_and_process()
    await manual_check.finish(f"已提醒 {r} 个群，退出 {l} 个群")


# 定时检查（根据配置时间）
try:
    require("nonebot_plugin_apscheduler")
    from nonebot_plugin_apscheduler import scheduler

    cfg = load_cfg()
    if bool(cfg.get("member_renewal_enable_scheduler", True)):
        async def _job():
            try:
                r, l = await _check_and_process()
                logger.info(f"[member_renewal] check finished, reminded={r}, left={l}")
            except Exception as e:
                logger.exception(f"[member_renewal] check failed: {e}")

        scheduler.add_job(
            _job,
            trigger="cron",
            hour=int(cfg.get("member_renewal_schedule_hour", 12) or 12),
            minute=int(cfg.get("member_renewal_schedule_minute", 0) or 0),
            second=int(cfg.get("member_renewal_schedule_second", 0) or 0),
            id="member_renewal_check",
            replace_existing=True,
        )
except Exception:
    logger.warning("nonebot-plugin-apscheduler 未安装，跳过计划任务。")


async def _check_and_process() -> Tuple[int, int]:
    data = _read_data()
    cfg = load_cfg()
    reminder_days = int(cfg.get("member_renewal_reminder_days_before", 7) or 7)
    today = _today_str()
    reminders = 0
    left = 0
    changed = False

    for k, v in data.items():
        if k == "generatedCodes" or not isinstance(v, dict):
            continue
        try:
            expiry = datetime.fromisoformat(v.get("expiry"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        status = v.get("status", "active")
        gid_str = str(v.get("group_id", k))
        try:
            gid = int(gid_str)
        except Exception:
            continue

        days = _days_remaining(expiry)

        if days < 0 and status != "expired":
            if bool(cfg.get("member_renewal_auto_leave_on_expire", True)):
                preferred = v.get("managed_by_bot")
                for bot in _choose_bots(preferred):
                    try:
                        await bot.set_group_leave(group_id=gid, is_dismiss=False)
                        left += 1
                        break
                    except Exception as e:
                        logger.debug(f"Leave group {gid} failed: {e}")
                        continue
            v["status"] = "expired"
            v["expired_at"] = _now_utc().isoformat()
            changed = True
            continue

        if 0 <= days <= reminder_days and status != "expired":
            last = v.get("last_reminder_on")
            if last != today:
                preferred = v.get("managed_by_bot")
                if days == 0:
                    content = "本群会员今天到期。请尽快联系管理员购买续费码（首次开通与续费同用），并在群内发送完成续费。"
                else:
                    content = f"本群会员将在 {days} 天后到期。请尽快联系管理员购买续费码（首次开通与续费同用），并在群内发送完成续费。"
                suffix = str(cfg.get("member_renewal_contact_suffix", "") or "").strip()
                if suffix and suffix not in content:
                    content = content + " " + suffix
                sent = False
                for bot in _choose_bots(preferred):
                    try:
                        await bot.send_group_msg(group_id=gid, message=Message(content))
                        sent = True
                        break
                    except Exception as e:
                        logger.debug(f"Notify group {gid} failed: {e}")
                        continue
                if sent:
                    v["last_reminder_on"] = today
                    reminders += 1
                    changed = True

    if changed:
        _write_data(data)
    return reminders, left

