from __future__ import annotations

import math
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from nonebot import get_bots
from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger
from sqlmodel import select, delete
from zoneinfo import ZoneInfo

from ..core.system_config import load_cfg
from ..db.base_models import async_maker, init_database
from ..db.membership_models import GeneratedCode, Membership
from ..core.framework.utils import plugin_data_dir


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
    await init_database()
    data: Dict[str, Any] = {"generatedCodes": {}}
    async with async_maker() as session:  # type: ignore[operator]
        # memberships
        result = await session.execute(select(Membership))
        rows = result.scalars().all()
        for m in rows:
            data[m.group_id] = {
                "group_id": m.group_id,
                "expiry": m.expiry,
                "last_renewed_by": m.last_renewed_by,
                "renewal_code_used": m.renewal_code_used,
                "managed_by_bot": m.managed_by_bot,
                "status": m.status,
                "last_reminder_on": m.last_reminder_on,
                "expired_at": m.expired_at,
            }
        # generated codes
        result = await session.execute(select(GeneratedCode))
        codes = result.scalars().all()
        gen_map: Dict[str, Any] = {}
        for c in codes:
            gen_map[c.code] = {
                "length": c.length,
                "unit": c.unit,
                "generated_time": c.generated_time,
                "max_use": c.max_use,
                "used_count": c.used_count,
                "expire_at": c.expire_at,
            }
        data["generatedCodes"] = gen_map
    # If database is empty, attempt a one-time migration from legacy JSON
    if not rows and not gen_map:
        try:
            legacy_dir = plugin_data_dir("membership")
            legacy_file = legacy_dir / "memberships.json"
            if legacy_file.exists():
                import json

                raw = legacy_file.read_text(encoding="utf-8")
                obj: Dict[str, Any] = json.loads(raw or "{}")
                if not isinstance(obj.get("generatedCodes"), dict):
                    obj["generatedCodes"] = {}
                # Persist into DB and return the migrated data
                await _write_data(obj)
                data = obj
                # best-effort rename backup
                try:
                    legacy_file.rename(legacy_file.with_suffix(".json.bak"))
                except Exception:
                    pass
        except Exception:
            pass
    return data


async def _write_data(obj: Dict[str, Any]) -> None:
    """Persist the given data snapshot into database.

    Strategy: replace all Membership and GeneratedCode rows with the provided content.
    Mirrors the previous JSON snapshot behavior to minimize changes.
    """
    await init_database()
    async with async_maker() as session:  # type: ignore[operator]
        # Replace memberships and codes
        await session.execute(delete(Membership))
        await session.execute(delete(GeneratedCode))

        # Insert memberships
        for k, v in obj.items():
            if k == "generatedCodes" or not isinstance(v, dict):
                continue
            m = Membership(
                group_id=str(v.get("group_id") or k),
                expiry=v.get("expiry"),
                last_renewed_by=v.get("last_renewed_by"),
                renewal_code_used=v.get("renewal_code_used"),
                managed_by_bot=v.get("managed_by_bot"),
                status=str(v.get("status") or "active"),
                last_reminder_on=v.get("last_reminder_on"),
                expired_at=v.get("expired_at"),
            )
            session.add(m)

        # Insert generated codes
        gen_map = obj.get("generatedCodes") or {}
        if isinstance(gen_map, dict):
            for code, rec in gen_map.items():
                try:
                    c = GeneratedCode(
                        code=str(code),
                        length=int(rec.get("length")),
                        unit=str(rec.get("unit")),
                        generated_time=str(rec.get("generated_time")),
                        max_use=int(rec.get("max_use", 1) or 1),
                        used_count=int(rec.get("used_count", 0) or 0),
                        expire_at=str(rec.get("expire_at")) if rec.get("expire_at") else None,
                    )
                except Exception:
                    continue
                session.add(c)

        await session.commit()


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
