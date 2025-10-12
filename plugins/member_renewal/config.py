from __future__ import annotations

from typing import Any, Dict

from ...config import register_plugin_config


# Unified defaults for member_renewal (written once if file missing)
DEFAULTS: Dict[str, Any] = {
    # scheduler and timezone
    "member_renewal_timezone": "Asia/Shanghai",
    "member_renewal_enable_scheduler": True,
    "member_renewal_schedule_hour": 12,
    "member_renewal_schedule_minute": 0,
    "member_renewal_schedule_second": 0,
    # reminder behavior
    "member_renewal_reminder_days_before": 7,
    "member_renewal_daily_remind_once": True,
    "member_renewal_contact_suffix": " 咨询/加入交流QQ群 757463664 联系群管",
    "member_renewal_remind_template": "本群会员将在 {days} 天后到期（{expiry}），请尽快联系管理员续费。",
    "member_renewal_soon_threshold_days": 7,
    # expiry handling
    "member_renewal_auto_leave_on_expire": True,
    "member_renewal_leave_mode": "leave",
    "member_renewal_default_bot_id": "",
    # bots list for console: [{"bot_id": str, "bot_name": str?}]
    "member_renewal_bots": [],
    # console/web
    "member_renewal_console_enable": True,
    # optional: stats API base for web console
    "member_renewal_stats_api_url": "http://127.0.0.1:8000",
    # renewal code generation
    "member_renewal_code_prefix": "ww续费",
    "member_renewal_code_random_len": 6,  # hex chars
    "member_renewal_code_expire_days": 0,  # 0 means no expiry
    "member_renewal_code_max_use": 1,
    # export
    "member_renewal_export_fields": ["group_id", "expiry", "status", "last_renewed_by"],
}


# Legacy migration removed: project now only uses unified config file


def _validate(cfg: Dict[str, Any]) -> None:
    """Light normalization without default-merging (unified style)."""
    # strip legacy/unused keys if present
    for k in (
        "member_renewal_console_token",
        "member_renewal_console_tokens",
        "member_renewal_console_ip_allowlist",
        "member_renewal_rate_limit",
    ):
        if k in cfg:
            cfg.pop(k, None)

    # normalize bots list shape
    bots = cfg.get("member_renewal_bots")
    norm_bots: list[dict] = []
    if isinstance(bots, list):
        for b in bots:
            try:
                if not isinstance(b, dict):
                    continue
                bid = str(b.get("bot_id") or "").strip()
                bname = str(b.get("bot_name") or "").strip()
                if not bid:
                    continue
                norm_bots.append({"bot_id": bid, "bot_name": bname})
            except Exception:
                continue
    if norm_bots:
        cfg["member_renewal_bots"] = norm_bots


# Register using unified config proxy
REG = register_plugin_config("member_renewal", DEFAULTS, filename="config.json", validator=_validate)


def load_cfg() -> Dict[str, Any]:
    """Return current config dict (no default merge beyond on-create)."""
    return REG.load()


def save_cfg(cfg: Dict[str, Any]) -> None:
    REG.save(cfg or {})


def config_path() -> Path:
    return REG.path
