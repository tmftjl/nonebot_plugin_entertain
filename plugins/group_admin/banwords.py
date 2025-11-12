# from __future__ import annotations

# import json
# from typing import Dict, List, Tuple
# from threading import RLock

# from nonebot import on_message
# from nonebot.matcher import Matcher
# from nonebot.params import RegexGroup
# from nonebot.log import logger
# from nonebot.adapters.onebot.v11 import (
#     Bot,
#     Message,
#     MessageEvent,
#     GroupMessageEvent,
#     MessageSegment,
# )

# from ...core.api import plugin_data_dir
# from . import _P as P
# from ...core.framework.perm import PermLevel, PermScene


 

# DATA_DIR = plugin_data_dir("group_admin")
# BAN_FILE = DATA_DIR / "banned_words.json"

# # In-memory cache to avoid decoding JSON on every message
# _BAN_CACHE: Dict[str, Dict[str, object]] = {}
# _BAN_CACHE_MTIME: float = -1.0
# _BAN_CACHE_LOCK = RLock()


# def _group_key(event: MessageEvent) -> str | None:
#     gid = getattr(event, "group_id", None)
#     return str(gid) if gid is not None else None


# def _load_ban_store() -> Dict[str, Dict[str, object]]:
#     """Load ban store from disk (uncached)."""
#     try:
#         if BAN_FILE.exists():
#             data = json.loads(BAN_FILE.read_text(encoding="utf-8"))
#             if isinstance(data, dict):
#                 return data
#     except Exception:
#         pass
#     return {}


# def _load_ban_store_cached() -> Dict[str, Dict[str, object]]:
#     """Fast path for frequent reads in on_message interceptor.

#     Uses file mtime to invalidate cache. Falls back to empty dict on errors.
#     """
#     global _BAN_CACHE_MTIME
#     try:
#         mtime = BAN_FILE.stat().st_mtime if BAN_FILE.exists() else -1.0
#     except Exception:
#         mtime = -2.0
#     with _BAN_CACHE_LOCK:
#         if _BAN_CACHE and _BAN_CACHE_MTIME == mtime:
#             return _BAN_CACHE
#         data = _load_ban_store()
#         _BAN_CACHE.clear()
#         if isinstance(data, dict):
#             _BAN_CACHE.update(data)
#         _BAN_CACHE_MTIME = mtime
#         return _BAN_CACHE


# def _save_ban_store(data: Dict[str, Dict[str, object]]) -> None:
#     """Persist store and refresh in-memory cache."""
#     global _BAN_CACHE_MTIME
#     try:
#         DATA_DIR.mkdir(parents=True, exist_ok=True)
#         BAN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
#         # Refresh cache after successful write
#         with _BAN_CACHE_LOCK:
#             _BAN_CACHE.clear()
#             _BAN_CACHE.update(data or {})
#             try:
#                 _BAN_CACHE_MTIME = BAN_FILE.stat().st_mtime
#             except Exception:
#                 _BAN_CACHE_MTIME = -1.0
#     except Exception:
#         pass


# banword_on = P.on_regex(
#     r"^#开启违禁词$",
#     name="banword_on",
#     display_name="开启违禁词",
#     priority=5,
#     block=True,
#     enabled=True,
#     level=PermLevel.ADMIN,
#     scene=PermScene.GROUP,
# )


# @banword_on.handle()
# async def _banword_on(matcher: Matcher, event: MessageEvent):
#     if not isinstance(event, GroupMessageEvent):
#         await matcher.finish("请在群聊中使用")
#     # Use cached store for high-frequency path
#     store = _load_ban_store_cached()
#     key = _group_key(event)
#     rec = store.get(key or "") or {}
#     rec.setdefault("words", [])
#     rec["enabled"] = True
#     rec.setdefault("action", "recall")
#     rec.setdefault("mute_seconds", 300)
#     rec.setdefault("exempt_admin", True)
#     store[key or ""] = rec
#     _save_ban_store(store)
#     await matcher.finish("已开启违禁词检测")


# banword_off = P.on_regex(
#     r"^#关闭违禁词$",
#     name="banword_off",
#     display_name="关闭违禁词",
#     priority=5,
#     block=True,
#     enabled=True,
#     level=PermLevel.ADMIN,
#     scene=PermScene.GROUP,
# )


# @banword_off.handle()
# async def _banword_off(matcher: Matcher, event: MessageEvent):
#     if not isinstance(event, GroupMessageEvent):
#         await matcher.finish("请在群聊中使用")
#     store = _load_ban_store()
#     key = _group_key(event)
#     rec = store.get(key or "") or {}
#     rec["enabled"] = False
#     store[key or ""] = rec
#     _save_ban_store(store)
#     await matcher.finish("已关闭违禁词检测")


