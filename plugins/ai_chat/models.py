"""AI 对话数据模型（移除好感度）

仅包含 ChatSession 表与相关便捷方法。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict
import secrets
import string
import time
import asyncio
from ...core.framework.local_cache import cache
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, select

from ...db.base_models import BaseIDModel, with_session


class ChatSession(BaseIDModel, table=True):
    """AI 对话会话表"""

    __tablename__ = "ai_chat_sessions"

    # 会话标识
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = Field(default="qq", description="消息平台")
    session_id: str = Field(unique=True, index=True, description="会话唯一标识")
    session_type: str = Field(description="会话类型: group | private")
    number: Optional[str] = Field(default=None, description="账号")
    provider_name: Optional[str] = Field(default=None, description="本会话使用的服务商名称")
    persona_name: str = Field(default="default", description="人格名称")
    max_history: int = Field(default=20, description="最大历史记录条数")
    history_json: str = Field(default="[]", description="会话历史 JSON")
    config_json: str = Field(default="{}", description="其他配置（JSON）")
    is_active: bool = Field(default=True, description="是否启用")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")

    # ==================== 数据库操作方法 ====================
    @classmethod
    @with_session
    async def get_session_id(cls, session: AsyncSession, platform: str, session_type: str, number: str) -> str:
        """根据 platform, session_type, number 获取会话"""

        stmt = select(cls).where(
            cls.platform == platform,
            cls.session_type == session_type,
            cls.number == number
        )
        result = await session.execute(stmt)
        session_obj = result.scalar_one_or_none() 
        if session_obj:
            return session_obj.session_id
        lock_key = f"ai_chat:get_session_id_lock:{platform}:{session_type}:{number}"
        token = None
        lock_timeout = 5.0  # 获取锁的最长等待时间
        retry_interval = 0.05 # 重试间隔
        start_time = time.time()
        try:
            while time.time() - start_time < lock_timeout:
                tok = secrets.token_hex(16)
                got = await cache.try_lock(lock_key, tok, ex=10)
                if got:
                    token = tok
                    break
                await asyncio.sleep(retry_interval)
            
            if not token:
                raise TimeoutError(f"在指定时间内未能获取到锁: {lock_key}")

            # 双重检查
            stmt_check = select(cls).where(
                cls.platform == platform,
                cls.session_type == session_type,
                cls.number == number
            )
            result_check = await session.execute(stmt_check)
            session_obj_check = result_check.scalar_one_or_none()
            
            if session_obj_check:
                return session_obj_check.session_id
            
            # 创建会话 (持有锁)
            alphabet = string.ascii_letters + string.digits
            session_id = ''.join(secrets.choice(alphabet) for i in range(6))
            new_session = cls(
                platform=platform,
                session_type=session_type,
                number=number,
                session_id=session_id
            )
            session.add(new_session)
            await session.flush()
            return session_id
        finally:
            if token:
                await cache.unlock(lock_key, token)
    
    @classmethod
    @with_session
    async def get_by_session_id(cls, session: AsyncSession, session_id: str) -> Optional["ChatSession"]:
        """根据 session_id 获取会话"""

        stmt = select(cls).where(cls.session_id == session_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    @with_session
    async def create_session(
        cls,
        session: AsyncSession,
        session_id: str,
        session_type: str,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
        persona_name: str = "default",
    ) -> "ChatSession":
        """创建新会话（不再持久化最大轮数，按配置动态控制）"""

        # 迁移：确保 history_json/provider_name 列存在
        try:
            await cls.ensure_history_column(session=session)
            await cls.ensure_provider_column(session=session)
        except Exception:
            pass

        chat_session = cls(
            session_id=session_id,
            session_type=session_type,
            group_id=group_id,
            user_id=user_id,
            persona_name=persona_name,
            is_active=True,
            history_json="[]",
        )
        session.add(chat_session)
        await session.flush()
        await session.refresh(chat_session)
        return chat_session

    @classmethod
    @with_session
    async def update_persona(cls, session: AsyncSession, session_id: str, persona_name: str) -> bool:
        """更新会话人格"""

        stmt = select(cls).where(cls.session_id == session_id)
        result = await session.execute(stmt)
        chat_session = result.scalar_one_or_none()

        if chat_session:
            chat_session.persona_name = persona_name
            chat_session.updated_at = datetime.now().isoformat()
            session.add(chat_session)
            await session.flush()
            return True
        return False

    @classmethod
    @with_session
    async def update_active_status(cls, session: AsyncSession, session_id: str, is_active: bool) -> bool:
        """更新会话启用状态"""

        stmt = select(cls).where(cls.session_id == session_id)
        result = await session.execute(stmt)
        chat_session = result.scalar_one_or_none()

        if chat_session:
            chat_session.is_active = is_active
            chat_session.updated_at = datetime.now().isoformat()
            session.add(chat_session)
            await session.flush()
            return True
        return False

    # ==================== 会话历史 JSON 维护 ====================

    @classmethod
    @with_session
    async def ensure_history_column(cls, session: AsyncSession) -> None:
        """确保 ai_chat_sessions 表存在 history_json 列（简易迁移）"""
        from sqlalchemy import text
        try:
            rs = await session.execute(text("PRAGMA table_info(ai_chat_sessions)"))
            cols = [row[1] for row in rs.fetchall()]
            if "history_json" not in cols:
                await session.execute(
                    text('ALTER TABLE ai_chat_sessions ADD COLUMN history_json TEXT DEFAULT "[]"')
                )
                await session.flush()
        except Exception:
            # 忽略迁移异常
            pass

    @classmethod
    @with_session
    async def ensure_provider_column(cls, session: AsyncSession) -> None:
        """确保 ai_chat_sessions 表存在 provider_name 列（简易迁移）"""
        from sqlalchemy import text
        try:
            rs = await session.execute(text("PRAGMA table_info(ai_chat_sessions)"))
            cols = [row[1] for row in rs.fetchall()]
            if "provider_name" not in cols:
                await session.execute(
                    text('ALTER TABLE ai_chat_sessions ADD COLUMN provider_name TEXT')
                )
                await session.flush()
        except Exception:
            # 忽略迁移异常
            pass

    @classmethod
    @with_session
    async def get_history_list(cls, session: AsyncSession, session_id: str) -> List[Dict]:
        """读取会话 history_json 列为列表"""
        row = await cls.get_by_session_id(session=session, session_id=session_id)
        if not row:
            return []
        try:
            import json
            data = json.loads(row.history_json or "[]")
            return data if isinstance(data, list) else []
        except Exception:
            return []

    @classmethod
    @with_session
    async def set_history_list(
        cls, session: AsyncSession, session_id: str, history: List[Dict]
    ) -> bool:
        """覆盖会话 history_json"""
        row = await cls.get_by_session_id(session=session, session_id=session_id)
        if not row:
            return False
        try:
            import json
            row.history_json = json.dumps(history, ensure_ascii=False)
            row.updated_at = datetime.now().isoformat()
            session.add(row)
            await session.flush()
            return True
        except Exception:
            return False

    # ==================== 服务商字段维护 ====================

    @classmethod
    @with_session
    async def update_provider(
        cls, session: AsyncSession, session_id: str, provider_name: Optional[str]
    ) -> bool:
        """更新会话的服务商名称（None 表示使用默认）"""
        try:
            await cls.ensure_provider_column(session=session)
        except Exception:
            pass
        row = await cls.get_by_session_id(session=session, session_id=session_id)
        if not row:
            return False
        row.provider_name = (provider_name or None)
        row.updated_at = datetime.now().isoformat()
        session.add(row)
        await session.flush()
        return True

    @classmethod
    @with_session
    async def update_provider_for_all(
        cls, session: AsyncSession, provider_name: Optional[str]
    ) -> int:
        """将所有会话的服务商设置为指定名称。返回影响的行数。"""
        try:
            await cls.ensure_provider_column(session=session)
        except Exception:
            pass
        from sqlalchemy import update as sa_update
        try:
            await session.execute(
                sa_update(cls).values(provider_name=(provider_name or None), updated_at=datetime.now().isoformat())
            )
            await session.flush()
            from sqlalchemy import select as sa_select, func
            cnt = (await session.execute(sa_select(func.count()).select_from(cls))).scalar_one()
            return int(cnt)
        except Exception:
            rows = await cls.select_rows()
            changed = 0
            for r in rows:
                try:
                    r.provider_name = (provider_name or None)
                    r.updated_at = datetime.now().isoformat()
                    session.add(r)
                    changed += 1
                except Exception:
                    continue
            await session.flush()
            return changed
        
    @classmethod
    @with_session
    async def append_history_items(
        cls,
        session: AsyncSession,
        session_id: str,
        items: List[Dict],
        max_history: int,
    ) -> List[Dict]:
        """追加若干历史项，并按 max_history 裁剪，返回最新列表"""
        row = await cls.get_by_session_id(session=session, session_id=session_id)
        if not row:
            return []
        try:
            import json
            try:
                lst = json.loads(row.history_json or "[]")
                if not isinstance(lst, list):
                    lst = []
            except Exception:
                lst = []
            lst.extend(items)
            row.history_json = json.dumps(lst, ensure_ascii=False)
            row.updated_at = datetime.now().isoformat()
            row.max_history = max_history
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return lst
        except Exception:
            return []

    @classmethod
    @with_session
    async def clear_history_json(cls, session: AsyncSession, session_id: str) -> bool:
        """清空会话 JSON 历史"""
        row = await cls.get_by_session_id(session=session, session_id=session_id)
        if not row:
            return False
        row.history_json = "[]"
        row.updated_at = datetime.now().isoformat()
        session.add(row)
        await session.flush()
        return True

    # ==================== 会话配置 JSON 维护 ====================

    @classmethod
    @with_session
    async def get_config_json(cls, session: AsyncSession, session_id: str) -> Dict:
        row = await cls.get_by_session_id(session=session, session_id=session_id)
        if not row:
            return {}
        try:
            import json
            data = json.loads(row.config_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @classmethod
    @with_session
    async def set_config_json(cls, session: AsyncSession, session_id: str, data: Dict) -> bool:
        row = await cls.get_by_session_id(session=session, session_id=session_id)
        if not row:
            return False
        try:
            import json
            row.config_json = json.dumps(data, ensure_ascii=False)
            row.updated_at = datetime.now().isoformat()
            session.add(row)
            await session.flush()
            return True
        except Exception:
            return False
