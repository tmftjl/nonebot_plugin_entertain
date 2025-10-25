"""AI 瀵硅瘽鏍稿績绠＄悊

鍖呭惈锛?
- CacheManager: 杞婚噺澶氬眰缂撳瓨绠＄悊
- ChatManager: AI 瀵硅瘽鏍稿績閫昏緫
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
    """澶氬眰缂撳瓨绠＄悊锛圠1 鍐呭瓨缂撳瓨 + TTL锛?""

    def __init__(self):
        # L1 缂撳瓨: {key: (value, expire_at)}
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """鑾峰彇缂撳瓨"""

        async with self._lock:
            if key in self._cache:
                value, expire_at = self._cache[key]
                # TTL=0 琛ㄧず姘镐箙缂撳瓨
                if expire_at == 0 or time.time() < expire_at:
                    return value
                # 杩囨湡锛屽垹闄?
                del self._cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: int = 0):
        """璁剧疆缂撳瓨

        Args:
            key: 缂撳瓨閿?
            value: 缂撳瓨鍊?
            ttl: 杩囨湡鏃堕棿锛堢锛夛紝0 琛ㄧず姘镐箙
        """

        expire_at = time.time() + ttl if ttl > 0 else 0
        async with self._lock:
            self._cache[key] = (value, expire_at)

    async def delete(self, key: str):
        """鍒犻櫎缂撳瓨"""

        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self):
        """娓呯┖鎵€鏈夌紦瀛?""

        async with self._lock:
            self._cache.clear()

    async def clear_pattern(self, pattern: str):
        """鎸夐敭鍚嶅寘鍚叧绯绘竻鐞嗙紦瀛橈紙绠€鍗曟ā寮忥級"""

        async with self._lock:
            keys_to_delete = [k for k in list(self._cache.keys()) if pattern in k]
            for k in keys_to_delete:
                self._cache.pop(k, None)


# ==================== ChatManager ====================


class ChatManager:
    """AI 瀵硅瘽鏍稿績绠＄悊"""

    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        # 浼氳瘽閿侊紙鍚屼竴浼氳瘽涓茶锛屼笉鍚屼細璇濆苟琛岋級
        self._session_locks: Dict[str, asyncio.Lock] = {}
        # 鍘嗗彶 JSON 鎸佷箙鍖栭攣锛堥伩鍏嶅紓姝ュ啓鍏ョ珵鎬侊級
        self._history_locks: Dict[str, asyncio.Lock] = {}
        # 绠€鏄撹縼绉绘鏌ユ爣蹇?
        self._schema_checked: bool = False
        # 鍒濆鍖栧鎴风
        self.reset_client()

        # 鎬ц兘寮€鍏筹紙濡傞渶蹇€熷洖閫€浼樺寲锛屾敼涓?False/0锛?        self.USE_L1_CACHE: bool = True
        self.TRIM_ROUNDS_DEFAULT: int = 0  # 0 琛ㄧず鍏抽棴鎸夎疆瑁佸壀

    def reset_client(self) -> None:
        """鏍规嵁褰撳墠閰嶇疆閲嶅缓 OpenAI 瀹㈡埛绔?""

        _ = get_config()  # 棰勭儹閰嶇疆
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
        except Exception as e:
            self.client = None
            logger.error(f"[AI Chat] OpenAI 瀹㈡埛绔垵濮嬪寲澶辫触: {e}")

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """鑾峰彇浼氳瘽閿?""

        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    # ==================== 鏁版嵁鍔犺浇 ====================

    async def _get_session(
        self,
        session_id: str,
        session_type: str,
        group_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ChatSession:
        """鑾峰彇鎴栧垱寤轰細璇濓紙鐩存帴鏌ュ簱锛?""

        cfg = get_config()
        # L1 缂撳瓨浼樺厛
        if self.USE_L1_CACHE:
            try:
                cache_key = f"ai_chat:session:{session_id}"
                cached = await cache_manager.get(cache_key)
                if cached is not None:
                    return cached
            except Exception:
                pass

        # 纭繚浼氳瘽琛ㄥ寘鍚?history_json 鍒楋紙涓€娆℃€ф鏌ワ級
        if not self._schema_checked:
            try:
                await ChatSession.ensure_history_column()
            finally:
                self._schema_checked = True

        # DB 鏌ヨ
        chat_session = await ChatSession.get_by_session_id(session_id=session_id)

        # 鑷姩鍒涘缓浼氳瘽
        if not chat_session and cfg.session.auto_create:
            chat_session = await ChatSession.create_session(
                session_id=session_id,
                session_type=session_type,
                group_id=group_id,
                user_id=user_id,
                persona_name="default",
                max_history=cfg.session.default_max_history,
            )
            logger.info(f"[AI Chat] 鍒涘缓鏂颁細璇?{session_id}")

        # 鍐欏叆缂撳瓨
        if self.USE_L1_CACHE:
            try:
                await cache_manager.set(cache_key, chat_session, ttl=cfg.cache.session_ttl)
            except Exception:
                pass
        return chat_session

    async def _get_history(
        self,
        session_id: str,
        session: Optional[ChatSession] = None,
        max_history: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """鑾峰彇鍘嗗彶娑堟伅锛堜紭鍏堣浼氳瘽 JSON锛屽甫缂撳瓨锛夈€傝繑鍥炲厓绱犱负 dict銆?""

        # 鐩存帴璇诲彇锛屼笉浣跨敤缂撳瓨

        # 浼樺厛浠庝細璇?JSON 璇诲彇
        if session is None:
            session = await self._get_session(session_id, session_type="group")

        # L1 缂撳瓨浼樺厛
        if self.USE_L1_CACHE:
            try:
                cfg = get_config()
                hist_key = f"ai_chat:history:{session_id}"
                cached = await cache_manager.get(hist_key)
                if cached is not None:
                    return cached
            except Exception:
                pass

        history_list: List[Dict[str, Any]] = []
        try:
            history_list = json.loads(session.history_json or "[]") if session and session.history_json else []
            if not isinstance(history_list, list):
                history_list = []
        except Exception:
            history_list = []

        # 鍏煎锛氳嫢 JSON 涓虹┖锛屽洖閫€鍒版槑缁嗚〃鏈€杩戣褰曪紝骞跺洖濉?JSON
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
            # 鍥炲～涓€娆★紙蹇界暐寮傚父锛?
            try:
                await ChatSession.set_history_list(session_id=session_id, history=history_list)
                if session:
                    session.history_json = json.dumps(history_list, ensure_ascii=False)
                    # 涓嶅啀鍐欏叆杩愯鏃剁紦瀛?
            except Exception:
                pass

        # 鍐欏叆缂撳瓨
        if self.USE_L1_CACHE:
            try:
                await cache_manager.set(hist_key, history_list, ttl=cfg.cache.history_ttl)
            except Exception:
                pass
        return history_list

    async def _get_favorability(self, user_id: str, session_id: str) -> UserFavorability:
        """鑾峰彇鎴栧垱寤虹敤鎴峰ソ鎰熷害锛堝甫缂撳瓨锛?""

        # L1 缂撳瓨浼樺厛
        if self.USE_L1_CACHE:
            try:
                cfg = get_config()
                favo_key = f"ai_chat:favo:{user_id}:{session_id}"
                cached = await cache_manager.get(favo_key)
                if cached is not None:
                    return cached
            except Exception:
                pass

        favo = await UserFavorability.get_favorability(user_id=user_id, session_id=session_id)

        if not favo:
            favo = await UserFavorability.create_favorability(
                user_id=user_id, session_id=session_id, initial_favorability=50
            )

        # 鍐欏叆缂撳瓨
        if self.USE_L1_CACHE:
            try:
                await cache_manager.set(favo_key, favo, ttl=cfg.cache.favorability_ttl)
            except Exception:
                pass
        return favo

    def _trim_history_rounds(self, history: List[Dict[str, Any]], max_pairs: int) -> List[Dict[str, Any]]:
        """鎸夎疆(user+assistant)瑁佸壀鍘嗗彶锛岀‘淇濅粠绗竴涓?user 寮€濮嬨€?
        Args:
            history: 鍘嗗彶鍒楄〃锛堟寜鏃堕棿鍗囧簭/浠绘剰锛?            max_pairs: 鏈€澶氫繚鐣欑殑杞暟
        """
        try:
            if not history:
                return []
            if max_pairs <= 0:
                return []
            keep = max_pairs * 2
            trimmed = history[-keep:] if len(history) > keep else list(history)
            # 瀹氫綅绗竴涓?user锛屼繚璇佸榻?            idx = next((i for i, m in enumerate(trimmed) if (isinstance(m, dict) and m.get("role") == "user") or getattr(m, "role", None) == "user"), 0)
            if idx > 0:
                trimmed = trimmed[idx:]
            # 鍐嶆鎴柇鍒板伓鏁伴暱搴?            if len(trimmed) > keep:
                trimmed = trimmed[-keep:]
            return trimmed
        except Exception:
            return history

    # ==================== 鏍稿績澶勭悊 ====================

    async def process_message(
        self,
        session_id: str,
        user_id: str,
        user_name: str,
        message: str,
        session_type: str = "group",
        group_id: Optional[str] = None,
    ) -> str:
        """澶勭悊鐢ㄦ埛娑堟伅锛堜覆琛屽悓浼氳瘽锛屾敮鎸佸伐鍏疯皟鐢級"""

        # OpenAI 鏈厤缃?
        if not self.client:
            return "AI 鏈厤缃垨鏆備笉鍙敤"

        # 浼氳瘽閿?
        lock = self._get_session_lock(session_id)
        async with lock:
            try:
                # 1. 鍏堝彇浼氳瘽瀵硅薄锛屽啀骞跺彂璇诲彇鍘嗗彶涓庡ソ鎰熷害
                session = await self._get_session(session_id, session_type, group_id, user_id)
                history, favo = await asyncio.gather(
                    self._get_history(session_id, session=session),
                    self._get_favorability(user_id, session_id),
                )

                # 浼氳瘽鏈惎鐢?
                if not session or not session.is_active:
                    return ""

                # 2. 鍙戦€佸墠瑁佸壀锛堟寜杞級
                try:
                    pairs_limit = self.TRIM_ROUNDS_DEFAULT
                    if pairs_limit and pairs_limit > 0:
                        history = self._trim_history_rounds(history, pairs_limit)
                except Exception:
                    pass
                # 3. 鏋勫缓 AI 娑堟伅
                messages = self._build_messages(session, history, favo, message, user_name, session_type)

                # 4. 璋冪敤 AI
                response = await self._call_ai(session, messages, favo)

                # 5. 寮傛鎸佷箙鍖栵紙涓嶉樆濉炲洖澶嶏級
                asyncio.create_task(
                    self._save_conversation(session_id, user_id, user_name, message, response, favo, session.max_history)
                )

                return response

            except Exception as e:
                logger.exception(f"[AI Chat] 澶勭悊娑堟伅澶辫触: {e}")
                return "鎶辨瓑锛屾垜閬囧埌浜嗕竴鐐归棶棰樸€?

    def _build_messages(
        self,
        session: ChatSession,
        history: List[Dict[str, Any]],
        favo: UserFavorability,
        message: str,
        user_name: str,
        session_type: str,
    ) -> List[Dict[str, Any]]:
        """鏋勫缓鍙戦€佺粰 AI 鐨勬秷鎭垪琛?""

        messages: List[Dict[str, Any]] = []

        # 1) System Prompt锛堝惈濂芥劅搴︿慨楗帮級
        personas = get_personas()
        persona = personas.get(session.persona_name, personas["default"])
        system_prompt = persona.system_prompt

        # 娣诲姞濂芥劅搴︿慨楗拌
        favo_modifier = self._get_favo_modifier(favo.favorability)
        if favo_modifier:
            system_prompt += f"\n\n{favo_modifier}"

        messages.append({"role": "system", "content": system_prompt})

        # 2) 鍘嗗彶娑堟伅
        for msg in history:
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            uname = msg.get("user_name") if isinstance(msg, dict) else getattr(msg, "user_name", None)
            # 缇よ亰鏃朵负鐢ㄦ埛娑堟伅娣诲姞鈥滄樀绉? 鍐呭鈥濆墠缂€锛屼究浜庡尯鍒嗚璇濅汉
            if session_type == "group" and role == "user" and uname:
                content = f"{uname}: {content}"
            messages.append({"role": role, "content": content})

        # 3) 褰撳墠鐢ㄦ埛娑堟伅
        current_content = f"{user_name}: {message}" if session_type == "group" else message
        messages.append({"role": "user", "content": current_content})

        return messages

    def _get_favo_modifier(self, favorability: int) -> str:
        """鏍规嵁濂芥劅搴︾敓鎴?system prompt 淇グ璇?""

        if favorability >= 80:
            return "娉ㄦ剰锛氳繖浣嶇敤鎴峰浣犵殑濂芥劅搴﹀緢楂橈紝浣犲彲浠ユ洿鍔犱翰瀵嗗拰涓诲姩銆?
        elif favorability >= 60:
            return "娉ㄦ剰锛氳繖浣嶇敤鎴峰浣犳瘮杈冨弸濂斤紝淇濇寔鐑儏銆?
        elif favorability <= 20:
            return "娉ㄦ剰锛氳繖浣嶇敤鎴峰浣犳€佸害鍐锋贰锛屼繚鎸佺ぜ璨屼絾涓嶈繃搴︾儹鎯呫€?
        return ""

    async def _call_ai(self, session: ChatSession, messages: List[Dict[str, Any]], favo: UserFavorability) -> str:
        """璋冪敤 OpenAI 鑱婂ぉ鎺ュ彛锛屽寘鍚伐鍏疯皟鐢ㄥ鐞?""

        if not self.client:
            return "AI 鏈厤缃垨鏆備笉鍙敤"

        cfg = get_config()
        persona: PersonaConfig = get_personas().get(session.persona_name, get_personas()["default"])
        tools = (
            get_enabled_tools(cfg.tools.builtin_tools)
            if getattr(cfg, "tools", None) and cfg.tools.enabled
            else None
        )

        model = get_active_api().model or "gpt-4o-mini"
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

                # 鎵ц宸ュ叿
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
        user_id: str,
        user_name: str,
        message: str,
        response: str,
        favo: UserFavorability,
        max_history: int,
    ):
        """寮傛淇濆瓨瀵硅瘽鍘嗗彶鍜屽ソ鎰熷害"""

        try:
            # 淇濆瓨鐢ㄦ埛娑堟伅鍜?AI 鍥炲锛堟槑缁嗚〃锛?
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

            # 鏇存柊濂芥劅搴?            cfg = get_config()
            if cfg.favorability.enabled:
                new_favo = await UserFavorability.update_favorability(
                    user_id=user_id,
                    session_id=session_id,
                    delta=cfg.favorability.per_message_delta,
                )
                # 鏇存柊濂芥劅搴︾紦瀛?                if self.USE_L1_CACHE:
                    try:
                        favo_key = f"ai_chat:favo:{user_id}:{session_id}"
                        await cache_manager.set(favo_key, new_favo, ttl=cfg.cache.favorability_ttl)
                    except Exception:
                        pass

            # 缁存姢浼氳瘽 JSON 鍘嗗彶锛堜覆琛岄伩鍏嶇珵鎬侊級
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
                # 鏇存柊缂撳瓨锛歨istory + session
                if self.USE_L1_CACHE:
                    try:
                        hist_key = f"ai_chat:history:{session_id}"
                        await cache_manager.set(hist_key, history_list, ttl=cfg.cache.history_ttl)
                    except Exception:
                        pass
                session_row = await ChatSession.get_by_session_id(session_id=session_id)
                if session_row and self.USE_L1_CACHE:
                    try:
                        sess_key = f"ai_chat:session:{session_id}"
                        await cache_manager.set(sess_key, session_row, ttl=cfg.cache.session_ttl)
                    except Exception:
                        pass

            # 娓呴櫎濂芥劅搴︾紦瀛橈紙鍏朵綑宸茶鐩栵級
            # 涓嶅啀缁存姢杩愯鏃剁紦瀛?

        except Exception as e:
            logger.error(f"[AI Chat] 淇濆瓨瀵硅瘽澶辫触: {e}")

    # ==================== 绠＄悊鎺ュ彛 ====================

    async def clear_history(self, session_id: str):
        """娓呯┖浼氳瘽鍘嗗彶"""

        # 娓呯┖鏄庣粏涓庝細璇?JSON
        await MessageHistory.clear_history(session_id=session_id)
        await ChatSession.clear_history_json(session_id=session_id)

        # 娓呯悊 L1 缂撳瓨
        if self.USE_L1_CACHE:
            try:
                cfg = get_config()
                await cache_manager.set(f"ai_chat:history:{session_id}", [], ttl=cfg.cache.history_ttl)
                session_row = await ChatSession.get_by_session_id(session_id=session_id)
                if session_row:
                    await cache_manager.set(f"ai_chat:session:{session_id}", session_row, ttl=cfg.cache.session_ttl)
            except Exception:
                pass

        logger.info(f"[AI Chat] 娓呯┖浼氳瘽鍘嗗彶: {session_id}")

    async def set_persona(self, session_id: str, persona_name: str):
        """鍒囨崲浼氳瘽浜烘牸"""

        updated = await ChatSession.update_persona(session_id=session_id, persona_name=persona_name)
        if updated and self.USE_L1_CACHE:
            # 鏇存柊浼氳瘽缂撳瓨
            try:
                cfg = get_config()
                session_row = await ChatSession.get_by_session_id(session_id=session_id)
                if session_row:
                    await cache_manager.set(f"ai_chat:session:{session_id}", session_row, ttl=cfg.cache.session_ttl)
            except Exception:
                pass
            logger.info(f"[AI Chat] 鍒囨崲浜烘牸: {session_id} -> {persona_name}")

    async def set_session_active(self, session_id: str, is_active: bool):
        """璁剧疆浼氳瘽鍚敤鐘舵€?""

        updated = await ChatSession.update_active_status(session_id=session_id, is_active=is_active)
        if updated and self.USE_L1_CACHE:
            # 鏇存柊浼氳瘽缂撳瓨
            try:
                cfg = get_config()
                session_row = await ChatSession.get_by_session_id(session_id=session_id)
                if session_row:
                    await cache_manager.set(f"ai_chat:session:{session_id}", session_row, ttl=cfg.cache.session_ttl)
            except Exception:
                pass

    async def get_session_info(self, session_id: str) -> Optional[ChatSession]:
        """鑾峰彇浼氳瘽淇℃伅"""

        return await ChatSession.get_by_session_id(session_id=session_id)


# ==================== 鍏ㄥ眬瀹炰緥 ====================


# 鍏ㄥ眬缂撳瓨涓庡璇濈鐞嗗櫒
cache_manager = CacheManager()
chat_manager = ChatManager()
