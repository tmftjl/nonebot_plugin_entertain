"""AI 对话核心管理（去除好感度，加入前后钩子）

- 去除了所有好感度逻辑与持久化
- 新增 pre/post 钩子，便于在调用 AI 前后自定义修改
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict

from nonebot.log import logger
from openai import AsyncOpenAI

from .config import get_config, get_personas, get_active_api
from .models import ChatSession
from .tools import get_enabled_tools, execute_tool
from .hooks import run_pre_ai_hooks, run_post_ai_hooks


# ==================== Chatroom Memory (in-memory) ====================


class ChatroomMemory:
    """聊天室历史（轻量内存环形缓冲）。

    仅用于群聊上下文提示，不做持久化。
    - 记录格式：[昵称/HH:MM:SS]: 文本
    - get_history_str() 返回以 "\n---\n" 连接的历史串
    """

    def __init__(self, max_cnt: int = 200):
        self.max_cnt = max_cnt
        self.session_chats: Dict[str, List[str]] = defaultdict(list)

    def record_user(self, session_id: str, user_name: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append(session_id, f"[{user_name}/{ts}]: {text}")

    def record_bot(self, session_id: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append(session_id, f"[You/{ts}]: {text}")

    def get_history_str(self, session_id: str) -> str:
        chats = self.session_chats.get(session_id, [])
        return "\n---\n".join(chats)

    def clear(self, session_id: str) -> int:
        cnt = len(self.session_chats.get(session_id, []))
        if session_id in self.session_chats:
            del self.session_chats[session_id]
        return cnt

    def _append(self, session_id: str, line: str) -> None:
        arr = self.session_chats[session_id]
        arr.append(line)
        if len(arr) > self.max_cnt:
            arr.pop(0)


# ==================== ChatManager ====================


class ChatManager:
    """AI 对话核心管理（去除好感度，加入前后钩子）"""

    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        # 会话锁（同一会话串行，不同会话并行）
        self._session_locks: Dict[str, asyncio.Lock] = {}
        # 历史 JSON 持久化锁（避免异步写入竞态）
        self._history_locks: Dict[str, asyncio.Lock] = {}
        # 简易迁移检查标记
        self._schema_checked: bool = False
        # 初始化客户端
        self.reset_client()
        # 聊天室历史（内存）
        try:
            self.ltm = ChatroomMemory(max_cnt=max(1, int(get_config().session.chatroom_history_max_lines)))
        except Exception:
            self.ltm = ChatroomMemory(max_cnt=200)

    def reset_client(self) -> None:
        """根据当前配置重建 OpenAI 客户端"""

        cfg = get_config()  # 预热配置
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
            # 热更新聊天室历史容量
            try:
                if hasattr(self, "ltm") and self.ltm:
                    self.ltm.max_cnt = max(1, int(cfg.session.chatroom_history_max_lines))
            except Exception:
                pass
        except Exception as e:
            self.client = None
            logger.error(f"[AI Chat] OpenAI 客户端初始化失败: {e}")

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
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
        """获取或创建会话（直接查库）"""

        # 仅在首次调用时做一次列检查
        if not self._schema_checked:
            try:
                await ChatSession.ensure_history_column()
            finally:
                self._schema_checked = True

        chat_session = await ChatSession.get_by_session_id(session_id=session_id)

        # 自动创建会话
        cfg = get_config()
        if not chat_session :
            chat_session = await ChatSession.create_session(
                session_id=session_id,
                session_type=session_type,
                group_id=group_id,
                user_id=user_id,
                persona_name="default",
                max_history=max(2, 2 * int(cfg.session.max_rounds)),
            )
            logger.info(f"[AI Chat] 创建新会话 {session_id}")

        return chat_session

    async def _get_history(
        self,
        session_id: str,
        session: Optional[ChatSession] = None,
    ) -> List[Dict[str, Any]]:
        """获取历史消息（优先读会话 JSON）。返回元素为 dict"""

        if session is None:
            session = await self._get_session(session_id, session_type="group")

        history_list: List[Dict[str, Any]] = []
        try:
            history_list = json.loads(session.history_json or "[]") if session and session.history_json else []
            if not isinstance(history_list, list):
                history_list = []
        except Exception:
            history_list = []

        return history_list

    def _trim_history_rounds(self, history: List[Dict[str, Any]], max_pairs: int) -> List[Dict[str, Any]]:
        """按轮(user+assistant)裁剪历史，确保从第一个 user 开始"""

        try:
            if not history:
                return []
            if max_pairs <= 0:
                return []
            keep = max_pairs * 2
            trimmed = history[-keep:] if len(history) > keep else list(history)
            # 定位第一个 user，保证对齐
            idx = next((i for i, m in enumerate(trimmed) if (isinstance(m, dict) and m.get("role") == "user") or getattr(m, "role", None) == "user"), 0)
            if idx > 0:
                trimmed = trimmed[idx:]
            # 再次截断到偶数长度
            if len(trimmed) > keep:
                trimmed = trimmed[-keep:]
            return trimmed
        except Exception:
            return history

    # ==================== 核心处理 ====================

    async def process_message(
        self,
        session_id: str,
        user_id: str,
        user_name: str,
        message: str,
        session_type: str = "group",
        group_id: Optional[str] = None,
        *,
        active_reply: bool = False,
        active_reply_suffix: Optional[str] = None,
    ) -> str:
        """处理用户消息（串行同会话，支持工具调用与前后钩子）"""

        if not self.client:
            return "AI 未配置或暂不可用"

        lock = self._get_session_lock(session_id)
        async with lock:
            try:
                # 1. 会话与历史
                session = await self._get_session(session_id, session_type, group_id, user_id)
                history = await self._get_history(session_id, session=session)

                if not session or not session.is_active:
                    return ""

                # 2. 裁剪历史（按轮）
                try:
                    pairs_limit = max(1, int(get_config().session.max_rounds))
                    history = self._trim_history_rounds(history, pairs_limit)
                except Exception:
                    pass

                # 2.1 群聊记录“聊天室历史”（内存）
                chatroom_history = ""
                if session_type == "group":
                    self.ltm.record_user(session_id, user_name, message)
                    chatroom_history = self.ltm.get_history_str(session_id)

                if active_reply:
                    history = []

                # 3. 构建消息列表
                messages = self._build_messages(
                    session,
                    history,
                    message,
                    user_name,
                    session_type,
                    chatroom_history=chatroom_history,
                    active_reply=active_reply,
                    active_reply_suffix=active_reply_suffix,
                )

                # 3.1 默认参数（可被 pre 钩子覆盖）
                cfg = get_config()
                default_tools = (
                    get_enabled_tools(cfg.tools.builtin_tools)
                    if getattr(cfg, "tools", None) and cfg.tools.enabled
                    else None
                )
                default_model = get_active_api().model or "gpt-4o-mini"
                default_temperature = cfg.session.default_temperature

                overrides = await run_pre_ai_hooks(
                    session=session,
                    messages=messages,
                    model=default_model,
                    temperature=default_temperature,
                    tools=default_tools,
                    session_type=session_type,
                    group_id=group_id,
                    user_id=user_id,
                    user_name=user_name,
                    request_text=message,
                )

                model = overrides.get("model", default_model)
                temperature = overrides.get("temperature", default_temperature)
                tools = overrides.get("tools", default_tools)
                messages = overrides.get("messages", messages)

                # 4. 调用 AI
                response = await self._call_ai(
                    session,
                    messages,
                    model=model,
                    temperature=temperature,
                    tools=tools,
                )

                # 4.1 post 钩子（允许二次处理）
                response = await run_post_ai_hooks(
                    session=session,
                    messages=messages,
                    response=response,
                    model=model,
                    temperature=temperature,
                    tools=tools,
                    session_type=session_type,
                    group_id=group_id,
                    user_id=user_id,
                    user_name=user_name,
                    request_text=message,
                )

                # 5. 异步持久化（不阻塞回复）
                max_msgs = max(0, 2 * int(get_config().session.max_rounds))
                asyncio.create_task(
                    self._save_conversation(session_id, user_name, message, response, max_msgs)
                )

                # 6. 记录机器人回复到“聊天室历史”
                if session_type == "group" and response:
                    try:
                        self.ltm.record_bot(session_id, response)
                    except Exception:
                        pass

                return response

            except Exception as e:
                logger.exception(f"[AI Chat] 处理消息失败: {e}")
                return "抱歉，我遇到了一点问题。"

    def _build_messages(
        self,
        session: ChatSession,
        history: List[Dict[str, Any]],
        message: str,
        user_name: str,
        session_type: str,
        *,
        chatroom_history: str = "",
        active_reply: bool = False,
        active_reply_suffix: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """构建发送给 AI 的消息列表"""

        messages: List[Dict[str, Any]] = []

        # 1) System Prompt
        personas = get_personas()
        persona = personas.get(session.persona_name, personas["default"])
        system_prompt = persona.system_prompt

        # 聊天室历史（注入到 system）
        if active_reply:
            if chatroom_history:
                system_prompt += (
                    "\nYou are now in a chatroom. The chat history is as follows:\n" + chatroom_history
                )

        messages.append({"role": "system", "content": system_prompt})
        _active_reply = bool(active_reply)
        _ar_suffix = (active_reply_suffix or "")

        # 2) 历史消息
        for msg in history:
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            uname = msg.get("user_name") if isinstance(msg, dict) else getattr(msg, "user_name", None)
            # 群聊时为用户消息添加“昵称: 内容”前缀
            if session_type == "group" and role == "user" and uname:
                content = f"{uname}: {content}"
            messages.append({"role": role, "content": content})

        # 3) 当前用户消息
        current_content = f"{user_name}: {message}" if session_type == "group" else message
        messages.append({"role": "user", "content": current_content})
        if _active_reply and _ar_suffix:
            try:
                suffix_use = _ar_suffix.replace("{message}", message).replace("{prompt}", message)
            except Exception:
                suffix_use = _ar_suffix
            messages.append({"role": "user", "content": suffix_use})

        return messages

    async def _call_ai(
        self,
        session: ChatSession,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """调用 OpenAI 聊天接口，包含工具调用处理"""

        if not self.client:
            return "AI 未配置或暂不可用"

        cfg = get_config()
        if tools is None:
            tools = (
                get_enabled_tools(cfg.tools.builtin_tools)
                if getattr(cfg, "tools", None) and cfg.tools.enabled
                else None
            )
        if model is None:
            model = get_active_api().model or "gpt-4o-mini"
        if temperature is None:
            temperature = cfg.session.default_temperature

        # 初次调用
        current_response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            tools=tools,
        )

        # 处理可能的工具调用（简单循环）
        max_iterations = (cfg.tools.max_iterations if getattr(cfg, "tools", None) else 2)
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
        user_name: str,
        message: str,
        response: str,
        max_history: int,
    ) -> None:
        """异步保存对话历史（仅维护会话 JSON 历史）"""

        try:
            # 维护会话 JSON 历史（串行避免竞态）
            lock = self._history_locks.setdefault(session_id, asyncio.Lock())
            async with lock:
                now = datetime.now().isoformat()
                items = [
                    {"role": "user", "content": message, "user_name": user_name, "created_at": now},
                    {"role": "assistant", "content": response, "created_at": now},
                ]
                _ = await ChatSession.append_history_items(
                    session_id=session_id, items=items, max_history=max_history
                )
        except Exception as e:
            logger.error(f"[AI Chat] 保存对话失败: {e}")

    # ==================== 管理接口 ====================

    async def clear_history(self, session_id: str):
        """清空会话历史"""

        await ChatSession.clear_history_json(session_id=session_id)

        # 清空聊天室历史
        try:
            _ = self.ltm.clear(session_id)
        except Exception:
            pass

        logger.info(f"[AI Chat] 清空会话历史: {session_id}")

    async def set_persona(self, session_id: str, persona_name: str):
        """切换会话人格"""

        updated = await ChatSession.update_persona(session_id=session_id, persona_name=persona_name)
        if updated:
            logger.info(f"[AI Chat] 切换人格: {session_id} -> {persona_name}")

    async def set_session_active(self, session_id: str, is_active: bool):
        """设置会话启用状态"""

        updated = await ChatSession.update_active_status(session_id=session_id, is_active=is_active)
        # 无需额外处理

    async def get_session_info(self, session_id: str) -> Optional[ChatSession]:
        """获取会话信息"""

        return await ChatSession.get_by_session_id(session_id=session_id)


# ==================== 全局实例 ====================

chat_manager = ChatManager()
