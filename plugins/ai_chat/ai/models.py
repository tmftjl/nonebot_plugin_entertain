"""AI 瀵硅瘽鏁版嵁妯″瀷锛堢Щ闄ゅソ鎰熷害锛?
浠呭寘鍚?ChatSession 琛ㄤ笌鐩稿叧渚挎嵎鏂规硶銆?"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, select

from ....db.base_models import BaseIDModel, with_session


class ChatSession(BaseIDModel, table=True):
    """AI 瀵硅瘽浼氳瘽琛?""

    __tablename__ = "ai_chat_sessions"

    # 浼氳瘽鏍囪瘑
    session_id: str = Field(unique=True, index=True, description="浼氳瘽鍞竴鏍囪瘑")
    session_type: str = Field(description="浼氳瘽绫诲瀷: group | private")
    group_id: Optional[str] = Field(default=None, description="缇ゅ彿锛堢兢鑱婁細璇濓級")
    user_id: Optional[str] = Field(default=None, description="鐢ㄦ埛 QQ锛堢鑱婁細璇濓級")

    # 閰嶇疆锛堢洿鎺ュ瓨鍌紝鏃犲閿級
    persona_name: str = Field(default="default", description="浜烘牸鍚嶇О")
    max_history: int = Field(default=20, description="鏈€澶у巻鍙茶褰曟潯鏁?)
    config_json: str = Field(default="{}", description="鍏朵粬閰嶇疆锛圝SON锛?)
    # 浼氳瘽绾у巻鍙诧細瀛樻渶杩戝璇濇潯鐩紝鍑忓皯鏌ヨ娆℃暟
    history_json: str = Field(default="[]", description="浼氳瘽鍘嗗彶 JSON")

    # 鐘舵€?    is_active: bool = Field(default=True, description="鏄惁鍚敤")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="鍒涘缓鏃堕棿")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="鏇存柊鏃堕棿")

    # ==================== 鏁版嵁搴撴搷浣滄柟娉?====================

    @classmethod
    @with_session
    async def get_by_session_id(cls, session: AsyncSession, session_id: str) -> Optional["ChatSession"]:
        """鏍规嵁 session_id 鑾峰彇浼氳瘽"""

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
        """鍒涘缓鏂颁細璇濓紙涓嶅啀鎸佷箙鍖栨渶澶ц疆鏁帮紝鎸夐厤缃姩鎬佹帶鍒讹級"""

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
        """鏇存柊浼氳瘽浜烘牸"""

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
        """鏇存柊浼氳瘽鍚敤鐘舵€?""

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

    # ==================== 浼氳瘽鍘嗗彶 JSON 缁存姢 ====================

    @classmethod
    @with_session
    async def ensure_history_column(cls, session: AsyncSession) -> None:
        """纭繚 ai_chat_sessions 琛ㄥ瓨鍦?history_json 鍒楋紙绠€鏄撹縼绉伙級"""
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
            # 蹇界暐杩佺Щ寮傚父
            pass

    @classmethod
    @with_session
    async def get_history_list(cls, session: AsyncSession, session_id: str) -> List[Dict]:
        """璇诲彇浼氳瘽 history_json 鍒椾负鍒楄〃"""
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
        """瑕嗙洊浼氳瘽 history_json"""
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
        items: List[Dict],
        max_history: int,
    ) -> List[Dict]:
        """杩藉姞鑻ュ共鍘嗗彶椤癸紝骞舵寜 max_history 瑁佸壀锛岃繑鍥炴渶鏂板垪琛?""
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
        """娓呯┖浼氳瘽 JSON 鍘嗗彶"""
        row = await cls.get_by_session_id(session=session, session_id=session_id)
        if not row:
            return False
        row.history_json = "[]"
        row.updated_at = datetime.now().isoformat()
        session.add(row)
        await session.flush()
        return True
