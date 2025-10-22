"""AI 对话核心管理器

包含：
- CacheManager: 轻量多层缓存管理
- ChatManager: AI 对话核心逻辑
"""
from __future__ import annotations

import asyncio
import json
import time
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
    """AI 对话核心管理器"""

    def __init__(self, cache: CacheManager):
        self.cache = cache
        self.client: Optional[AsyncOpenAI] = None
        # 会话锁（同一会话串行，不同会话并行）
        self._session_locks: Dict[str, asyncio.Lock] = {}
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

        # 尝试从缓存获取
        cache_key = f"session:{session_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # 从数据库查询（使用 models 的便捷方法）
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
            logger.info(f"[AI Chat] 创建新会话: {session_id}")

        # 缓存会话
        if chat_session:
            await self.cache.set(cache_key, chat_session, ttl=cfg.cache.session_ttl)

        return chat_session

    async def _get_history(self, session_id: str, max_history: int = 20) -> List[MessageHistory]:
        """获取历史消息（带缓存）"""

        cfg = get_config()

        cache_key = f"history:{session_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        history = await MessageHistory.get_recent_history(session_id=session_id, limit=max_history)

        await self.cache.set(cache_key, history, ttl=cfg.cache.history_ttl)

        return history

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
                # 1. 并发加载会话/历史/好感度
                session, history, favo = await asyncio.gather(
                    self._get_session(session_id, session_type, group_id, user_id),
                    self._get_history(session_id),
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
                    self._save_conversation(session_id, user_id, user_name, message, response, favo)
                )

                return response

            except Exception as e:
                logger.exception(f"[AI Chat] 处理消息失败: {e}")
                return "抱歉，我遇到了一点问题.."

    def _build_messages(
        self,
        session: ChatSession,
        history: List[MessageHistory],
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
            content = msg.content
            # 群聊时为用户消息添加“昵称: 内容”前缀，便于区分说话人
            if session_type == "group" and msg.role == "user" and msg.user_name:
                content = f"{msg.user_name}: {content}"
            messages.append({"role": msg.role, "content": content})

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
        personas = get_personas()
        persona = personas.get(session.persona_name, personas["default"])

        # 获取模型与温度（模型来自当前激活的 API，温度使用全局默认）
        active_api = get_active_api()
        model = active_api.model
        temperature = cfg.session.default_temperature

        # 获取启用的工具（使用全局配置）
        tools = None
        if cfg.tools.enabled and cfg.tools.builtin_tools:
            tools = get_enabled_tools(cfg.tools.builtin_tools)

        try:
            # 调用 OpenAI
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                tools=tools if tools else None,
                max_tokens=cfg.response.max_length,
            )

            # 工具调用
            if response.choices[0].message.tool_calls:
                return await self._handle_tool_calls(session, messages, response, model, temperature, tools)

            # 普通回复
            reply = response.choices[0].message.content or ""
            return (reply or "").strip()

        except Exception as e:
            logger.error(f"[AI Chat] OpenAI API 调用失败: {e}")
            return "抱歉，AI 服务暂时不可用.."

    async def _handle_tool_calls(
        self,
        session: ChatSession,
        messages: List[Dict[str, Any]],
        response: Any,
        model: str,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]],
    ) -> str:
        """处理工具调用的多轮对话"""

        cfg = get_config()
        max_iterations = cfg.tools.max_iterations

        iteration = 0
        current_response = response

        while iteration < max_iterations:
            tool_calls = current_response.choices[0].message.tool_calls
            if not tool_calls:
                break

            # 添加 AI 的工具调用消息
            messages.append(
                {
                    "role": "assistant",
                    "content": current_response.choices[0].message.content or "",
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
    ):
        """异步保存对话历史和好感度"""

        try:
            # 保存用户消息与 AI 回复（使用 models 的便捷方法）
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

            # 清除缓存
            await self.cache.delete(f"history:{session_id}")
            await self.cache.delete(f"favo:{user_id}:{session_id}")

        except Exception as e:
            logger.error(f"[AI Chat] 保存对话失败: {e}")

    # ==================== 管理接口 ====================

    async def clear_history(self, session_id: str):
        """清空会话历史"""

        # 使用 models 的便捷方法
        await MessageHistory.clear_history(session_id=session_id)

        # 清除缓存
        await self.cache.delete(f"history:{session_id}")

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

