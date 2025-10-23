"""AI 对话核心管理

包含：
- CacheManager: 轻量多层缓存管理
- ChatManager: AI 对话核心逻辑
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from nonebot.log import logger
from openai import AsyncOpenAI

from .config import get_config, get_personas, PersonaConfig, get_active_api
from .models import ChatSession, MessageHistory, UserFavorability
from .tools import get_enabled_tools, execute_tool


# ==================== CacheManager ====================


class CacheManager:
    """多层缓存管理（L1 内存缓存 + TTL）"""

    def __init__(self):
        # L1 缓存: {key: (value, expire_at)}
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""

        async with self._lock:
            if key in self._cache:
                value, expire_at = self._cache[key]
                # TTL=0 表示永久缓存
                if expire_at == 0 or time.time() < expire_at:
                    return value
                # 过期，删除
                del self._cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: int = 0):
        """设置缓存

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），0 表示永久
        """

        expire_at = time.time() + ttl if ttl > 0 else 0
        async with self._lock:
            self._cache[key] = (value, expire_at)

    async def delete(self, key: str):
        """删除缓存"""

        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self):
        """清空所有缓存"""

        async with self._lock:
            self._cache.clear()

    async def clear_pattern(self, pattern: str):
        """按键名包含关系清理缓存（简单模式）"""

        async with self._lock:
            keys_to_delete = [k for k in list(self._cache.keys()) if pattern in k]
            for k in keys_to_delete:
                self._cache.pop(k, None)


# ==================== ChatManager ====================


class ChatManager:
    """AI 对话核心管理"""

    def __init__(self, cache: CacheManager):
        self.cache = cache
        self.client: Optional[AsyncOpenAI] = None
        # 会话锁（同一会话串行，不同会话并行）
        self._session_locks: Dict[str, asyncio.Lock] = {}
        # 历史 JSON 持久化锁（避免异步写入竞态）
        self._history_locks: Dict[str, asyncio.Lock] = {}
        # 简易迁移检查标志
        self._schema_checked: bool = False
        # 初始化客户端
        self.reset_client()

    def reset_client(self) -> None:
        """根据当前配置重建 OpenAI 客户端"""

        _ = get_config()  # 预热配置
        try:
            active_api = get_active_api()
            if not active_api.api_key:
                self.client = None
                logger.warning("[AI Chat] OpenAI 未配置 API Key，已禁用对话能力")
                return
            self.client = AsyncOpenAI(
                api_key=active_api.api_key,
                base_url=active_api.base_url,
                timeout=active_api.timeout,
            )
            logger.debug("[AI Chat] OpenAI 客户端已初始化")
        except Exception as e:
            self.client = None
            logger.error(f"[AI Chat] OpenAI 客户端初始化失败: {e}")

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """获取会话锁"""

        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    # ==================== 数据加载 ====================

    async def _get_session(
        self,
        session_id: str,
        session_type: str,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ChatSession:
        """获取或创建会话（带缓存）"""

        cfg = get_config()

        # 缓存
        cache_key = f"session:{session_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # 确保会话表包含 history_json 列（一次性检查）
        if not self._schema_checked:
            try:
                await ChatSession.ensure_history_column()
            finally:
                self._schema_checked = True

        # DB 查询
        chat_session = await ChatSession.get_by_session_id(session_id=session_id)

        # 自动创建会话
        if not chat_session and cfg.session.auto_create:
            chat_session = await ChatSession.create_session(
                session_id=session_id,
                session_type=session_type,
                group_id=group_id,
                user_id=user_id,
                persona_name="default",
                max_history=cfg.session.default_max_history,
            )
            logger.info(f"[AI Chat] 创建新会话 {session_id}")

        # 缓存会话
        if chat_session:
            await self.cache.set(cache_key, chat_session, ttl=cfg.cache.session_ttl)

        return chat_session

    async def _get_history(
        self,
        session_id: str,
        session: Optional[ChatSession] = None,
        max_history: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """获取历史消息（优先读会话 JSON，带缓存）。返回元素为 dict。"""

        cfg = get_config()
        cache_key = f"history:{session_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # 优先从会话 JSON 读取
        if session is None:
            session = await self._get_session(session_id, session_type="group")
        history_list: List[Dict[str, Any]] = []
        try:
            history_list = json.loads(session.history_json or "[]") if session and session.history_json else []
            if not isinstance(history_list, list):
                history_list = []
        except Exception:
            history_list = []

        # 兼容：若 JSON 为空，回退到明细表最近记录，并回填 JSON
        if not history_list:
            limit = max_history or (session.max_history if session else 20)
            rows = await MessageHistory.get_recent_history(session_id=session_id, limit=limit)
            history_list = [
                {
                    "role": r.role,
                    "content": r.content,
                    "user_name": r.user_name,
                    "created_at": r.created_at,
                }
                for r in rows
            ]
            # 回填一次（忽略异常）
            try:
                await ChatSession.set_history_list(session_id=session_id, history=history_list)
                if session:
                    session.history_json = json.dumps(history_list, ensure_ascii=False)
                    await self.cache.set(f"session:{session_id}", session, ttl=cfg.cache.session_ttl)
            except Exception:
                pass

        await self.cache.set(cache_key, history_list, ttl=cfg.cache.history_ttl)
        return history_list

    async def _get_favorability(self, user_id: str, session_id: str) -> UserFavorability:
        """获取或创建用户好感度（带缓存）"""

        cfg = get_config()

        cache_key = f"favo:{user_id}:{session_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        favo = await UserFavorability.get_favorability(user_id=user_id, session_id=session_id)

        if not favo:
            favo = await UserFavorability.create_favorability(
                user_id=user_id, session_id=session_id, initial_favorability=50
            )

        await self.cache.set(cache_key, favo, ttl=cfg.cache.favorability_ttl)

        return favo

    # ==================== 核心处理 ====================

    async def process_message(
        self,
        session_id: str,
        user_id: str,
        user_name: str,
        message: str,
        session_type: str = "group",
        group_id: Optional[str] = None,
    ) -> str:
        """处理用户消息（串行同会话，支持工具调用）"""

        # OpenAI 未配置
        if not self.client:
            return "AI 未配置或暂不可用"

        # 会话锁
        lock = self._get_session_lock(session_id)
        async with lock:
            try:
                # 1. 先取会话对象，再并发读取历史与好感度
                session = await self._get_session(session_id, session_type, group_id, user_id)
                history, favo = await asyncio.gather(
                    self._get_history(session_id, session=session),
                    self._get_favorability(user_id, session_id),
                )

                # 会话未启用
                if not session or not session.is_active:
                    return ""

                # 2. 构建 AI 消息
                messages = self._build_messages(session, history, favo, message, user_name, session_type)

                # 3. 调用 AI
                response = await self._call_ai(session, messages, favo)

                # 4. 异步持久化（不阻塞回复）
                asyncio.create_task(
                    self._save_conversation(session_id, user_id, user_name, message, response, favo, session.max_history)
                )

                return response

            except Exception as e:
                logger.exception(f"[AI Chat] 处理消息失败: {e}")
                return "抱歉，我遇到了一点问题。"

    def _build_messages(
        self,
        session: ChatSession,
        history: List[Dict[str, Any]],
        favo: UserFavorability,
        message: str,
        user_name: str,
        session_type: str,
    ) -> List[Dict[str, Any]]:
        """构建发送给 AI 的消息列表"""

        messages: List[Dict[str, Any]] = []

        # 1) System Prompt（含好感度修饰）
        personas = get_personas()
        persona = personas.get(session.persona_name, personas["default"])
        system_prompt = persona.system_prompt

        # 添加好感度修饰语
        favo_modifier = self._get_favo_modifier(favo.favorability)
        if favo_modifier:
            system_prompt += f"\n\n{favo_modifier}"

        messages.append({"role": "system", "content": system_prompt})

        # 2) 历史消息
        for msg in history:
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            uname = msg.get("user_name") if isinstance(msg, dict) else getattr(msg, "user_name", None)
            # 群聊时为用户消息添加“昵称: 内容”前缀，便于区分说话人
            if session_type == "group" and role == "user" and uname:
                content = f"{uname}: {content}"
            messages.append({"role": role, "content": content})

        # 3) 当前用户消息
        current_content = f"{user_name}: {message}" if session_type == "group" else message
        messages.append({"role": "user", "content": current_content})

        return messages

    def _get_favo_modifier(self, favorability: int) -> str:
        """根据好感度生成 system prompt 修饰语"""

        if favorability >= 80:
            return "注意：这位用户对你的好感度很高，你可以更加亲密和主动。"
        elif favorability >= 60:
            return "注意：这位用户对你比较友好，保持热情。"
        elif favorability <= 20:
            return "注意：这位用户对你态度冷淡，保持礼貌但不过度热情。"
        return ""

    async def _call_ai(self, session: ChatSession, messages: List[Dict[str, Any]], favo: UserFavorability) -> str:
        """调用 OpenAI 聊天接口，包含工具调用处理"""

        if not self.client:
            return "AI 未配置或暂不可用"

        cfg = get_config()
        persona: PersonaConfig = get_personas().get(session.persona_name, get_personas()["default"])
        tools = get_enabled_tools()

        model = get_active_api().model or "gpt-4o-mini"
        temperature = cfg.session.default_temperature

        # 初次调用
        current_response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            tools=tools,
        )

        # 处理可能的工具调用（简单循环）
        max_iterations = 2
        iteration = 0
        while iteration < max_iterations:
            choice = current_response.choices[0]
            tool_calls = choice.message.tool_calls or []

            # 无工具调用则直接返回
            if not tool_calls:
                break

            # 将 AI 的工具调用消息加入 messages
            messages.append(
                {
                    "role": "assistant",
                    "content": choice.message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            # 执行工具调用
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    tool_args = {}

                # 执行工具
                tool_result = await execute_tool(tool_name, tool_args)

                # 添加工具结果消息
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})

            # 再次调用 AI 继续对话
            current_response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                tools=tools,
            )

            iteration += 1

        # 返回最终回复
        return current_response.choices[0].message.content or ""

    async def _save_conversation(
        self,
        session_id: str,
        user_id: str,
        user_name: str,
        message: str,
        response: str,
        favo: UserFavorability,
        max_history: int,
    ):
        """异步保存对话历史和好感度"""

        try:
            # 保存用户消息和 AI 回复（明细表）
            await MessageHistory.add_message(
                session_id=session_id,
                user_id=user_id,
                user_name=user_name,
                role="user",
                content=message,
            )

            await MessageHistory.add_message(
                session_id=session_id,
                role="assistant",
                content=response,
            )

            # 更新好感度
            cfg = get_config()
            if cfg.favorability.enabled:
                await UserFavorability.update_favorability(
                    user_id=user_id,
                    session_id=session_id,
                    delta=cfg.favorability.per_message_delta,
                )

            # 维护会话 JSON 历史（串行避免竞态）
            lock = self._history_locks.setdefault(session_id, asyncio.Lock())
            async with lock:
                now = datetime.now().isoformat()
                items = [
                    {"role": "user", "content": message, "user_name": user_name, "created_at": now},
                    {"role": "assistant", "content": response, "created_at": now},
                ]
                history_list = await ChatSession.append_history_items(
                    session_id=session_id, items=items, max_history=max_history
                )
                # 更新缓存：history + session
                await self.cache.set(f"history:{session_id}", history_list, ttl=cfg.cache.history_ttl)
                session_row = await ChatSession.get_by_session_id(session_id=session_id)
                if session_row:
                    await self.cache.set(f"session:{session_id}", session_row, ttl=cfg.cache.session_ttl)

            # 清除好感度缓存（其余已覆盖）
            await self.cache.delete(f"favo:{user_id}:{session_id}")

        except Exception as e:
            logger.error(f"[AI Chat] 保存对话失败: {e}")

    # ==================== 管理接口 ====================

    async def clear_history(self, session_id: str):
        """清空会话历史"""

        # 清空明细与会话 JSON
        await MessageHistory.clear_history(session_id=session_id)
        await ChatSession.clear_history_json(session_id=session_id)

        # 清除缓存
        await self.cache.delete(f"history:{session_id}")
        await self.cache.delete(f"session:{session_id}")

        logger.info(f"[AI Chat] 清空会话历史: {session_id}")

    async def set_persona(self, session_id: str, persona_name: str):
        """切换会话人格"""

        updated = await ChatSession.update_persona(session_id=session_id, persona_name=persona_name)
        if updated:
            # 清除缓存
            await self.cache.delete(f"session:{session_id}")
            logger.info(f"[AI Chat] 切换人格: {session_id} -> {persona_name}")

    async def set_session_active(self, session_id: str, is_active: bool):
        """设置会话启用状态"""

        updated = await ChatSession.update_active_status(session_id=session_id, is_active=is_active)
        if updated:
            # 清除缓存
            await self.cache.delete(f"session:{session_id}")

    async def get_session_info(self, session_id: str) -> Optional[ChatSession]:
        """获取会话信息"""

        return await ChatSession.get_by_session_id(session_id=session_id)


# ==================== 全局实例 ====================


# 全局缓存与对话管理器
cache_manager = CacheManager()
chat_manager = ChatManager(cache_manager)
