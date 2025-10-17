from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, delete

from .base_models import BaseIDModel, with_session


class Membership(BaseIDModel, table=True):
    """Group membership record.

    Stores membership status and expiry for a group.
    All datetime fields are stored as ISO strings in UTC.
    """

    group_id: str = Field(index=True, unique=True, nullable=False, title="group_id")
    expiry: Optional[str] = Field(default=None, nullable=True, title="expiry")
    last_renewed_by: Optional[str] = Field(default=None, nullable=True, title="last_renewed_by")
    renewal_code_used: Optional[str] = Field(default=None, nullable=True, title="renewal_code_used")
    managed_by_bot: Optional[str] = Field(default=None, nullable=True, title="managed_by_bot")
    status: str = Field(default="active", nullable=False, title="status")
    last_reminder_on: Optional[str] = Field(default=None, nullable=True, title="last_reminder_on")
    expired_at: Optional[str] = Field(default=None, nullable=True, title="expired_at")

    # ---- CRUD helpers ----
    @classmethod
    async def all(cls) -> List["Membership"]:
        """Fetch all membership rows."""
        # Reuse BaseIDModel.select_rows (decorated with with_session)
        return await cls.select_rows()  # type: ignore[return-value]

    @classmethod
    @with_session
    async def replace_all(
        cls,
        session: AsyncSession,
        rows: List[Dict[str, Any]],
    ) -> None:
        """Replace all membership rows with provided dictionaries.

        Each dict should contain fields matching the Membership model.
        """
        await session.execute(delete(cls))
        for r in rows:
            session.add(cls(**r))


class GeneratedCode(BaseIDModel, table=True):
    """Redeemable membership code.

    All datetime fields are stored as ISO strings in UTC.
    """

    code: str = Field(index=True, unique=True, nullable=False, title="code")
    length: int = Field(nullable=False, title="length")
    unit: str = Field(nullable=False, title="unit")
    generated_time: str = Field(nullable=False, title="generated_time")
    max_use: int = Field(default=1, nullable=False, title="max_use")
    used_count: int = Field(default=0, nullable=False, title="used_count")
    expire_at: Optional[str] = Field(default=None, nullable=True, title="expire_at")

    # ---- CRUD helpers ----
    @classmethod
    async def all(cls) -> List["GeneratedCode"]:
        """Fetch all generated codes."""
        return await cls.select_rows()  # type: ignore[return-value]

    @classmethod
    @with_session
    async def replace_all(
        cls,
        session: AsyncSession,
        rows: List[Dict[str, Any]],
    ) -> None:
        """Replace all codes with provided dictionaries."""
        await session.execute(delete(cls))
        for r in rows:
            session.add(cls(**r))


# ---- Snapshot helpers combining both models ----
async def read_snapshot() -> Dict[str, Any]:
    """Load all memberships and codes into a single dict snapshot.

    Structure:
        {
          "generatedCodes": { code: {length, unit, generated_time, ...} },
          "<group_id>": { ...membership fields... },
          ...
        }
    """
    data: Dict[str, Any] = {"generatedCodes": {}}

    mem_rows = await Membership.all()
    for m in mem_rows:
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

    codes = await GeneratedCode.all()
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

    return data


async def write_snapshot(obj: Dict[str, Any]) -> None:
    """Persist the given data snapshot into database by replacing rows."""
    # Build membership rows
    mem_rows: List[Dict[str, Any]] = []
    for k, v in obj.items():
        if k == "generatedCodes" or not isinstance(v, dict):
            continue
        mem_rows.append(
            {
                "group_id": str(v.get("group_id") or k),
                "expiry": v.get("expiry"),
                "last_renewed_by": v.get("last_renewed_by"),
                "renewal_code_used": v.get("renewal_code_used"),
                "managed_by_bot": v.get("managed_by_bot"),
                "status": str(v.get("status") or "active"),
                "last_reminder_on": v.get("last_reminder_on"),
                "expired_at": v.get("expired_at"),
            }
        )

    # Build code rows
    code_rows: List[Dict[str, Any]] = []
    gen_map = obj.get("generatedCodes") or {}
    if isinstance(gen_map, dict):
        for code, rec in gen_map.items():
            try:
                code_rows.append(
                    {
                        "code": str(code),
                        "length": int(rec.get("length")),
                        "unit": str(rec.get("unit")),
                        "generated_time": str(rec.get("generated_time")),
                        "max_use": int(rec.get("max_use", 1) or 1),
                        "used_count": int(rec.get("used_count", 0) or 0),
                        "expire_at": str(rec.get("expire_at")) if rec.get("expire_at") else None,
                    }
                )
            except Exception:
                continue

    await Membership.replace_all(mem_rows)
    await GeneratedCode.replace_all(code_rows)
