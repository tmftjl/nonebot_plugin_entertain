from __future__ import annotations

import asyncio
import sqlite3
from functools import wraps
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, TypeVar
from typing_extensions import Concatenate, ParamSpec

from nonebot.log import logger
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker  # type: ignore
from sqlmodel import Field, SQLModel, and_, select

from ..core.framework.utils import data_dir


# ---- Type vars ----
T_BaseIDModel = TypeVar("T_BaseIDModel", bound="BaseIDModel")
P = ParamSpec("P")
R = TypeVar("R")


# ---- Database config (SQLite-only for this project) ----
# Database file under data/entertain/entertain.db
DB_PATH = data_dir() / "entertain.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = None  # set on init
async_maker: async_sessionmaker[AsyncSession] = None  # type: ignore[assignment]
_db_init_lock = asyncio.Lock()
_db_initialized = False
sqlite_semaphore: Optional[asyncio.Semaphore] = None


async def init_database() -> None:
    """Initialize async SQLite engine and create tables.

    This repository favors a simple, embedded SQLite database located at
    data/db/entertain.db to avoid external services and DSN configs.
    """
    global _db_initialized, engine, async_maker, sqlite_semaphore
    if _db_initialized:
        return
    async with _db_init_lock:
        if _db_initialized:
            return
        logger.info("[DB] Initializing SQLite database...")
        try:
            # Create engine with SQLite tuning
            eng = create_async_engine(
                DB_URL,
                echo=False,
                pool_recycle=1800,
                connect_args={"check_same_thread": False},
            )

            @event.listens_for(eng.sync_engine, "connect")
            def _set_pragmas(dbapi_connection: sqlite3.Connection, connection_record):  # type: ignore[override]
                try:
                    cur = dbapi_connection.cursor()
                    cur.execute("PRAGMA journal_mode=WAL")
                    cur.execute("PRAGMA synchronous=NORMAL")
                    cur.execute("PRAGMA busy_timeout=5000")
                    # Align with AstrBot-like tuning for better read/write concurrency
                    cur.execute("PRAGMA cache_size=20000")
                    cur.execute("PRAGMA temp_store=MEMORY")
                    cur.execute("PRAGMA mmap_size=134217728")
                    cur.execute("PRAGMA optimize")
                    cur.close()
                except Exception:
                    # Best effort; keep running even if PRAGMA fails
                    pass

            # Assign globals only after successful creation
            global engine  # noqa: PLW0603 (explicit global assignment)
            engine = eng
            sqlite_semaphore = asyncio.Semaphore(20)
            async_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

            # Create all tables declared with SQLModel
            async with engine.begin() as conn:  # type: ignore[arg-type]
                await conn.run_sync(SQLModel.metadata.create_all)

            _db_initialized = True
            logger.info("[DB] SQLite initialized successfully")
        except Exception as e:
            logger.exception(f"[DB] Initialization failed: {e}")
            raise ValueError("[DB] Initialization failed, please check environment and dependencies")


def with_session(
    func: Callable[Concatenate[Any, AsyncSession, P], Awaitable[R]]
) -> Callable[Concatenate[Any, P], Awaitable[R]]:
    """Decorator to inject AsyncSession if not explicitly provided.

    Usage:
        class MyModel(BaseIDModel):
            ...

            @classmethod
            @with_session
            async def do_something(cls, session: AsyncSession):
                ...
    """

    @wraps(func)
    async def wrapper(self, *args: P.args, **kwargs: P.kwargs):
        if not _db_initialized:
            raise RuntimeError("数据库尚未初始化，请先调用 init_database()")

        session = kwargs.pop("session", None)
        if session is not None:
            return await func(self, session, *args, **kwargs)

        async with async_maker() as new_session:  # type: ignore[operator]
            result = await func(self, new_session, *args, **kwargs)
            await new_session.commit()
            return result

    return wrapper


class BaseIDModel(SQLModel):
    """Base model with auto-increment integer primary key and helpers."""

    id: Optional[int] = Field(default=None, primary_key=True, title="id")

    @classmethod
    @with_session
    async def get_by_ids(
        cls: Type[T_BaseIDModel], session: AsyncSession, ids: List[int]
    ) -> List[T_BaseIDModel]:
        """Fetch records by a list of primary key IDs."""
        if not ids:
            return []
        stmt = select(cls).where(cls.id.in_(ids))  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    @with_session
    async def select_rows(
        cls: Type[T_BaseIDModel], session: AsyncSession, **conditions: Any
    ) -> List[T_BaseIDModel]:
        """Query with equality conditions and return all matching rows."""
        stmt = select(cls)
        if conditions:
            stmt = stmt.where(and_(*(getattr(cls, k) == v for k, v in conditions.items())))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    @with_session
    async def _batch_insert_or_update(
        cls: Type[T_BaseIDModel],
        session: AsyncSession,
        datas: List[Dict[str, Any]],
        update_keys: List[str],
        index_elements: List[str],
    ) -> None:
        """SQLite UPSERT for a batch of rows.

        Only SQLite dialect is implemented to match this project's default DB.
        """
        if not datas:
            return

        from sqlalchemy.dialects.sqlite import insert

        stmt = insert(cls).values(datas)
        update_stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_={k: stmt.excluded[k] for k in update_keys},
        )
        await session.execute(update_stmt)
