"""AI 瀵硅瘽鏍稿績绠＄悊锛堝幓闄ゅソ鎰熷害锛屽姞鍏ュ墠鍚庨挬瀛愶級

- 鍘婚櫎浜嗘墍鏈夊ソ鎰熷害閫昏緫涓庢寔涔呭寲
- 鏂板 pre/post 閽╁瓙锛屼究浜庡湪璋冪敤 AI 鍓嶅悗鑷畾涔変慨鏀?
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict

from nonebot.log import logger
from openai import AsyncOpenAI

from ..config import get_config, get_personas, get_active_api
from .models import ChatSession
from .tools import get_enabled_tools, execute_tool
from .hooks import run_pre_ai_hooks, run_post_ai_hooks


# ==================== Chatroom Memory (in-memory) ====================


class ChatroomMemory:
    """鑱婂ぉ瀹ゅ巻鍙诧紙杞婚噺鍐呭瓨鐜舰缂撳啿锛夈€?

    浠呯敤浜庣兢鑱婁笂涓嬫枃鎻愮ず锛屼笉鍋氭寔涔呭寲銆?
    - 璁板綍鏍煎紡锛歔鏄电О/HH:MM:SS]: 鏂囨湰
    - get_history_str() 杩斿洖浠?"\n---\n" 杩炴帴鐨勫巻鍙蹭覆
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
    """AI 瀵硅瘽鏍稿績绠＄悊锛堝幓闄ゅソ鎰熷害锛屽姞鍏ュ墠鍚庨挬瀛愶級"""

    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        # 浼氳瘽閿侊紙鍚屼竴浼氳瘽涓茶锛屼笉鍚屼細璇濆苟琛岋級
        self._session_locks: Dict[str, asyncio.Lock] = {}
        # 鍘嗗彶 JSON 鎸佷箙鍖栭攣锛堥伩鍏嶅紓姝ュ啓鍏ョ珵鎬侊級
        self._history_locks: Dict[str, asyncio.Lock] = {}
        # 绠€鏄撹縼绉绘鏌ユ爣璁?
        self._schema_checked: bool = False
        # 鍒濆鍖栧鎴风
        self.reset_client()
        # 鑱婂ぉ瀹ゅ巻鍙诧紙鍐呭瓨锛?
        try:
            self.ltm = ChatroomMemory(max_cnt=max(1, int(get_config().session.chatroom_history_max_lines)))
        except Exception:
            self.ltm = ChatroomMemory(max_cnt=200)

    def reset_client(self) -> None:
        """鏍规嵁褰撳墠閰嶇疆閲嶅缓 OpenAI 瀹㈡埛绔?""

        cfg = get_config()  # 棰勭儹閰嶇疆
        try:
            active_api = get_active_api()
            if not active_api.api_key:
                self.client = None
                logger.warning("[AI Chat] OpenAI 鏈厤缃?API Key锛屽凡绂佺敤瀵硅瘽鑳藉姏")
                return
            self.client = AsyncOpenAI(
                api_key=active_api.api_key,
                base_url=active_api.base_url,
                timeout=active_api.timeout,
            )
            logger.debug("[AI Chat] OpenAI 瀹㈡埛绔凡鍒濆鍖?)
            # 鐑洿鏂拌亰澶╁鍘嗗彶瀹归噺
            try:
                if hasattr(self, "ltm") and self.ltm:
                    self.ltm.max_cnt = max(1, int(cfg.session.chatroom_history_max_lines))
            except Exception:
                pass
        except Exception as e:
            self.client = None
            logger.error(f"[AI Chat] OpenAI 瀹㈡埛绔垵濮嬪寲澶辫触: {e}")

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    def _model_supports_vision(self, model: Optional[str]) -> bool:
        """根据模型名称的特征词，粗略判断是否支持读图。

        说明：不同服务商的命名不完全一致，此处仅做通用判断，避免抛错。
        """
        try:
            if not model:
                return False
            name = str(model).lower()
            keywords = ["4o", "vision", "gpt-4.1", "gpt-4v", "omni"]
            return any(k in name for k in keywords)
        except Exception:
            return False

    # ==================== 鏁版嵁鍔犺浇 ====================

    async def _get_session(
        self,
        session_id: str,
        session_type: str,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ChatSession:
        """鑾峰彇鎴栧垱寤轰細璇濓紙鐩存帴鏌ュ簱锛?""

        # 浠呭湪棣栨璋冪敤鏃跺仛涓€娆″垪妫€鏌?
        if not self._schema_checked:
            try:
                await ChatSession.ensure_history_column()
            finally:
                self._schema_checked = True

        chat_session = await ChatSession.get_by_session_id(session_id=session_id)

        # 鑷姩鍒涘缓浼氳瘽
        cfg = get_config()
        if not chat_session :
            chat_session = await ChatSession.create_session(
                session_id=session_id,
                session_type=session_type,
                group_id=group_id,
                user_id=user_id,
                persona_name="default",
            )
            logger.info(f"[AI Chat] 鍒涘缓鏂颁細璇?{session_id}")

        return chat_session

    async def _get_history(
        self,
        session_id: str,
        session: Optional[ChatSession] = None,
    ) -> List[Dict[str, Any]]:
        """鑾峰彇鍘嗗彶娑堟伅锛堜紭鍏堣浼氳瘽 JSON锛夈€傝繑鍥炲厓绱犱负 dict"""

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
        """鎸夎疆(user+assistant)瑁佸壀鍘嗗彶锛岀‘淇濅粠绗竴涓?user 寮€濮?""

        try:
            if not history:
                return []
            if max_pairs <= 0:
                return []
            keep = max_pairs * 2
            trimmed = history[-keep:] if len(history) > keep else list(history)
            # 瀹氫綅绗竴涓?user锛屼繚璇佸榻?
            idx = next((i for i, m in enumerate(trimmed) if (isinstance(m, dict) and m.get("role") == "user") or getattr(m, "role", None) == "user"), 0)
            if idx > 0:
                trimmed = trimmed[idx:]
            # 鍐嶆鎴柇鍒板伓鏁伴暱搴?
            if len(trimmed) > keep:
                trimmed = trimmed[-keep:]
            return trimmed
        except Exception:
            return history

    # ==================== 鏍稿績澶勭悊 ====================

    def _sanitize_response(self, text: str) -> str:
        """绉婚櫎妯″瀷杩斿洖涓殑鎬濊€?鍐呴儴鏍囩鍧楋紝閬垮厤娉勯湶鎬濊€冭繃绋嬨€?

        浼氭竻鐞嗕互涓嬪潡鍙婂叾鍐呭锛堝ぇ灏忓啓涓嶆晱鎰燂級锛?
        <thinking>銆?analysis>銆?reflection>銆?chain_of_thought>銆?cot>銆?
        <reasoning>銆?plan>銆?instructions>銆?internal>銆?scratchpad>銆?
        <tool>銆?tool_call>銆?function_call>
        """
        if not text:
            return text
        try:
            tags = (
                "thinking|analysis|reflection|chain_of_thought|cot|reasoning|"
                "plan|instructions|internal|scratchpad|tool|tool_call|function_call"
            )
            # 绉婚櫎鎴愬鍧楁爣绛惧強鍐呭
            cleaned = re.sub(rf"(?is)<(?:{tags})[^>]*>.*?</(?:{tags})\s*>", "", text)
            # 娓呯悊鍙兘娈嬬暀鐨勮繖浜涙爣绛剧殑瀛ょ珛璧锋鏍囩
            cleaned = re.sub(rf"(?is)</?(?:{tags})[^>]*>", "", cleaned)
            # 鍏煎 [thinking]...[/thinking] 鐨勫啓娉?
            cleaned = re.sub(rf"(?is)\[(?:{tags})[^\]]*\].*?\[/(?:{tags})\s*\]", "", cleaned)
            # 瑙勮寖绌虹櫧
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
            return cleaned
        except Exception:
            return text

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
        images: Optional[List[str]] = None,
    ) -> str:
        """澶勭悊鐢ㄦ埛娑堟伅锛堜覆琛屽悓浼氳瘽锛屾敮鎸佸伐鍏疯皟鐢ㄤ笌鍓嶅悗閽╁瓙锛?""

        if not self.client:
            return "AI 鏈厤缃垨鏆備笉鍙敤"

        lock = self._get_session_lock(session_id)
        async with lock:
            try:
                # 1. 浼氳瘽涓庡巻鍙?
                session = await self._get_session(session_id, session_type, group_id, user_id)
                history = await self._get_history(session_id, session=session)

                if not session or not session.is_active:
                    return ""

                # 2. 瑁佸壀鍘嗗彶锛堟寜杞級
                try:
                    pairs_limit = max(1, int(get_config().session.max_rounds))
                    history = self._trim_history_rounds(history, pairs_limit)
                except Exception:
                    pass

                # 2.1 缇よ亰璁板綍鈥滆亰澶╁鍘嗗彶鈥濓紙鍐呭瓨锛?
                chatroom_history = ""
                if session_type == "group":
                    self.ltm.record_user(session_id, user_name, message)
                    chatroom_history = self.ltm.get_history_str(session_id)

                if active_reply:
                    history = []

                # 3. 鏋勫缓娑堟伅鍒楄〃
                messages = self._build_messages(
                    session,
                    history,
                    message,
                    user_name,
                    session_type,
                    chatroom_history=chatroom_history,
                    active_reply=active_reply,
                    active_reply_suffix=active_reply_suffix,
                    images=images or [],
                )

                # 3.1 榛樿鍙傛暟锛堝彲琚?pre 閽╁瓙瑕嗙洊锛?
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

                # 如果本轮包含图片且模型不支持读图，直接以人格口吻友好提示
                if images and not self._model_supports_vision(model):
                    return (
                        "抱歉，我当前的模型不具备图像理解能力。"
                        "如需解析图片，请切换到支持视觉的模型（例如 gpt‑4o / gpt‑4o‑mini）后再试。"
                    )

                # 4. 璋冪敤 AI
                response = await self._call_ai(
                    session,
                    messages,
                    model=model,
                    temperature=temperature,
                    tools=tools,
                )

                # 4.1 post 閽╁瓙锛堝厑璁镐簩娆″鐞嗭級
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

                # 鏈€缁堣緭鍑烘竻娲楋紙绉婚櫎 <thinking> 绛夊唴閮ㄦ爣绛撅級
                response = self._sanitize_response(response)

                # 5. 寮傛鎸佷箙鍖栵紙涓嶉樆濉炲洖澶嶏級
                max_msgs = max(0, 2 * int(get_config().session.max_rounds))
                asyncio.create_task(
                    self._save_conversation(
                        session_id, user_name, message, response, max_msgs, images=images or []
                    )
                )

                # 6. 璁板綍鏈哄櫒浜哄洖澶嶅埌鈥滆亰澶╁鍘嗗彶鈥?
                if session_type == "group" and response:
                    try:
                        self.ltm.record_bot(session_id, response)
                    except Exception:
                        pass

                return response

            except Exception as e:
                logger.exception(f"[AI Chat] 澶勭悊娑堟伅澶辫触: {e}")
                return "鎶辨瓑锛屾垜閬囧埌浜嗕竴鐐归棶棰樸€?

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
        images: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """鏋勫缓鍙戦€佺粰 AI 鐨勬秷鎭垪琛?""

        messages: List[Dict[str, Any]] = []

        # 1) System Prompt
        personas = get_personas()
        # 鏇村仴澹細浼樺厛褰撳墠浼氳瘽璁惧畾锛屽叾娆?default锛屾渶鍚庝换涓€鍙敤浜烘牸
        persona = personas.get(session.persona_name) or personas.get("default") or next(iter(personas.values()))
        # 浣跨敤浜烘牸璇︽儏浣滀负绯荤粺鎻愮ず璇?
        system_prompt = persona.details

        # 鑱婂ぉ瀹ゅ巻鍙诧紙娉ㄥ叆鍒?system锛?
        if active_reply:
            if chatroom_history:
                system_prompt += (
                    "\nYou are now in a chatroom. The chat history is as follows:\n" + chatroom_history
                )

        messages.append({"role": "system", "content": system_prompt})
        _active_reply = bool(active_reply)
        _ar_suffix = (active_reply_suffix or "")

        # 2) 鍘嗗彶娑堟伅
        for msg in history:
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            uname = msg.get("user_name") if isinstance(msg, dict) else getattr(msg, "user_name", None)
            # 缇よ亰鏃朵负鐢ㄦ埛娑堟伅娣诲姞鈥滄樀绉? 鍐呭鈥濆墠缂€
            if session_type == "group" and role == "user" and uname:
                content = f"{uname}: {content}"
            messages.append({"role": role, "content": content})

        # 3) 褰撳墠鐢ㄦ埛娑堟伅锛堟敮鎸佸浘鏂囨贩鍚堬級
        current_content = f"{user_name}: {message}" if session_type == "group" else message
        if images:
            parts: List[Dict[str, Any]] = []
            if current_content:
                parts.append({"type": "text", "text": current_content})
            for url in images:
                parts.append({"type": "image_url", "image_url": {"url": str(url)}})
            messages.append({"role": "user", "content": parts})
        else:
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
        """璋冪敤 OpenAI 鑱婂ぉ鎺ュ彛锛屽寘鍚伐鍏疯皟鐢ㄥ鐞?""

        if not self.client:
            return "AI 鏈厤缃垨鏆備笉鍙敤"

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

        # 鍒濇璋冪敤
        current_response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            tools=tools,
        )

        # 澶勭悊鍙兘鐨勫伐鍏疯皟鐢紙绠€鍗曞惊鐜級
        max_iterations = (cfg.tools.max_iterations if getattr(cfg, "tools", None) else 2)
        iteration = 0
        while iteration < max_iterations:
            choice = current_response.choices[0]
            tool_calls = choice.message.tool_calls or []

            # 鏃犲伐鍏疯皟鐢ㄥ垯鐩存帴杩斿洖
            if not tool_calls:
                break

            # 灏?AI 鐨勫伐鍏疯皟鐢ㄦ秷鎭姞鍏?messages
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

            # 鎵ц宸ュ叿璋冪敤
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    tool_args = {}

                tool_result = await execute_tool(tool_name, tool_args)

                # 娣诲姞宸ュ叿缁撴灉娑堟伅
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})

            # 鍐嶆璋冪敤 AI 缁х画瀵硅瘽
            current_response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                tools=tools,
            )

            iteration += 1

        # 杩斿洖鏈€缁堝洖澶?
        return current_response.choices[0].message.content or ""

    async def _save_conversation(
        self,
        session_id: str,
        user_name: str,
        message: str,
        response: str,
        max_history: int,
        *,
        images: Optional[List[str]] = None,
    ) -> None:
        """寮傛淇濆瓨瀵硅瘽鍘嗗彶锛堜粎缁存姢浼氳瘽 JSON 鍘嗗彶锛?""

        try:
            # 缁存姢浼氳瘽 JSON 鍘嗗彶锛堜覆琛岄伩鍏嶇珵鎬侊級
            lock = self._history_locks.setdefault(session_id, asyncio.Lock())
            async with lock:
                now = datetime.now().isoformat()
                user_item = {
                    "role": "user",
                    "content": message,
                    "user_name": user_name,
                    "created_at": now,
                }
                if images:
                    user_item["attachments"] = {"images": list(images)}
                items = [user_item, {"role": "assistant", "content": response, "created_at": now}]
                _ = await ChatSession.append_history_items(
                    session_id=session_id, items=items, max_history=max_history
                )
        except Exception as e:
            logger.error(f"[AI Chat] 淇濆瓨瀵硅瘽澶辫触: {e}")

    # ==================== 绠＄悊鎺ュ彛 ====================

    async def clear_history(self, session_id: str):
        """娓呯┖浼氳瘽鍘嗗彶"""

        await ChatSession.clear_history_json(session_id=session_id)

        # 娓呯┖鑱婂ぉ瀹ゅ巻鍙?
        try:
            _ = self.ltm.clear(session_id)
        except Exception:
            pass

        logger.info(f"[AI Chat] 娓呯┖浼氳瘽鍘嗗彶: {session_id}")

    async def set_persona(self, session_id: str, persona_name: str):
        """鍒囨崲浼氳瘽浜烘牸"""

        updated = await ChatSession.update_persona(session_id=session_id, persona_name=persona_name)
        if updated:
            logger.info(f"[AI Chat] 鍒囨崲浜烘牸: {session_id} -> {persona_name}")

    async def set_session_active(self, session_id: str, is_active: bool):
        """璁剧疆浼氳瘽鍚敤鐘舵€?""

        updated = await ChatSession.update_active_status(session_id=session_id, is_active=is_active)
        # 鏃犻渶棰濆澶勭悊

    async def get_session_info(self, session_id: str) -> Optional[ChatSession]:
        """鑾峰彇浼氳瘽淇℃伅"""

        return await ChatSession.get_by_session_id(session_id=session_id)


# ==================== 鍏ㄥ眬瀹炰緥 ====================

chat_manager = ChatManager()
