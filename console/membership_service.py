from __future__ import annotations

import math
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from nonebot import get_bots
from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger
 
from zoneinfo import ZoneInfo

from ..core.system_config import load_cfg
from ..db.membership_models import read_snapshot, write_snapshot


# 有效时长单位
UNITS = ("天", "月", "年")


# 时区与时间工具
def _tz():
    cfg = load_cfg()
    tzname = str(cfg.get("member_renewal_timezone", "Asia/Shanghai") or "Asia/Shanghai")
    try:
        return ZoneInfo(tzname)
    except Exception:
        logger.warning(f"membership: 无效或不可用的时区 '{tzname}'，改用 +08:00")
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


# 数据库存储（SQLite via SQLModel）
async def _read_data() -> Dict[str, Any]:
    """Load all memberships and codes from the database as a dict structure.

    Structure:
        {
          "generatedCodes": { code: {length, unit, generated_time} },
          "<group_id>": { ...membership fields... },
          ...
        }
    """
    return await read_snapshot()


async def _write_data(obj: Dict[str, Any]) -> None:
    """Persist the given data snapshot into database via model helpers."""
    await write_snapshot(obj)


def _add_duration(start: datetime, length: int, unit: str) -> datetime:
    if unit == "天":
        return start + timedelta(days=length)
    if unit == "月":
        # 简化：按 30 天算 1 个月
        return start + timedelta(days=30 * length)
    if unit == "年":
        return start + timedelta(days=365 * length)
    return start


def _ensure_generated_codes(obj: Dict[str, Any]) -> Dict[str, Any]:
    if "generatedCodes" not in obj or not isinstance(obj.get("generatedCodes"), dict):
        obj["generatedCodes"] = {}
    return obj


def generate_unique_code(length: int, unit: str) -> str:
    # 生成唯一续费码：前缀 + 时长 + 单位 + 随机串
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
