from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from nonebot.log import logger

from .base_models import init_database
from .membership_models import GeneratedCode, Membership, write_snapshot


def _plugin_root() -> Path:
    # db/ is directly under the package root
    return Path(__file__).resolve().parents[1]


def _find_legacy_file() -> Optional[Path]:
    """Locate legacy JSON file to migrate.

    Supports the following filenames at the package root, in order:
    - group_memberships.json (preferred)
    - memberships.json (older name)
    """
    root = _plugin_root()
    candidates = [
        root / "group_memberships.json",
        root / "memberships.json",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


async def _is_db_empty() -> bool:
    # consider DB empty only if both tables have no rows
    mem_empty = len(await Membership.all()) == 0
    code_empty = len(await GeneratedCode.all()) == 0
    return mem_empty and code_empty


async def migrate_legacy_json_on_startup() -> None:
    """Migrate group_memberships.json to the current database if needed.

    - Only runs if a legacy JSON exists AND the database is empty
    - After successful migration, renames the JSON to *.migrated
    """
    # Ensure DB is ready (idempotent)
    await init_database()

    legacy = _find_legacy_file()
    if not legacy:
        return

    try:
        if not await _is_db_empty():
            logger.info(
                f"[membership] 检测到现有数据库数据，跳过迁移：{legacy.name}"
            )
            return
    except Exception:
        # If we cannot determine emptiness, skip to be safe
        logger.warning("[membership] 无法检测数据库状态，跳过旧数据迁移")
        return

    try:
        logger.info(f"[membership] 发现旧版数据文件，开始迁移：{legacy}")
        # Read JSON (best-effort, tolerate BOM/encoding via text mode)
        raw = legacy.read_text(encoding="utf-8")
        data = json.loads(raw)

        # Persist snapshot into database using model helpers
        await write_snapshot(data)

        # Rename legacy file to avoid repeated migration
        backup = legacy.with_suffix(legacy.suffix + ".migrated")
        try:
            legacy.rename(backup)
            logger.success(f"[membership] 迁移完成，已备份旧文件为：{backup.name}")
        except Exception:
            logger.success("[membership] 迁移完成（旧文件未能重命名，保留原始文件）")
    except Exception as e:
        logger.error("[membership] 旧版数据迁移失败，请检查 JSON 内容与权限")
        logger.exception(e)

