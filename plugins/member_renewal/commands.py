from __future__ import annotations

import re
from datetime import datetime, timezone
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
from .config import config
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

# Register defaults to unified permissions.json
P = Plugin(enabled=True, level="all", scene="all")

# 生成续费码（仅私聊超管）
gen_code = P.on_regex(
    r"^ww生成续费码(\d+)(天|月|年)?$",
    name="generate_code",
    priority=10,
    permission=P.permission_cmd("generate_code"),
    enabled=True,
    level="superuser",
    scene="private",
)


@gen_code.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if not isinstance(event, PrivateMessageEvent):
        await matcher.finish("为安全起见，请在私聊中生成续费码。")
    matched = event.get_plaintext()
    m = re.match(r"^ww生成续费码(\d+)(天|月|年)?$", matched)
    assert m
    length = int(m.group(1))
    unit = m.group(2) or "天"

    data = _ensure_generated_codes(_read_data())
    code = generate_unique_code(length, unit)
    data["generatedCodes"][code] = {
        "length": length,
        "unit": unit,
        "generated_time": _now_utc().isoformat(),
    }
    _write_data(data)

    await matcher.finish(
        Message(
            f"已生成续费码（仅可使用一次）：\n{code}\n\n"
            "请将其发送到需要开通/续费的群聊中（首次开通也使用此码）。"
        )
    )


# 使用续费码（群聊）
use_code = P.on_regex(
    r"^ww续费(\d+)(天|月|年)-([A-Za-z0-9_]+)$",
    name="use_code",
    priority=10,
    enabled=True,
    level="all",
    scene="group",
)


@use_code.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("续费码只能在群聊中使用哦。")
    matched = event.get_plaintext()
    m = re.match(r"^ww续费(\d+)(天|月|年)-([A-Za-z0-9_]+)$", matched)
    assert m
    parsed_len = int(m.group(1))
    parsed_unit = m.group(2)
    code = matched
    gid = str(event.group_id)

    data = _ensure_generated_codes(_read_data())
    rec = data["generatedCodes"].get(code)
    if not rec:
        await matcher.finish("该续费码无效或已被使用。")

    if rec.get("length") != parsed_len or rec.get("unit") != parsed_unit:
        await matcher.finish("续费码信息不匹配，请检查。")

    now = _now_utc()
    current_expiry_str = (data.get(gid) or {}).get("expiry")
    if current_expiry_str:
        try:
            current_expiry = datetime.fromisoformat(current_expiry_str)
            if current_expiry.tzinfo is None:
                current_expiry = current_expiry.replace(tzinfo=timezone.utc)
        except Exception:
            current_expiry = now
    else:
        current_expiry = now

    if current_expiry < now:
        current_expiry = now

    new_expiry = _add_duration(current_expiry, parsed_len, parsed_unit)

    data[gid] = {
        "group_id": gid,
        "expiry": new_expiry.isoformat(),
        "last_renewed_by": str(event.user_id),
        "renewal_code_used": code,
        "managed_by_bot": str(event.self_id),
        "status": "active",
        "last_reminder_on": None,
    }
    data["generatedCodes"].pop(code, None)
    _write_data(data)

    await matcher.finish(
        Message(
            f"本群会员已成功开通/续费 {parsed_len}{parsed_unit}\n到期时间：{_format_cn(new_expiry)}"
        )
    )


# 到期查询（群聊）
check_group = P.on_regex(
    r"^ww到期$",
    name="check_group",
    priority=12,
    enabled=True,
    level="all",
    scene="group",
)


