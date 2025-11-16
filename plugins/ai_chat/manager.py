"""AI 对话核心管理（去除好感度，加入前后钩子）

- 去除了所有好感度逻辑与持久化
- 新增 pre/post 钩子，便于在调用 AI 前后自定义修改
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageEvent,
    Message,
    MessageSegment,
)
from dataclasses import dataclass
from nonebot.log import logger
from openai import AsyncOpenAI

# Track background tasks to prevent unbounded growth
_BG_TASKS: set[asyncio.Task] = set()


def _track_bg(task: asyncio.Task) -> None:
    _BG_TASKS.add(task)
    task.add_done_callback(lambda t: _BG_TASKS.discard(t))

from .config import get_config, get_personas, CFG, get_api_by_name
from .models import ChatSession
from .tools import get_enabled_tools, execute_tool
from .hooks import run_pre_ai_hooks, run_post_ai_hooks
from ...core.image_utils import image_url_to_base64

@dataclass
class AiChat:
    session: ChatSession
    messages: List[Dict[str, Any]]
    history: List[Dict[str, Any]]
    system_prompt: str
    tools: str
    config: Dict[str, Any]

class ChatManager:
    """AI 对话核心管理（去除好感度，加入前后钩子）"""

    def __init__(self):
        # 多服务商客户端缓存：{ provider_name: AsyncOpenAI }
        self.client: Optional[AsyncOpenAI] = None
        self.clients: Dict[str, AsyncOpenAI] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._history_locks: Dict[str, asyncio.Lock] = {}
        self.reset_client()

    def reset_client(self) -> None:
        """清空客户端缓存，根据会话按需创建。"""

        cfg = get_config()
        try:
            self.client = None
            self.clients = {}
            logger.debug("[AI Chat] 已清空 OpenAI 客户端缓存")
            try:
                if hasattr(self, "ltm") and self.ltm:
                    self.ltm.max_cnt = max(1, int(cfg.session.chatroom_history_max_lines))
            except Exception:
                pass
        except Exception as e:
            self.client = None
            self.clients = {}
            logger.error(f"[AI Chat] 客户端缓存重置失败: {e}")

    def _get_client_for(self, provider_name: Optional[str]) -> Optional[AsyncOpenAI]:
        from .config import get_api_by_name
        try:
            key = (provider_name or "").strip() or "__default__"
            if key in self.clients:
                return self.clients[key]
            api = get_api_by_name(provider_name)
            if not api or not api.api_key:
                return None
            cli = AsyncOpenAI(api_key=api.api_key, base_url=api.base_url, timeout=api.timeout)
            self.clients[key] = cli
            return cli
        except Exception:
            return None

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    def _get_active_api_flags(self, provider_name: Optional[str]) -> tuple[bool, bool]:
        """Return (support_tools, support_vision) for given provider.

        Falls back to (True, True) when not configured.
        """
        try:
            raw = CFG.load() or {}
            apis = dict(raw.get("api") or {})
            key = (provider_name or "").strip()
            if not key or key not in apis:
                if apis:
                    key = next(iter(apis.keys()))
            provider = dict(apis.get(key) or {})
            support_tools = bool(provider.get("support_tools", True))
            support_vision = bool(provider.get("support_vision", True))
            return support_tools, support_vision
        except Exception:
            return True, True

    # 对话历史
    async def _get_history(self, session: Optional[ChatSession] = None, max_pairs: int = 20) -> List[Dict[str, Any]]:
        """获取历史消息（优先读会话 JSON）。返回元素为 dict"""
        history: List[Dict[str, Any]] = []
        history = json.loads(session.history_json or "[]") if session and session.history_json else []
        if not isinstance(history, list):
            history = []
        if max_pairs <= 0:
            return []
        keep = max_pairs * 2
        trimmed = history[-keep:] if len(history) > keep else list(history)
        idx = next(
            (i for i, m in enumerate(trimmed) if (isinstance(m, dict) and m.get("role") == "user") or getattr(m, "role", None) == "user"),
            0,
        )
        if idx > 0:
            trimmed = trimmed[idx:]
        if len(trimmed) > keep:
            trimmed = trimmed[-keep:]
        return trimmed
    # ==================== 核心处理 ====================

    async def process_message(
        self,
        user_name: str,
        bot: Bot,
        event: MessageEvent,
        platform: str = "qq",
        session_type: str = "group",
        number: Optional[str] = None,
    ) -> Any:
        """处理用户消息（串行同会话，支持工具与前后钩子，多模态输出）。

        返回优先为 dict：{"text": str, "images": [str], "tts_path": Optional[str]}。
        """

        # 选择本会话服务商
        cfg_for_provider = get_config()
        current_provider = None
        session_id = await ChatSession.get_session_id(platform, session_type, number)
        lock = self._get_session_lock(session_id)
        async with lock:
            try:
                session = await ChatSession.get_by_session_id(session_id)
                pairs_limit = max(1, int(get_config().session.max_rounds))
                history = await self._get_history(session, pairs_limit)
                personas = get_personas()
                persona = personas.get(session.persona_name) or personas.get("default") or next(iter(personas.values()))
                system_prompt = persona.details

                # 计算会话服务商与能力
                current_provider = getattr(session, "provider_name", None) or getattr(get_config().session, "default_provider", "")
                client = self._get_client_for(current_provider)
                if not client:
                    return "AI 未配置或暂不可用"
                support_tools, support_vision = self._get_active_api_flags(current_provider)
                messages = self._build_ai_content(bot=bot, event=event)

                cfg = get_config()
                config = cfg.session
                config.set("provider",current_provider)
                config.set("model",get_api_by_name(current_provider).model)
                default_tools = None
                if getattr(cfg, "tools", None) and cfg.tools.enabled:
                    default_tools = get_enabled_tools(cfg.tools.builtin_tools)

                aiChat = AiChat(session, messages, history, system_prompt, default_tools, config)
                aiChat = await run_pre_ai_hooks(event, aiChat)
                response = await self._call_ai(aiChat, client)
                response = await run_post_ai_hooks(event=event, response=response)
                response = self._sanitize_response(response)

                clean_text, out_images = self._extract_output_media(response)
                tts_path: Optional[str] = None
                try:
                    cfg2 = get_config()
                    if getattr(cfg2, "output", None) and cfg2.output.tts_enable and clean_text:
                        from .tts import run_tts
                        tts_path = await run_tts(session_id=session_id, text=clean_text, manager=self)
                except Exception:
                    tts_path = None

                max_msgs = max(0, 2 * int(get_config().session.max_rounds))
                _track_bg(asyncio.create_task(
                    self._save_conversation(session_id, user_name, plain_current_text, clean_text, max_msgs)
                ))

                if session_type == "group" and clean_text:
                    try:
                        self.ltm.record_bot(session_id, clean_text)
                    except Exception:
                        pass

                return {"text": clean_text, "images": out_images, "tts_path": tts_path}

            except Exception as e:
                logger.exception(f"[AI Chat] 处理消息失败: {e}")
                return "抱歉，我遇到了一点问题。"
            
    # 辅助函数：获取昵称
    async def _get_nickname_for_at(self, bot: Bot, event: MessageEvent, user_id: int) -> str:
        try:
            if user_id == bot.self_id:
                return "@AI助手"
            if isinstance(event, GroupMessageEvent):
                member_info = await bot.get_group_member_info(
                    group_id=event.group_id, 
                    user_id=user_id,
                    no_cache=True
                )
                nickname = member_info.get('card') or member_info.get('nickname')
                return f"@{nickname or user_id}"
            else:
                stranger_info = await bot.get_stranger_info(user_id=user_id)
                return f"@{stranger_info.get('nickname', user_id)}"
        except Exception:
            return f"@{user_id}"
    
    # 核心函数：构建 AI 消息 (保持顺序版 + 支持 Forward)
    async def _build_ai_content(self, bot: Bot, event: MessageEvent) -> List[Dict[str, Any]]:
        """
        构建发送给 AI Vision 的消息内容列表（保持文本和图片的原始顺序）
        """

        openai_content_list: List[Dict[str, Any]] = []
        current_text_parts: List[str] = []

        # 内部函数：用于“提交”当前累积的文本
        def commit_pending_text():
            if current_text_parts:
                full_text = "".join(current_text_parts)
                openai_content_list.append({"type": "text", "text": full_text})
                current_text_parts.clear()

        # --- 核心处理循环 ---
        # 我们可以复用这个循环来处理 event.message 和 event.reply.message
        async def process_message_iterable(message_iter: List[MessageSegment]):
            for segment in message_iter:

                if segment.type == "text":
                    current_text_parts.append(str(segment))

                elif segment.type == "at":
                    user_id = int(segment.data["qq"])
                    nickname = await _get_nickname_for_at(bot, event, user_id)
                    current_text_parts.append(nickname)

                elif segment.type == "image":
                    commit_pending_text() # 提交图片前的文本

                    image_url = segment.data.get("url")
                    if not image_url:
                        continue

                    base64_data_url = await image_url_to_base64(image_url)
                    if base64_data_url:
                        openai_content_list.append({
                            "type": "image_url",
                            "image_url": {"url": base64_data_url}
                        })

                elif segment.type == "forward":
                    commit_pending_text() # 提交转发消息前的文本

                    # --- 这是你需要的聊天记录处理逻辑 ---
                    forward_content_list = segment.data.get("content")
                    current_text_parts.append("\n--- 以下是合并转发的聊天记录 ---\n")
                    if not forward_content_list:
                        current_text_parts.append("[聊天记录内容为空或获取失败]\n")
                        continue

                    for msg_dict in forward_content_list:
                        sender_nickname = msg_dict.get("sender", {}).get("nickname", "未知")
                        current_text_parts.append(f"[{sender_nickname}]: ")

                        # 遍历这条消息中的所有片段 (注意：这些是字典，不是 MessageSegment 对象)
                        inner_message_segments = msg_dict.get("message", [])
                        for inner_seg in inner_message_segments:
                            seg_type = inner_seg.get("type")
                            if seg_type == "text":
                                current_text_parts.append(inner_seg.get("data", {}).get("text", ""))
                            elif seg_type == "at":
                                current_text_parts.append("@(某人)") # 在这里再次解析@太复杂，简化处理
                            elif seg_type == "image":
                                current_text_parts.append("[图片]") # 同上，简化处理
                            # 忽略 reply, face 等

                        current_text_parts.append("\n") # 每条消息后换行

                    current_text_parts.append("--- 聊天记录结束 ---\n")

                elif segment.type in ["reply", "face", "record", "video"]:
                    # 忽略这些，它们不应提交给 AI
                    pass
                
        # --- 执行 ---

        # 1. 处理当前消息
        await process_message_iterable(event.message)

        # 2. 处理被回复的消息
        if event.reply:
            commit_pending_text() # 提交正文和回复之间的文本
            current_text_parts.append("\n--- 以下为用户发消息时引用的回复信息 ---\n")
            await process_message_iterable(event.reply.message)
            current_text_parts.append("--- 回复信息结束 ---\n")

        # 3. 提交最后剩余的文本
        commit_pending_text()

        return openai_content_list

    async def _call_ai(self, aichat: AiChat, client: Optional[AsyncOpenAI] = None) -> str:
        """调用 OpenAI 聊天接口，包含工具调用处理"""

        if not client:
            return "AI 未配置或暂不可用"
        support_tools, support_vision = self._get_active_api_flags(aichat.config.get("provider"))
        system_message = {
            "role": "system",
            "content": aichat.system_prompt
        }
        current_user_message = {
            "role": "user",
            "content": aichat.messages
        }
        messages = [system_message] + aichat.history + [current_user_message]

        _kwargs: Dict[str, Any] = {"model": aichat.config.get("model"), "messages": messages, "temperature": aichat.config.get("temperature")}
        if support_tools:
            _kwargs["tools"] = aichat.config.get("tools")
        current_response = await client.chat.completions.create(**_kwargs)

        iteration = 0
        while iteration < 3:
            choice = current_response.choices[0]
            tool_calls = choice.message.tool_calls or []
            if not tool_calls:
                break
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

            tasks = []
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                tasks.append(execute_tool(tc.function.name, args))
            results = []
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
            for tc, res in zip(tool_calls, results or []):
                content = str(res) if not isinstance(res, Exception) else f"工具执行异常: {res}"
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

            _kwargs2: Dict[str, Any] = {"model": aichat.config.get("model"), "messages": messages, "temperature": aichat.config.get("temperature")}
            if support_tools:
                _kwargs2["tools"] = aichat.config.get("tools")
            current_response = await client.chat.completions.create(**_kwargs2)

            iteration += 1

        return current_response.choices[0].message.content or ""

    # ==================== 输出多模态处理 ====================
    def _extract_output_media(self, text: str) -> tuple[str, List[str]]:
        """从模型输出文本中提取图片 URL，并返回（清洗后文本, 图片URL列表）"""

        if not text:
            return "", []
        try:
            imgs: List[str] = []
            cleaned = text
            import re as _re
            md_img = _re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")

            def _md_sub(m):
                url = m.group(1)
                imgs.append(url)
                return ""

            cleaned = md_img.sub(_md_sub, cleaned)
            url_pat = _re.compile(r"(https?:\/\/\S+?\.(?:png|jpe?g|gif|webp|bmp))(?!\S)", _re.IGNORECASE)

            def _url_sub(m):
                url = m.group(1)
                imgs.append(url)
                return url

            cleaned = url_pat.sub(_url_sub, cleaned)
            data_pat = _re.compile(r"data:image\/[^;]+;base64,[A-Za-z0-9+\/=]+")
            for m in data_pat.finditer(cleaned):
                imgs.append(m.group(0))
            cleaned = cleaned.strip()
            return cleaned, imgs
        except Exception:
            return text, []

    def _sanitize_response(self, text: str) -> str:
        """尽量清理“思考过程/提示词泄漏”，保留对用户可见的最终回答。

        - 清除标签块与代码围栏中的思考/提示内容
        - 移除以 THOUGHT/思考/Analysis/Plan/Constraint 等开头的段落
        - 进一步按段落过滤元信息，只保留正常回答
        """
        if not text:
            return text
        try:
            cleaned = text

            # 标签样式内容（如 <thinking>...）
            tags = (
                "thinking|analysis|reflection|chain_of_thought|cot|reasoning|"
                "plan|instructions|internal|scratchpad|tool|tool_call|function_call|"
                "prompt|system_prompt|constraints?"
            )
            cleaned = re.sub(rf"(?is)<(?:{tags})[^>]*>.*?</(?:{tags})\s*>", "", cleaned)
            cleaned = re.sub(rf"(?is)</?(?:{tags})[^>]*>", "", cleaned)
            cleaned = re.sub(rf"(?is)\[(?:{tags})[^\]]*\].*?\[/(?:{tags})\s*\]", "", cleaned)

            # 思考/提示相关代码围栏
            fence_kw = r"thought|thinking|analysis|reasoning|plan|prompt|system|constraints?"
            cleaned = re.sub(rf"(?is)```\s*(?:{fence_kw})?\s*[\s\S]*?```", "", cleaned)

            # 标题式的思考段落（直到空行）
            head_kw = (
                r"THOUGHT|Thoughts?|Analysis|Reasoning|Plan|Constraints?|Constraint\s+Checklist|"
                r"Confidence\s*Score|Strategizing\s*complete|System\s*Prompt|Internal|Scratchpad|"
                r"思考|深度思考|分析|推理|人设校验|最高的系统指令|约束清单|工具调用|联网函数|web_search"
            )
            cleaned = re.sub(rf"(?ims)^\s*(?:{head_kw})\b[\s\S]*?(?:\n\s*\n|\Z)", "", cleaned)

            # 常见“开始回答”提示句
            cleaned = re.sub(r"(?i)^\s*(?:I\s+will\s+now\s+generate\s+the\s+response\.|开始回答|现在生成回答).*\n?", "", cleaned)

            # 按段落过滤元信息
            meta_kw = re.compile(
                r"(?i)\b(THOUGHT|Thoughts?|Analysis|Reasoning|Plan|Constraint|Checklist|Confidence|System\s*Prompt|Internal|Scratchpad|web_search)\b|[思想析理约束人设工具联网]"
            )
            paras = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
            if paras:
                keep = [p for p in paras if not meta_kw.search(p)]
                if keep:
                    cleaned = "\n\n".join(keep)

            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
            return cleaned or ""
        except Exception:
            return text

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

        _ = await ChatSession.update_active_status(session_id=session_id, is_active=is_active)

    async def get_session_info(self, session_id: str) -> Optional[ChatSession]:
        """获取会话信息"""

        return await ChatSession.get_by_session_id(session_id=session_id)


# ==================== 全局实例 ====================
chat_manager = ChatManager()