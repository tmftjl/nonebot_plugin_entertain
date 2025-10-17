from __future__ import annotations

from typing import Optional

from sqlmodel import Field, SQLModel

from .base_models import BaseIDModel


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