@check_group.handle()
async def _(_: Matcher, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await check_group.finish("此指令需在群聊中使用。")
    gid = str(event.group_id)
    data = _read_data()
    rec = data.get(gid)
    if not rec:
        await check_group.finish("未找到本群的会员记录。")
    try:
        expiry = datetime.fromisoformat(rec.get("expiry"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except Exception:
        await check_group.finish("记录损坏，无法解析到期时间。")
        return
    days = _days_remaining(expiry)
    if days < 0:
        status = "已到期"
    elif days == 0:
        status = "今天到期"
    else:
        status = f"有效(剩余{days}天)"
    await check_group.finish(Message(f"本群会员状态：{status}\n到期：{_format_cn(expiry)}"))


# 引导提示（低优先级，不拦截）
prompt = P.on_regex(
    r"^ww(购群|续费)$",
    name="prompt",
    priority=15,
    enabled=True,
    level="all",
    scene="all",
)


@prompt.handle()
async def _(_: Matcher):
    await prompt.finish("如需首次开通或续费，请联系管理员购买续费码（会员开通码），在群内直接发送即可生效。")


# 引导提示（高优先级，拦截）
purchase_prompt = P.on_regex(
    r"^ww(购群|续费)$",
    name="purchase_prompt",
    priority=9,
    block=True,
    enabled=True,
    level="all",
    scene="all",
)


@purchase_prompt.handle()
async def _(_: Matcher):
    await purchase_prompt.finish("如需首次开通或续费，请联系管理员购买续费码（会员开通码），在群内直接发送即可生效。 如需购买/续费请加群 757463664 联系。")


# 退群（需超管）
leave_with_gid_cmd = P.on_regex(
    r"^(?:ww)?退出群\s*(\d+)$",
    name="leave_group",
    priority=8,
    permission=P.permission_cmd("leave_group"),
    block=True,
    enabled=True,
    level="superuser",
    scene="all",
)


@leave_with_gid_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent, matched: str = RegexMatched()):
    m = re.match(r"^(?:ww)?退出群\s*(\d+)$", matched)
    if not m:
        await matcher.finish("格式错误，用法：ww退出群<群号> 或 退出群<群号>")
        return
    gid_str = m.group(1)
    try:
        gid = int(gid_str)
    except Exception:
        await matcher.finish("群号格式错误")
        return
    ok = False
    try:
        for bot in _choose_bots(str(getattr(event, "self_id", ""))):
            try:
                await bot.set_group_leave(group_id=gid, is_dismiss=False)
                ok = True
                break
            except Exception as e:
                logger.debug(
                    f"leave group {gid} via command failed on bot {getattr(bot, 'self_id', '?')}: {e}"
                )
                continue
    except Exception as e:
        logger.debug(f"leave command unexpected error: {e}")

    data = _read_data()
    data.pop(str(gid), None)
    _write_data(data)

    if ok:
        await matcher.finish("已退出群并移除配置记录。")
    else:
        await matcher.finish(f"尝试退群失败，但已移除配置记录：{gid}")


# 手动检查（需超管）
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
    await manual_check.finish(f"已处理：提醒 {r} 个群，退出 {l} 个群。")


# Scheduler: daily check (configurable time)
try:
    require("nonebot_plugin_apscheduler")
    from nonebot_plugin_apscheduler import scheduler

    if config.member_renewal_enable_scheduler:
        async def _job():
            try:
                r, l = await _check_and_process()
                logger.info(f"[member_renewal] check finished, reminded={r}, left={l}")
            except Exception as e:
                logger.exception(f"[member_renewal] check failed: {e}")

        scheduler.add_job(
            _job,
            trigger="cron",
            hour=int(getattr(config, "member_renewal_schedule_hour", 12)),
            minute=int(getattr(config, "member_renewal_schedule_minute", 0)),
            second=int(getattr(config, "member_renewal_schedule_second", 0)),
            id="member_renewal_check",
            replace_existing=True,
        )
except Exception:
    logger.warning("nonebot-plugin-apscheduler 未安装；定时检查已禁用。")


async def _check_and_process() -> Tuple[int, int]:
    data = _read_data()
    reminder_days = int(getattr(config, "member_renewal_reminder_days_before", 7))
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
            if getattr(config, "member_renewal_auto_leave_on_expire", True):
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
                content = (
                    "本群会员今天到期。请尽快联系管理员购买续费码（首次开通与续费同用），并在群内发送完成续费。"
                    if days == 0
                    else f"本群会员将在 {days} 天后到期。请尽快联系管理员购买续费码（首次开通与续费同用），并在群内发送完成续费。"
                )
                content = content + " 如需购买/续费请加群 757463664 联系。"
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