# banword_add = P.on_regex(
#     r"^#添加违禁词\s*(.+)$",
#     name="banword_add",
#     display_name="添加违禁词",
#     priority=5,
#     block=True,
#     enabled=True,
#     level=PermLevel.ADMIN,
#     scene=PermScene.GROUP,
# )


# @banword_add.handle()
# async def _banword_add(matcher: Matcher, event: MessageEvent, groups: Tuple = RegexGroup()):
#     if not isinstance(event, GroupMessageEvent):
#         await matcher.finish("请在群聊中使用")
#     word = (groups[0] or "").strip()
#     if not word:
#         await matcher.finish("请提供要添加的违禁词")
#     store = _load_ban_store()
#     key = _group_key(event) or ""
#     rec = store.get(key) or {"enabled": True, "words": [], "action": "recall", "mute_seconds": 300, "exempt_admin": True}
#     words: List[str] = list(rec.get("words", []))
#     if word not in words:
#         words.append(word)
#     rec["words"] = words
#     store[key] = rec
#     _save_ban_store(store)
#     await matcher.finish("已添加")


# banword_del = P.on_regex(
#     r"^#删除违禁词\s*(.+)$",
#     name="banword_del",
#     display_name="删除违禁词",
#     priority=5,
#     block=True,
#     enabled=True,
#     level=PermLevel.ADMIN,
#     scene=PermScene.GROUP,
# )


# @banword_del.handle()
# async def _banword_del(matcher: Matcher, event: MessageEvent, groups: Tuple = RegexGroup()):
#     if not isinstance(event, GroupMessageEvent):
#         await matcher.finish("请在群聊中使用")
#     word = (groups[0] or "").strip()
#     if not word:
#         await matcher.finish("请提供要删除的违禁词")
#     store = _load_ban_store()
#     key = _group_key(event) or ""
#     rec = store.get(key) or {}
#     words: List[str] = list(rec.get("words", []))
#     if word in words:
#         words.remove(word)
#     rec["words"] = words
#     store[key] = rec
#     _save_ban_store(store)
#     await matcher.finish("已删除")


# banword_clear = P.on_regex(
#     r"^#清空违禁词$",
#     name="banword_clear",
#     display_name="清空违禁词",
#     priority=5,
#     block=True,
#     enabled=True,
#     level=PermLevel.ADMIN,
#     scene=PermScene.GROUP,
# )


# @banword_clear.handle()
# async def _banword_clear(matcher: Matcher, event: MessageEvent):
#     if not isinstance(event, GroupMessageEvent):
#         await matcher.finish("请在群聊中使用")
#     store = _load_ban_store()
#     key = _group_key(event) or ""
#     rec = store.get(key) or {}
#     rec["words"] = []
#     store[key] = rec
#     _save_ban_store(store)
#     await matcher.finish("已清空")


# banword_list = P.on_regex(
#     r"^#违禁词列表$",
#     name="banword_list",
#     display_name="违禁词列表",
#     priority=5,
#     block=True,
#     enabled=True,
#     level=PermLevel.ADMIN,
#     scene=PermScene.GROUP,
# )


# @banword_list.handle()
# async def _banword_list(matcher: Matcher, event: MessageEvent):
#     if not isinstance(event, GroupMessageEvent):
#         await matcher.finish("请在群聊中使用")
#     store = _load_ban_store()
#     key = _group_key(event) or ""
#     rec = store.get(key) or {}
#     words: List[str] = list(rec.get("words", []))
#     enabled = bool(rec.get("enabled", False))
#     action = str(rec.get("action", "recall"))
#     mute_seconds = int(rec.get("mute_seconds", 300) or 300)
#     status = "开启" if enabled else "关闭"
#     if not words:
#         await matcher.finish(f"违禁词检测：{status}\n动作：{action}\n时长：{mute_seconds}s\n暂无词条")
#     await matcher.finish(
#         "\n".join(
#             [
#                 f"违禁词检测：{status}",
#                 f"动作：{action}",
#                 f"时长：{mute_seconds}s",
#                 "词条：" + ", ".join(words[:100]),
#             ]
#         )
#     )


# banword_action = P.on_regex(
#     r"^#违禁词动作\s*(警告|撤回|禁言)$",
#     name="banword_action",
#     display_name="违禁词动作",
#     priority=5,
#     block=True,
#     enabled=True,
#     level=PermLevel.ADMIN,
#     scene=PermScene.GROUP,
# )


