"""AI 对话数据模型

包含 3 个核心表：
- ChatSession: 会话信息（含会话内历史 JSON）
- MessageHistory: 对话历史明细
- UserFavorability: 用户好感度

所有数据库操作均提供便捷的类方法。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, select, and_, desc

from ...db.base_models import BaseIDModel, with_session


class ChatSession(BaseIDModel, table=True):
    """AI 对话会话表"""

    __tablename__ = "ai_chat_sessions"

    # 会话标识
    session_id: str = Field(unique=True, index=True, description="会话唯一标识")
    session_type: str = Field(description="会话类型: group | private")
    group_id: Optional[str] = Field(default=None, description="群号（群聊会话）")
    user_id: Optional[str] = Field(default=None, description="用户 QQ（私聊会话）")

    # 配置（直接存储，无外键）
    persona_name: str = Field(default="default", description="人格名称")
    max_history: int = Field(default=20, description="最大历史记录条数")
    config_json: str = Field(default="{}", description="其他配置（JSON）")
    # 会话级历史：存最近对话条目，减少查询次数
    history_json: str = Field(default="[]", description="会话历史 JSON")

    # 状态
    is_active: bool = Field(default=True, description="是否启用")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")

    # ==================== 数据库操作方法 ====================

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
        max_history: int = 20,
    ) -> "ChatSession":
        """创建新会话"""

        chat_session = cls(
            session_id=session_id,
            session_type=session_type,
            group_id=group_id,
            user_id=user_id,
            persona_name=persona_name,
            max_history=max_history,
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
        """确保 ai_chat_sessions 表存在 history_json 列（简易迁移）。"""
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
    async def get_history_list(cls, session: AsyncSession, session_id: str) -> list[dict]:
        """读取会话 history_json 列为列表。"""
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
        cls, session: AsyncSession, session_id: str, history: list[dict]
    ) -> bool:
        """覆盖会话 history_json。"""
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

    @classmethod
    @with_session
    async def append_history_items(
        cls,
        session: AsyncSession,
        session_id: str,
        items: list[dict],
        max_history: int,
    ) -> list[dict]:
        """追加若干历史项，并按 max_history 裁剪，返回最新列表。"""
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
            if max_history > 0 and len(lst) > max_history:
                lst = lst[-max_history:]
            row.history_json = json.dumps(lst, ensure_ascii=False)
            row.updated_at = datetime.now().isoformat()
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return lst
        except Exception:
            return []

    @classmethod
    @with_session
    async def clear_history_json(cls, session: AsyncSession, session_id: str) -> bool:
        """清空会话 JSON 历史。"""
        row = await cls.get_by_session_id(session=session, session_id=session_id)
        if not row:
            return False
        row.history_json = "[]"
        row.updated_at = datetime.now().isoformat()
        session.add(row)
        await session.flush()
        return True


class MessageHistory(BaseIDModel, table=True):
    """对话历史记录表（明细归档，不参与会话读取性能路径）"""

    __tablename__ = "ai_message_history"

    session_id: str = Field(index=True, description="会话 ID")
    user_id: Optional[str] = Field(default=None, description="用户 QQ")
    user_name: Optional[str] = Field(default=None, description="用户昵称（群聊时有值）")
    role: str = Field(description="消息角色：user | assistant | tool | system")
    content: str = Field(description="消息内容")
    tool_calls: Optional[str] = Field(default=None, description="工具调用原始 JSON")
    tool_call_id: Optional[str] = Field(default=None, description="工具调用 ID")
    tokens: Optional[int] = Field(default=None, description="消耗的 tokens （可选）")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")

    @classmethod
    @with_session
    async def get_recent_history(
        cls, session: AsyncSession, session_id: str, limit: int = 20
    ) -> list["MessageHistory"]:
        """获取最近的历史消息（按时间升序返回）"""

        stmt = (
            select(cls)
            .where(cls.session_id == session_id)
            .order_by(desc(cls.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = list(reversed(result.scalars().all()))
        return rows

    @classmethod
    @with_session
    async def add_message(
        cls,
        session: AsyncSession,
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        tool_calls: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        tokens: Optional[int] = None,
    ) -> "MessageHistory":
        """添加一条消息"""

        message = cls(
            session_id=session_id,
            user_id=user_id,
            user_name=user_name,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tokens=tokens,
        )
        session.add(message)
        await session.flush()
        await session.refresh(message)
        return message

    @classmethod
    @with_session
    async def clear_history(cls, session: AsyncSession, session_id: str) -> int:
        """清空会话历史（明细表），返回删除的消息数量"""

        stmt = select(cls).where(cls.session_id == session_id)
        result = await session.execute(stmt)
        messages = result.scalars().all()

        count = 0
        for msg in messages:
            await session.delete(msg)
            count += 1

        await session.flush()
        return count


class UserFavorability(BaseIDModel, table=True):
    """用户好感度表"""

    __tablename__ = "ai_user_favorability"

    user_id: str = Field(index=True, description="用户 QQ")
    session_id: str = Field(index=True, description="会话 ID")

    # 好感度数据
    favorability: int = Field(default=50, description="好感度（0-100）")
    interaction_count: int = Field(default=0, description="互动次数")

    # 情感统计
    positive_count: int = Field(default=0, description="正面情感次数")
    negative_count: int = Field(default=0, description="负面情感次数")

    # 时间
    last_interaction: str = Field(default_factory=lambda: datetime.now().isoformat(), description="最后互动时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")

    # ==================== 数据库操作方法 ====================

    @classmethod
    @with_session
    async def get_favorability(
        cls, session: AsyncSession, user_id: str, session_id: str
    ) -> Optional["UserFavorability"]:
        """获取用户好感度"""

        stmt = select(cls).where(and_(cls.user_id == user_id, cls.session_id == session_id))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    @with_session
    async def create_favorability(
        cls, session: AsyncSession, user_id: str, session_id: str, initial_favorability: int = 50
    ) -> "UserFavorability":
        """创建用户好感度记录"""

        favo = cls(user_id=user_id, session_id=session_id, favorability=initial_favorability, interaction_count=0)
        session.add(favo)
        await session.flush()
        await session.refresh(favo)
        return favo

    @classmethod
    @with_session
    async def update_favorability(
        cls,
        session: AsyncSession,
        user_id: str,
        session_id: str,
        delta: int = 1,
        positive: bool = False,
        negative: bool = False,
    ) -> Optional["UserFavorability"]:
        """更新用户好感度"""

        stmt = select(cls).where(and_(cls.user_id == user_id, cls.session_id == session_id))
        result = await session.execute(stmt)
        favo = result.scalar_one_or_none()

        if favo:
            favo.interaction_count += 1
            favo.favorability = max(0, min(100, favo.favorability + delta))

            if positive:
                favo.positive_count += 1
            if negative:
                favo.negative_count += 1

            now = datetime.now().isoformat()
            favo.last_interaction = now
            favo.updated_at = now

            session.add(favo)
            await session.flush()
            await session.refresh(favo)

        return favo

    @classmethod
    @with_session
    async def set_favorability(
        cls, session: AsyncSession, user_id: str, session_id: str, favorability: int
    ) -> Optional["UserFavorability"]:
        """直接设置用户好感度"""

        stmt = select(cls).where(and_(cls.user_id == user_id, cls.session_id == session_id))
        result = await session.execute(stmt)
        favo = result.scalar_one_or_none()

        if favo:
            favo.favorability = max(0, min(100, favorability))
            favo.updated_at = datetime.now().isoformat()
            session.add(favo)
            await session.flush()
            await session.refresh(favo)

        return favo

