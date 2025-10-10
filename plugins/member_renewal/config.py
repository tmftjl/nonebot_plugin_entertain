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
    # console
    "member_renewal_console_enable": False,
    # legacy single-token for compatibility
    "member_renewal_console_token": "",
    # new multi-token list: [{"token": str, "role": "viewer|operator|admin", "note": str?, "disabled": bool?}]
    "member_renewal_console_tokens": [],
    "member_renewal_console_ip_allowlist": [],
    # rate limit for APIs
    "member_renewal_rate_limit": {"window_sec": 15, "max": 120},
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
    # clamp rate limit
    rl = cfg.get("member_renewal_rate_limit") or {}
    if not isinstance(rl, dict):
        rl = {"window_sec": 15, "max": 120}
    rl["window_sec"] = int(max(1, int(rl.get("window_sec", 15))))
    rl["max"] = int(max(1, int(rl.get("max", 120))))
    cfg["member_renewal_rate_limit"] = rl
    # tokens normalize
    toks = cfg.get("member_renewal_console_tokens") or []
    if not isinstance(toks, list):
        toks = []
    norm = []
    for t in toks:
        if not isinstance(t, dict):
            continue
        token = str(t.get("token") or "").strip()
        role = str(t.get("role") or "viewer").lower()
        if role not in ("viewer", "operator", "admin"):
            role = "viewer"
        if token:
            norm.append({
                "token": token,
                "role": role,
                "note": str(t.get("note") or ""),
                "disabled": bool(t.get("disabled", False)),
            })
    cfg["member_renewal_console_tokens"] = norm


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
        return json.loads(json.dumps(self._obj))

    def save(self, new_obj: Dict[str, Any]) -> None:
        merged = {**DEFAULTS, **(new_obj or {})}
        save_plugin_config("member_renewal", merged, filename="config.json")
        self._obj = merged


config = _ConfigAdapter()