# @banword_action.handle()
# async def _banword_action(matcher: Matcher, event: MessageEvent, groups: Tuple = RegexGroup()):
#     if not isinstance(event, GroupMessageEvent):
#         await matcher.finish("请在群聊中使用")
#     action_cn = (groups[0] or "").strip()
#     mapping = {"警告": "warn", "撤回": "recall", "禁言": "mute"}
#     action = mapping.get(action_cn, "recall")
#     store = _load_ban_store()
#     key = _group_key(event) or ""
#     rec = store.get(key) or {}
#     rec["action"] = action
#     store[key] = rec
#     _save_ban_store(store)
#     await matcher.finish(f"已设置违禁词动作为：{action_cn}")


# banword_mute_seconds = P.on_regex(
#     r"^#违禁词时长\s*(\d+[a-zA-Z\u4e00-\u9fa5]*)$",
#     name="banword_mute_seconds",
#     display_name="违禁词禁言时长",
#     priority=5,
#     block=True,
#     enabled=True,
#     level=PermLevel.ADMIN,
#     scene=PermScene.GROUP,
# )


# @banword_mute_seconds.handle()
# async def _banword_mute_seconds(matcher: Matcher, event: MessageEvent, groups: Tuple = RegexGroup()):
#     if not isinstance(event, GroupMessageEvent):
#         await matcher.finish("请在群聊中使用")
#     from .utils import parse_duration_to_seconds

#     sec = parse_duration_to_seconds((groups[0] or "").strip(), 300)
#     store = _load_ban_store()
#     key = _group_key(event) or ""
#     rec = store.get(key) or {}
#     rec["mute_seconds"] = int(sec)
#     store[key] = rec
#     _save_ban_store(store)
#     await matcher.finish(f"已设置违禁词禁言时长为 {sec} 秒")


# banword_exempt = P.on_regex(
#     r"^#违禁词管理员保护\s*(开启|关闭)$",
#     name="banword_exempt",
#     display_name="违禁词管理员保护",
#     priority=5,
#     block=True,
#     enabled=True,
#     level=PermLevel.ADMIN,
#     scene=PermScene.GROUP,
# )


# @banword_exempt.handle()
# async def _banword_exempt(matcher: Matcher, event: MessageEvent, groups: Tuple = RegexGroup()):
#     if not isinstance(event, GroupMessageEvent):
#         await matcher.finish("请在群聊中使用")
#     onoff = (groups[0] or "").strip()
#     val = True if onoff == "开启" else False
#     store = _load_ban_store()
#     key = _group_key(event) or ""
#     rec = store.get(key) or {}
#     rec["exempt_admin"] = val
#     store[key] = rec
#     _save_ban_store(store)
#     await matcher.finish(f"管理员保护：{onoff}")


# # 违禁词拦截器
# banwatch = on_message(priority=98, block=False, permission=P.permission())


# def _sender_is_admin(event: GroupMessageEvent) -> bool:
#     try:
#         role = getattr(getattr(event, "sender", None), "role", None)
#         return str(role) in {"admin", "owner"}
#     except Exception:
#         return False


# def _is_superuser(event: MessageEvent) -> bool:
#     try:
#         from nonebot import get_driver

#         su = set(get_driver().config.superusers)  # type: ignore[attr-defined]
#         return str(getattr(event, "user_id", "")) in {str(x) for x in su}
#     except Exception:
#         return False


# @banwatch.handle()
# async def _(bot: Bot, event: MessageEvent):
#     if not isinstance(event, GroupMessageEvent):
#         return
#     key = _group_key(event)
#     if not key:
#         return
#     store = _load_ban_store()
#     rec = store.get(key) or {}
#     if not rec or not rec.get("enabled", False):
#         return
#     if rec.get("exempt_admin", True) and (_sender_is_admin(event) or _is_superuser(event)):
#         return
#     words: List[str] = list(rec.get("words", []))
#     if not words:
#         return
#     text = event.get_plaintext() or ""
#     hit = None
#     for w in words:
#         try:
#             if w and w in text:
#                 hit = w
#                 break
#         except Exception:
#             continue
#     if not hit:
#         return
#     action = str(rec.get("action", "recall"))
#     mute_seconds = int(rec.get("mute_seconds", 300) or 300)
#     try:
#         if action in ("recall", "mute"):
#             try:
#                 await bot.delete_msg(message_id=event.message_id)
#             except Exception:
#                 pass
#         if action == "mute":
#             try:
#                 await bot.set_group_ban(group_id=event.group_id, user_id=event.user_id, duration=max(1, mute_seconds))
#             except Exception:
#                 pass
#         if action == "warn":
#             await bot.send_group_msg(
#                 group_id=event.group_id,
#                 message=MessageSegment.at(event.user_id) + Message(f" 触发违禁词：{hit}"),
#             )
#     except Exception as e:
#         logger.debug(f"违禁词处理异常: {e}")

