from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

# Use project-wide ConfigProxy instead of local pydantic model
from ...config import register_plugin_config, get_plugin_config, save_plugin_config
from ...utils import config_dir


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
    "member_renewal_contact_suffix": " 咨询/加入交流群 757463664 联系群管",
    "member_renewal_remind_template": "本群会员将在 {days} 天后到期（{expiry}），请尽快联系管理员续费。",
    "member_renewal_soon_threshold_days": 7,
    # expiry handling
    "member_renewal_auto_leave_on_expire": True,
    "member_renewal_leave_mode": "leave",
    "member_renewal_default_bot_id": "",
    # bots list for console: [{"bot_id": str, "bot_name": str?}]
    "member_renewal_bots": [],
    # console
    "member_renewal_console_enable": False,
    # renewal code generation
    "member_renewal_code_prefix": "ww续费",
    "member_renewal_code_random_len": 6,  # hex chars
    "member_renewal_code_expire_days": 0,  # 0 means no expiry
    "member_renewal_code_max_use": 1,
    # export
    "member_renewal_export_fields": ["group_id", "expiry", "status", "last_renewed_by"],
}


def _migrate_legacy_config() -> None:
    """Migrate old plugins/member_renewal/member_renewal.json to
    config/member_renewal/config.json once, preserving fields.
    """
    old = Path(__file__).parent / "member_renewal.json"
    new = config_dir("member_renewal") / "config.json"
    if new.exists():
        return
    if not old.exists():
        return
    try:
        data = json.loads(old.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    # merge into defaults
    merged = {**DEFAULTS, **data}
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        new.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _validate(cfg: Dict[str, Any]) -> None:
    # very light checks; fill missing keys with defaults
    for k, v in DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v
    # remove legacy keys
    for k in (
        "member_renewal_console_token",
        "member_renewal_console_tokens",
        "member_renewal_console_ip_allowlist",
        "member_renewal_rate_limit",
    ):
        if k in cfg:
            cfg.pop(k, None)

    # normalize bots list
    bots = cfg.get("member_renewal_bots") or []
    if not isinstance(bots, list):
        bots = []
    norm_bots = []
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
    cfg["member_renewal_bots"] = norm_bots


_migrate_legacy_config()

# Register and ensure config file exists
register_plugin_config("member_renewal", DEFAULTS, filename="config.json", validator=_validate)


class _ConfigAdapter:
    """Attribute-style adapter for the JSON config file.

    Retains backward-compatible attribute names used across the plugin.
    """

    def __init__(self) -> None:
        self._load()

    def _load(self) -> None:
        self._obj: Dict[str, Any] = get_plugin_config("member_renewal", filename="config.json")

    def reload(self) -> None:
        self._load()

    def __getattr__(self, item: str):  # fallback to defaults when missing
        if item in self._obj:
            return self._obj[item]
        if item in DEFAULTS:
            return DEFAULTS[item]
        raise AttributeError(item)

    def to_dict(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self._obj, ensure_ascii=False))

    def save(self, new_obj: Dict[str, Any]) -> None:
        merged = {**DEFAULTS, **(new_obj or {})}
        save_plugin_config("member_renewal", merged, filename="config.json")
        self._obj = merged


config = _ConfigAdapter()

