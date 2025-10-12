from __future__ import annotations

import json
import math
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from nonebot import get_bots
from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger
from zoneinfo import ZoneInfo

from .config import load_cfg
from ...utils import config_dir


# Valid membership time units
UNITS = ("天", "月", "年")


# ----- Time helpers -----


def _tz():
    cfg = load_cfg()
    tzname = str(cfg.get("member_renewal_timezone", "Asia/Shanghai") or "Asia/Shanghai")
    try:
        return ZoneInfo(tzname)
    except Exception:
        logger.warning(
            f"member_renewal: invalid or unavailable timezone '{tzname}', fallback to +08:00"
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
_OLD_DATA_FILE = _PLUGIN_DIR / "group_memberships.json"
_NEW_DATA_FILE = config_dir("member_renewal") / "memberships.json"


def _ensure_file() -> None:
    # Ensure new path exists and migrate from legacy path once
    try:
        _NEW_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if not _NEW_DATA_FILE.exists():
        if _OLD_DATA_FILE.exists():
            try:
                text = _OLD_DATA_FILE.read_text(encoding="utf-8")
            except Exception:
                text = '{"generatedCodes": {}}'
            try:
                _NEW_DATA_FILE.write_text(text, encoding="utf-8")
            except Exception:
                try:
                    _NEW_DATA_FILE.write_text('{"generatedCodes": {}}', encoding="utf-8")
                except Exception:
                    pass
            # backup legacy file
            try:
                bak = _OLD_DATA_FILE.with_suffix(_OLD_DATA_FILE.suffix + ".bak")
                shutil.move(str(_OLD_DATA_FILE), str(bak))
            except Exception:
                pass
        else:
            try:
                _NEW_DATA_FILE.write_text('{"generatedCodes": {}}', encoding="utf-8")
            except Exception:
                pass


def _read_data() -> Dict[str, Any]:
    _ensure_file()
    try:
        raw = _NEW_DATA_FILE.read_text(encoding="utf-8")
        obj: Dict[str, Any] = json.loads(raw or "{}")
    except Exception:
        obj = {"generatedCodes": {}}
    if not isinstance(obj.get("generatedCodes"), dict):
        obj["generatedCodes"] = {}
    return obj


def _write_data(obj: Dict[str, Any]) -> None:
    _ensure_file()
    # atomic write
    tmp = _NEW_DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_NEW_DATA_FILE)


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
    # Use cryptographic randomness and unified config
    cfg = load_cfg()
    prefix = str(cfg.get("member_renewal_code_prefix", "ww续费") or "ww续费")
    n = int(cfg.get("member_renewal_code_random_len", 6) or 6)
    n = max(2, n)
    b = math.ceil(n / 2)
    rand = secrets.token_hex(b)[:n]
    return f"{prefix}{length}{unit}-{rand}"


def _choose_bots(preferred_id: Optional[str]) -> List[Bot]:
    bots_map = get_bots()
    bots: List[Bot] = []
    if preferred_id and preferred_id in bots_map:
        bots.append(bots_map[preferred_id])
    bots.extend([b for sid, b in bots_map.items() if sid != preferred_id])
    return bots

