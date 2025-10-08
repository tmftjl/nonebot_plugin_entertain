from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel


class Config(BaseModel):
    member_renewal_timezone: str = "Asia/Shanghai"
    member_renewal_enable_scheduler: bool = True
    member_renewal_schedule_hour: int = 12
    member_renewal_schedule_minute: int = 0
    member_renewal_schedule_second: int = 0
    member_renewal_reminder_days_before: int = 7
    member_renewal_auto_leave_on_expire: bool = True
    member_renewal_console_enable: bool = False
    member_renewal_console_token: str = ""


_plugin_dir = Path(__file__).parent
_cfg_path = _plugin_dir / "member_renewal.json"
_cfg_obj = {}
if _cfg_path.exists():
    try:
        _cfg_obj = json.loads(_cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        _cfg_obj = {}

config = Config.parse_obj(_cfg_obj)
