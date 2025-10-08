from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from nonebot import get_bots
from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger
import secrets
from zoneinfo import ZoneInfo

from .config import config

# Valid membership time units
UNITS = ("天", "月", "年")


# ----- Time helpers -----


def _tz():
    try:
        return ZoneInfo(config.member_renewal_timezone)
    except Exception:
        # Fallback to +08:00 if timezone database is unavailable
        logger.warning(
            f"member_renewal: invalid or unavailable timezone '{config.member_renewal_timezone}', fallback to +08:00"
        )
        return timezone(timedelta(hours=8))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_local() -> datetime:
    return datetime.now(_tz())


def _format_cn(dt: datetime) -> str:
    return dt.astimezone(_tz()).strftime("%Y-%m-%d %H:%M")


def _today_str() -> str:
    return _now_local().strftime("%Y-%m-%d")


def _days_remaining(expiry: datetime) -> int:
    local_expiry = expiry.astimezone(_tz())
    today = _now_local().date()
    return (local_expiry.date() - today).days


# ----- Simple JSON storage (local file only) -----

_PLUGIN_DIR = Path(__file__).parent
DATA_FILE = _PLUGIN_DIR / "group_memberships.json"


def _ensure_file() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists() or not DATA_FILE.read_text(encoding="utf-8").strip():
        DATA_FILE.write_text('{"generatedCodes": {}}', encoding="utf-8")


def _read_data() -> Dict[str, Any]:
    _ensure_file()
    try:
        raw = DATA_FILE.read_text(encoding="utf-8")
        obj: Dict[str, Any] = json.loads(raw or "{}")
    except Exception:
        obj = {"generatedCodes": {}}
    if not isinstance(obj.get("generatedCodes"), dict):
        obj["generatedCodes"] = {}
    return obj


def _write_data(obj: Dict[str, Any]) -> None:
    _ensure_file()
    DATA_FILE.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _add_duration(start: datetime, length: int, unit: str) -> datetime:
    if unit == "天":
        return start + timedelta(days=length)
    if unit == "月":
        # Simple month add: 30 days per month for predictability
        return start + timedelta(days=30 * length)
    if unit == "年":
        return start + timedelta(days=365 * length)
    return start


def _ensure_generated_codes(obj: Dict[str, Any]) -> Dict[str, Any]:
    if "generatedCodes" not in obj or not isinstance(obj.get("generatedCodes"), dict):
        obj["generatedCodes"] = {}
    return obj


def generate_unique_code(length: int, unit: str) -> str:
    # Use cryptographic randomness to avoid collisions
    rand = secrets.token_hex(3)  # 6 hex chars
    return f"ww续费{length}{unit}-{rand}"


def _choose_bots(preferred_id: Optional[str]) -> List[Bot]:
    bots_map = get_bots()
    bots: List[Bot] = []
    if preferred_id and preferred_id in bots_map:
        bots.append(bots_map[preferred_id])
    bots.extend([b for sid, b in bots_map.items() if sid != preferred_id])
    return bots
