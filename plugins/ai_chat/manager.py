"""AI 对话核心管理 (已修复身份识别 & 移除历史图片存储)
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from collections import defaultdict
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Bot,
    MessageEvent,
    MessageSegment,
)
from dataclasses import dataclass
from nonebot.log import logger
from openai import AsyncOpenAI

from ...core.framework.local_cache import cache
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
    tools: Optional[List[Dict[str, Any]]]
    config: Dict[str, Any]

class ChatManager:
    """AI 对话核心管理"""

    def __init__(self):
        # 多服务商客户端缓存：{ provider_name: AsyncOpenAI }
        self.clients: Dict[str, AsyncOpenAI] = {}
        self.reset_client()

    def reset_client(self) -> None:
        """清空客户端缓存，根据会话按需创建。"""
        self.clients = {}
        logger.debug("[AI Chat] 已清空 OpenAI 客户端缓存")

    def _get_client_for(self, provider_name: Optional[str]) -> Optional[AsyncOpenAI]:
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

    def _get_active_api_flags(self, provider_name: Optional[str]) -> tuple[bool, bool]:
        api_item = get_api_by_name(provider_name)
        support_tools = getattr(api_item, "support_tools", True)
        support_vision = getattr(api_item, "support_vision", True)
        return support_tools, support_vision

    # ==================== 1. 历史记录处理 (注入名字) ====================
    async def _get_history(self, session: Optional[ChatSession] = None, max_pairs: int = 20) -> List[Dict[str, Any]]:
        """获取历史消息。在此处将存储的 user_name 拼接到 content 中"""
        history: List[Dict[str, Any]] = []
        history = json.loads(session.history_json or "[]") if session and session.history_json else []
        if not isinstance(history, list):
            history = []
        if max_pairs <= 0:
            return []
        
        keep = max_pairs * 2
        trimmed = history[-keep:] if len(history) > keep else list(history)
        
        # 找到第一个 User 消息的位置，避免截断导致第一条是 Assistant
        idx = next(
            (i for i, m in enumerate(trimmed) if (isinstance(m, dict) and m.get("role") == "user") or getattr(m, "role", None) == "user"),
            0,
        )
        if idx > 0:
            trimmed = trimmed[idx:]
        if len(trimmed) > keep:
            trimmed = trimmed[-keep:]

        # --- 处理名字注入 ---
        processed_history = []
        for msg in trimmed:
            new_msg = msg.copy()
            # 如果是 User 消息，且有名字，且内容是纯文本（因为存的时候已经转成纯文本了），则拼接
            if new_msg.get("role") == "user":
                u_name = new_msg.pop("user_name", None) # 取出并移除，API 不需要这个字段
                content = new_msg.get("content", "")
                if u_name and isinstance(content, str):
                     # 格式：[张三]: 你好
                    new_msg["content"] = f"[{u_name}]: {content}"
            
            processed_history.append(new_msg)

        return processed_history

    # ==================== 核心处理 ====================

    async def process_message(
        self,
        user_name: str,
        bot: Bot,
        event: MessageEvent,
        session_id: str,
    ) -> Any:
        """处理用户消息"""
        current_provider = None
        lock_key = f"ai_chat:session_lock:{session_id}"
        
        try:
            async with cache.lock(lock_key, ex=60, block=True, timeout=45):
                try:
                    session = await ChatSession.get_by_session_id(session_id)
                    if not session:
                        logger.error(f"[AI Chat] 无法找到或创建会话: {session_id}")
                        return "系统错误：会话加载失败。"
                    
                    pairs_limit = max(1, int(get_config().session.max_rounds))
                    
                    # 1. 读取历史 (已带名字)
                    history = await self._get_history(session, pairs_limit)
                    
                    personas = get_personas()
                    persona = personas.get(session.persona_name) or personas.get("default") or next(iter(personas.values()))
                    system_prompt = persona.details

                    current_provider = getattr(session, "provider_name", None) or getattr(get_config().session, "default_provider", "")
                    client = self._get_client_for(current_provider)
                    if not client:
                        return "AI 未配置或暂不可用"

                    # 2. 构建当前消息 (传入 user_name)
                    messages = await self._build_ai_content(bot=bot, event=event, user_name=user_name)

                    cfg = get_config()
                    session_config_dict = cfg.session.model_dump()
                    api_item = get_api_by_name(current_provider)
                    session_config_dict["provider"] = current_provider
                    session_config_dict["model"] = api_item.model
                    session_config_dict["temperature"] = session_config_dict.get("default_temperature", 0.7)
                    
                    default_tools = None
                    if getattr(cfg, "tools", None) and cfg.tools.enabled:
                        _tools_list = get_enabled_tools(cfg.tools.builtin_tools)
                        if _tools_list:
                            default_tools = _tools_list

                    # 3. 调用 AI
                    aiChat = AiChat(session, messages, history, system_prompt, default_tools, session_config_dict)
                    aiChat = await run_pre_ai_hooks(event, aiChat)
                    response = await self._call_ai(aiChat, client)
                    response = await run_post_ai_hooks(event, aiChat, response)
                    
                    # 4. 清洗回复 (包含去除开头的名字)
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

                    # 5. 保存历史 (传入原始 messages 列表进行压缩清洗)
                    max_msgs = max(0, int(get_config().session.max_rounds))
                    await self._save_conversation(session_id, user_name, messages, clean_text, max_msgs)

                    return {"text": clean_text, "images": out_images, "tts_path": tts_path}

                except Exception as e:
                    logger.exception(f"[AI Chat] 处理消息失败: {e}")
                    pass
        
        except TimeoutError:
            logger.warning(f"[AI Chat] 会话 {session_id} 获取锁超时")
            return "说太快了，我处理不过来啦..."

    # 辅助函数：获取昵称
    async def _get_nickname_for_at(self, bot: Bot, event: MessageEvent, user_id: int) -> str:
        try:
            if user_id == bot.self_id:
                return "@AI助手"
            if isinstance(event, GroupMessageEvent):
                member_info = await bot.get_group_member_info(group_id=event.group_id, user_id=user_id, no_cache=True)
                nickname = member_info.get('card') or member_info.get('nickname')
                return f"@{nickname or user_id}"
            else:
                stranger_info = await bot.get_stranger_info(user_id=user_id)
                return f"@{stranger_info.get('nickname', user_id)}"
        except Exception:
            return f"@{user_id}"
    
    # ==================== 2. 构建 AI 消息 (包含名字前缀) ====================
    async def _build_ai_content(self, bot: Bot, event: MessageEvent, user_name: str) -> List[Dict[str, Any]]:
        """
        构建发送给 AI Vision 的消息内容列表
        user_name: 当前消息发送者的昵称
        """

        openai_content_list: List[Dict[str, Any]] = []
        
        # 初始化直接带上名字前缀
        current_text_parts: List[str] = [f"[{user_name}]: "]

        def commit_pending_text():
            if current_text_parts:
                full_text = "".join(current_text_parts)
                openai_content_list.append({"type": "text", "text": full_text})
                current_text_parts.clear()

        async def process_message_iterable(message_iter: List[MessageSegment]):
            for segment in message_iter:
                if segment.type == "text":
                    current_text_parts.append(str(segment))
                elif segment.type == "at":
                    user_id = int(segment.data["qq"])
                    nickname = await self._get_nickname_for_at(bot, event, user_id)
                    current_text_parts.append(nickname)
                elif segment.type == "image":
                    commit_pending_text()
                    image_url = segment.data.get("url")
                    if not image_url: continue
                    base64_data_url = await image_url_to_base64(image_url, include_data_url=True)
                    if base64_data_url:
                        openai_content_list.append({
                            "type": "image_url",
                            "image_url": {"url": base64_data_url}
                        })
                elif segment.type == "forward":
                    commit_pending_text()
                    forward_content_list = segment.data.get("content")
                    current_text_parts.append("\n--- 以下是合并转发的聊天记录 ---\n")
                    if not forward_content_list:
                        current_text_parts.append("[内容为空]\n")
                        continue
                    for msg_dict in forward_content_list:
                        sender_nickname = msg_dict.get("sender", {}).get("nickname", "未知")
                        current_text_parts.append(f"[{sender_nickname}]: ")
                        inner_message_segments = msg_dict.get("message", [])
                        for inner_seg in inner_message_segments:
                            seg_type = inner_seg.get("type")
                            if seg_type == "text":
                                current_text_parts.append(inner_seg.get("data", {}).get("text", ""))
                            elif seg_type == "image":
                                current_text_parts.append("[图片]")
                        current_text_parts.append("\n")
                    current_text_parts.append("--- 聊天记录结束 ---\n")
                elif segment.type in ["reply", "face", "record", "video"]:
                    pass
                
        await process_message_iterable(event.message)

        if event.reply:
            commit_pending_text()
            current_text_parts.append("\n--- 以下为用户发消息时引用的回复信息 ---\n")
            await process_message_iterable(event.reply.message)
            current_text_parts.append("--- 回复信息结束 ---\n")

        commit_pending_text()
        return openai_content_list

    async def _call_ai(self, aichat: AiChat, client: Optional[AsyncOpenAI] = None) -> str:
        """调用 OpenAI 聊天接口"""
        if not client: return "AI 未配置"
        
        support_tools, support_vision = self._get_active_api_flags(aichat.config.get("provider"))
        system_message = {"role": "system", "content": aichat.system_prompt}
        current_user_message = {"role": "user", "content": aichat.messages}
        
        # 组合消息
        messages = [system_message] + aichat.history + [current_user_message]
        
        provider_name = (aichat.config.get("provider") or "").lower()
        is_gemini = "gemini" in provider_name

        _kwargs: Dict[str, Any] = {"model": aichat.config.get("model"), "messages": messages, "temperature": aichat.config.get("temperature")}
        user_tools = aichat.tools if (support_tools and aichat.tools) else []
        
        if is_gemini:
            gemini_tools_payload = [{"googleSearch": {}}]
            if user_tools: gemini_tools_payload.extend(user_tools)
            _kwargs["extra_body"] = {"tools": gemini_tools_payload}
        else:
            if user_tools: _kwargs["tools"] = user_tools
            
        current_response = await client.chat.completions.create(**_kwargs)

        # 工具调用循环
        iteration = 0
        while iteration < 3:
            choice = current_response.choices[0]
            tool_calls = choice.message.tool_calls or []
            if not tool_calls:
                break
            messages.append({
                "role": "assistant",
                "content": choice.message.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ]
            })
            tasks = []
            for tc in tool_calls:
                try: args = json.loads(tc.function.arguments or "{}")
                except Exception: args = {}
                tasks.append(execute_tool(tc.function.name, args))
            results = []
            if tasks: results = await asyncio.gather(*tasks, return_exceptions=True)
            for tc, res in zip(tool_calls, results or []):
                content = str(res) if not isinstance(res, Exception) else f"异常: {res}"
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

            _kwargs["messages"] = messages
            current_response = await client.chat.completions.create(**_kwargs)
            iteration += 1

        return current_response.choices[0].message.content or ""

    def _extract_output_media(self, text: str) -> tuple[str, List[str]]:
        if not text: return "", []
        try:
            imgs: List[str] = []
            cleaned = text
            import re as _re
            # Markdown 图片
            cleaned = _re.sub(r"!\[[^\]]*\]\(([^)\s]+)\)", lambda m: imgs.append(m.group(1)) or "", cleaned)
            # 纯 URL 图片
            url_pat = _re.compile(r"(https?:\/\/\S+?\.(?:png|jpe?g|gif|webp|bmp))(?!\S)", _re.IGNORECASE)
            cleaned = url_pat.sub(lambda m: imgs.append(m.group(1)) or m.group(1), cleaned) # URL 暂时保留在文本中，因为有时候是表情包
            # Base64 (不常见，但为了安全)
            cleaned = _re.sub(r"data:image\/[^;]+;base64,[A-Za-z0-9+\/=]+", lambda m: imgs.append(m.group(0)) or "", cleaned)
            return cleaned.strip(), imgs
        except Exception:
            return text, []

    # ==================== 3. 清洗回复 (过滤开头的人设名) ====================
    def _sanitize_response(self, text: str) -> str:
        if not text: return text
        try:
            cleaned = text
            # 1. 清理思考标签
            tags = "thinking|analysis|reflection|chain_of_thought|cot|reasoning|plan|instructions|internal|tool|function_call"
            cleaned = re.sub(rf"(?is)<(?:{tags})[^>]*>.*?</(?:{tags})\s*>", "", cleaned)
            cleaned = re.sub(rf"(?is)</?(?:{tags})[^>]*>", "", cleaned)
            
            # 2. 清理代码块思考
            cleaned = re.sub(r"(?is)```\s*(?:thought|thinking|analysis)\s*[\s\S]*?```", "", cleaned)

            # 3. 清理标题式思考
            head_kw = r"THOUGHT|Analysis|Reasoning|Plan|思考|深度思考|分析|推理"
            cleaned = re.sub(rf"(?ims)^\s*(?:{head_kw})\b[\s\S]*?(?:\n\s*\n|\Z)", "", cleaned)

            # 4. === 新增：清理 AI 自带的开头名字 ===
            # 匹配 [AI助手]: 或者 [Bot Name]： 这种格式
            cleaned = re.sub(r"^\[.*?\][:：]\s*", "", cleaned)

            return re.sub(r"\n{3,}", "\n\n", cleaned).strip() or ""
        except Exception:
            return text

    # ==================== 4. 保存对话 (移除 Base64 图片) ====================
    async def _save_conversation(
        self,
        session_id: str,
        user_name: str,
        message_content_list: List[Dict[str, Any]],
        response: str,
        max_history: int,
    ) -> None:
        """
        保存对话历史。
        将 message_content_list (OpenAI 格式) 转换为纯文本存储，
        **移除所有图片数据**，防止历史记录过大。
        """
        try:
            # 将发送给 AI 的复杂消息列表转换为简单的纯文本历史
            simple_user_content = ""
            
            if isinstance(message_content_list, list):
                for item in message_content_list:
                    msg_type = item.get("type")
                    if msg_type == "text":
                        simple_user_content += item.get("text", "")
                    elif msg_type == "image_url":
                        # 核心：替换图片为占位符
                        simple_user_content += " [图片] "
            else:
                # Fallback
                simple_user_content = str(message_content_list)

            now = datetime.now().isoformat()
            items = [
                {
                    "role": "user", 
                    "content": simple_user_content.strip(), 
                    "user_name": user_name, 
                    "created_at": now
                },
                {
                    "role": "assistant", 
                    "content": response, 
                    "created_at": now
                },
            ]
            _ = await ChatSession.append_history_items(
                session_id=session_id, items=items, max_history=max_history
            )
        except Exception as e:
            logger.error(f"[AI Chat] 保存对话失败: {e}")

    # ==================== 管理接口 ====================

    async def clear_history(self, session_id: str):
        await ChatSession.clear_history_json(session_id=session_id)
        logger.info(f"[AI Chat] 清空会话历史: {session_id}")

    async def set_persona(self, session_id: str, persona_name: str):
        updated = await ChatSession.update_persona(session_id=session_id, persona_name=persona_name)
        if updated:
            logger.info(f"[AI Chat] 切换人格: {session_id} -> {persona_name}")

    async def set_session_active(self, session_id: str, is_active: bool):
        _ = await ChatSession.update_active_status(session_id=session_id, is_active=is_active)

    async def get_session_info(self, session_id: str) -> Optional[ChatSession]:
        return await ChatSession.get_by_session_id(session_id=session_id)


chat_manager = ChatManager()