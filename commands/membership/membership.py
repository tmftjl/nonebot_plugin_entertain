from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Tuple

from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from ...core.framework.registry import Plugin
from ...core.system_config import load_cfg
from ...console.membership_service import (
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

# 插件元信息（中文，UTF-8）
__plugin_meta__ = PluginMetadata(
    name="会员与控制台",
    description="群会员到期提醒/自动退群，续费码生成与兑换，简易 Web 控制台",
    usage="命令：控制台登录 / ww生成续费<数字><天|月|年> / ww续费<数字><天|月|年>-<随机码> / ww到期",
    type="application",
)



# 系统命令注册（中文、UTF-8、精简注释）
P = Plugin(name="core", category="system", enabled=True, level="all", scene="all")


# 控制台登录
login_cmd = P.on_regex(
    r"^今汐登录$",
    name="console_login",
    priority=5,
    block=True,
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
    console_host = str(
        cfg.get("member_renewal_console_host", "http://localhost:8080")
        or "http://localhost:8080"
    )
    login_url = f"{console_host}/member_renewal/console?token={token}"
    await matcher.finish(Message(f"控制台登录地址：{login_url}"))


# 生成续费码（超级用户）
gen_code_cmd = P.on_regex(
    r"^ww生成续费码(\d+)(天|月|年)$",
    name="gen_code",
    priority=5,
    block=True,
    permission=SUPERUSER,
    enabled=True,
    level="superuser",
    scene="all",
)


@gen_code_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if not isinstance(event, PrivateMessageEvent):
        await matcher.finish("为安全起见，请在私聊生成续费码")
    matched = event.get_plaintext()
    m = re.match(r"^ww生成续费码(\d+)(天|月|年)$", matched)
    assert m
    length = int(m.group(1))
    unit = m.group(2)

    data = _ensure_generated_codes(await _read_data())
    code = generate_unique_code(length, unit)
    data["generatedCodes"][code] = {
        "length": length,
        "unit": unit,
        "generated_time": _now_utc().isoformat(),
    }
    await _write_data(data)

    await matcher.finish(
        Message(
            f"已生成续费码（默认一次性）：{code}\n"
            "请将其发送到需要开通/续费的群聊中（首次开通也使用此码）"
        )
    )


# 使用续费码（群聊）
redeem_cmd = P.on_regex(
    r"^ww续费(\d+)(天|月|年)-([A-Za-z0-9_]+)$",
    name="redeem",
    priority=5,
    block=True,
    enabled=True,
    level="all",
    scene="group",
)


@redeem_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await matcher.finish("续费码只能在群聊中使用哦")
    matched = event.get_plaintext()
    m = re.match(r"^ww续费(\d+)(天|月|年)-([A-Za-z0-9_]+)$", matched)
    assert m
    parsed_len = int(m.group(1))
    parsed_unit = m.group(2)
    code = matched
    gid = str(event.group_id)

    data = _ensure_generated_codes(await _read_data())
    rec = data["generatedCodes"].get(code)
    if not rec:
        await matcher.finish("该续费码无效或已被使用")

    if rec.get("length") != parsed_len or rec.get("unit") != parsed_unit:
        await matcher.finish("续费码信息不匹配，请检查")

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
    await _write_data(data)

    await matcher.finish(
        Message(f"本群会员已成功续费{parsed_len}{parsed_unit}，到期时间：{_format_cn(new_expiry)}")
    )


# 到期查询（群聊）
check_group = P.on_regex(
    r"^ww到期$",
    name="check_group",
    priority=5,
    block=True,
    enabled=True,
    level="all",
    scene="group",
)


@check_group.handle()
async def _(_: Matcher, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await check_group.finish("该指令需在群聊中使用")
    gid = str(event.group_id)
    data = await _read_data()
    rec = data.get(gid)
    if not rec:
        await check_group.finish("未找到本群的会员记录")
    try:
        expiry = datetime.fromisoformat(rec.get("expiry"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    except Exception:
        await check_group.finish("记录损坏，无法解析到期时间")
        return
    days = _days_remaining(expiry)
    if days < 0:
        status = "已到期"
    elif days == 0:
        status = "今天到期"
    else:
        status = f"有效(剩余{days}天)"
    await check_group.finish(Message(f"本群会员状态：{status}\n到期：{_format_cn(expiry)}"))


# 引导提示（不拦截）
prompt = P.on_regex(
    r"^ww(拉群|续费)$",
    name="prompt",
    priority=5,
    block=True,
    enabled=True,
    level="all",
    scene="all",
)


@prompt.handle()
async def _(_: Matcher):
    await prompt.finish(
        "如需首次开通或续费，请联系管理员购买续费码（会员开通码），在群内直接发送即可生效"
    )


# 手动检查
manual_check = P.on_regex(
    r"^ww检查会员$",
    name="manual_check",
    priority=5,
    block=True,
    permission=P.permission_cmd("manual_check"),
    enabled=True,
    level="superuser",
    scene="all",
)


@manual_check.handle()
async def _(_: Matcher):
    r, l = await _check_and_process()
    await manual_check.finish(f"已提醒{r}个群，退出{l}个群")


# 定时检查（Cron）
try:
    from nonebot_plugin_apscheduler import scheduler

    cfg = load_cfg()
    if bool(cfg.get("member_renewal_enable_scheduler", True)):
        async def _job():
            try:
                r, l = await _check_and_process()
                logger.info(f"[membership] 定时检查完成，提醒={r}，退出={l}")
            except Exception as e:
                logger.exception(f"[membership] 定时检查失败: {e}")

        scheduler.add_job(
            _job,
            trigger="cron",
            hour=int(cfg.get("member_renewal_schedule_hour", 12) or 12),
            minute=int(cfg.get("member_renewal_schedule_minute", 0) or 0),
            second=int(cfg.get("member_renewal_schedule_second", 0) or 0),
            id="membership_check",
            replace_existing=True,
        )
except Exception:
    logger.warning("nonebot-plugin-apscheduler 未安装或未加载，跳过计划任务")


async def _check_and_process() -> Tuple[int, int]:
    """检查群到期，提醒或退群

    返回 (提醒数量, 退群数量)
    """
    data = await _read_data()
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

        # 已过期
        if days < 0 and status != "expired":
            if bool(cfg.get("member_renewal_auto_leave_on_expire", True)):
                # 读取退群模式配置
                preferred = v.get("managed_by_bot")
                for bot in _choose_bots(preferred):
                    try:
                        await bot.set_group_leave(group_id=gid)
                        left += 1
                        break
                    except Exception as e:
                        logger.debug(f"退群失败 {gid} : {e}")
                        continue
            v["status"] = "expired"
            v["expired_at"] = _now_utc().isoformat()
            changed = True
            continue

        # 即将到期提醒
        if 0 <= days <= reminder_days and status != "expired":
            last = v.get("last_reminder_on")

            # 检查是否每日仅提醒一次
            daily_remind_once = bool(cfg.get("member_renewal_daily_remind_once", True))
            should_remind = True

            if daily_remind_once:
                # 启用每日仅提醒一次：检查是否今天已提醒
                should_remind = (last != today)
            # else: 不启用时，每次检查都提醒（不检查 last）

            if should_remind:
                preferred = v.get("managed_by_bot")
                if days == 0:
                    content = (
                        "本群会员今天到期。请尽快联系管理员购买续费码（首次开通与续费同用），并在群内发送完成续费"
                    )
                else:
                    content = (
                        f"本群会员将在 {days} 天后到期。请尽快联系管理员购买续费码（首次开通与续费同用），并在群内发送完成续费"
                    )
                # 统一改为使用配置模板（如未设置则使用默认模板）
                tmpl = str(
                    cfg.get(
                        "member_renewal_remind_template",
                        "本群会员将在 {days} 天后到期（{expiry}），请尽快联系管理员续费",
                    )
                    or "本群会员将在 {days} 天后到期（{expiry}），请尽快联系管理员续费"
                )
                try:
                    content = tmpl.format(days=days, expiry=_format_cn(expiry))
                except Exception:
                    # 保底沿用原有文案
                    content = (
                        f"本群会员将在 {days} 天后到期。请尽快联系管理员购买续费码（首次开通与续费同用），并在群内发送完成续费"
                    )
                # 去掉提醒尾注：不再追加联系方式后缀
                sent = False
                for bot in _choose_bots(preferred):
                    try:
                        await bot.send_group_msg(group_id=gid, message=Message(content))
                        sent = True
                        break
                    except Exception as e:
                        logger.debug(f"提醒发送失败 {gid}: {e}")
                        continue
                if sent:
                    v["last_reminder_on"] = today
                    reminders += 1
                    changed = True

    if changed:
        await _write_data(data)
    return reminders, left


# ===== 配置重载回调 =====
def _reload_membership_scheduler():
    """配置重载时重新调度定时任务"""
    try:
        from nonebot_plugin_apscheduler import scheduler  # type: ignore

        cfg = load_cfg()
        enable = bool(cfg.get("member_renewal_enable_scheduler", True))
        if not enable:
            try:
                scheduler.remove_job("membership_check")  # type: ignore
                logger.info("[membership] 定时任务已禁用")
            except Exception:
                pass
            return

        hour = int(cfg.get("member_renewal_schedule_hour", 12) or 12)
        minute = int(cfg.get("member_renewal_schedule_minute", 0) or 0)
        second = int(cfg.get("member_renewal_schedule_second", 0) or 0)

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
            f"[membership] 配置重载：定时任务已更新为 {hour:02d}:{minute:02d}:{second:02d}"
        )
    except Exception as e:
        logger.debug(f"[membership] 配置重载失败: {e}")


# 注册配置重载回调
try:
    from ...core.framework.config import register_reload_callback
    register_reload_callback("system", _reload_membership_scheduler)
    logger.debug("[membership] 已注册配置重载回调")
except Exception as e:
    logger.debug(f"[membership] 注册配置重载回调失败: {e}")
