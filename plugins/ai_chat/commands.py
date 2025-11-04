"""AI 对话命令处理（去除好感度 + 前后钩子已在 manager 中提供）

包含所有命令的处理逻辑：
- 对话触发（@ 机器人或主动回复）
- 会话管理（清空会话、会话信息、开启AI、关闭AI）
- 人格系统（人格、人格列表、切换人格）
- 服务商管理（列表、切换）
- 系统维护（重载AI配置）
- 工具管理（列表、开启、关闭）
"""
from __future__ import annotations

import re
from typing import List

from nonebot import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, MessageEvent, Message, MessageSegment
from nonebot.log import logger

from ...core.framework.registry import Plugin
from ...core.framework.perm import _is_superuser, _uid, _has_group_role, PermLevel, PermScene
from .manager import chat_manager
from .config import get_config, get_personas, reload_all, save_config, CFG
from .tools import list_tools as ai_list_tools
import base64
import mimetypes


P = Plugin(name="ai_chat", display_name="AI 对话", enabled=True, level=PermLevel.LOW, scene=PermScene.ALL)
def get_session_id(event: MessageEvent) -> str:
    if isinstance(event, GroupMessageEvent):
        return f"group_{event.group_id}"
    if isinstance(event, PrivateMessageEvent):
        return f"private_{event.user_id}"
    return f"unknown_{event.user_id}"


def get_user_name(event: MessageEvent) -> str:
    try:
        sender = getattr(event, "sender", None)
        if sender:
            return getattr(sender, "card", None) or getattr(sender, "nickname", None) or str(event.user_id)
    except Exception:
        pass
    return str(event.user_id)


def _is_at_bot_robust(bot: Bot, event: MessageEvent) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    try:
        for seg in event.message:
            if seg.type == "at" and seg.data.get("qq") == bot.self_id:
                return True
        raw = str(event.message)
        if f"[CQ:at,qq={bot.self_id}]" in raw or f"[at:qq={bot.self_id}]" in raw:
            return True

        # 主动回复（实验项，读取原始配置）
        cfg_raw = CFG.load() or {}
        sess = (cfg_raw.get("session") or {})
        ar = ((sess.get("chatroom_enhance") or {}).get("active_reply") or {})
        if ar.get("enable", False):
            try:
                import random as _rnd
                prob = float(ar.get("probability", 0.0) or 0.0)
            except Exception:
                prob = 0.0
            if prob > 0.0 and _rnd.random() <= prob:
                try:
                    setattr(event, "_ai_active_reply", True)
                    setattr(event, "_ai_active_reply_suffix", ar.get("prompt_suffix"))
                except Exception:
                    pass
                return True
    except Exception:
        pass
    return False


def extract_plain_text(message: Message) -> str:
    text_parts = []
    for seg in message:
        if seg.type == "text":
            text_parts.append(seg.data.get("text", "").strip())
    return " ".join(text_parts).strip()


async def extract_image_data_uris(bot: Bot, message: Message) -> List[str]:
    images: List[str] = []
    for seg in message:
        try:
            if seg.type != "image":
                continue
            data = seg.data or {}
            url = data.get("url")
            if isinstance(url, str) and (url.startswith("http://") or url.startswith("https://") or url.startswith("data:")):
                images.append(url)
                continue
            file_id = data.get("file") or data.get("image")
            if file_id:
                try:
                    info = await bot.call_api("get_image", file=file_id)
                    path = (info.get("file") or info.get("path") or "").strip()
                    if path:
                        try:
                            # 鍙€夊帇缂╋細鏍规嵁閰嶇疆缂╂斁鍒版渶闀胯竟闄愬畾锛屽苟浠?JPEG 杈撳嚭
                            from .config import get_config
                            cfg = get_config()
                            max_side = int(getattr(getattr(cfg, "input", None), "image_max_side", 0) or 0)
                            quality = int(getattr(getattr(cfg, "input", None), "image_jpeg_quality", 85) or 85)
                            if max_side > 0:
                                try:
                                    from PIL import Image
                                    import io
                                    with Image.open(path) as im:
                                        w, h = im.size
                                        scale = 1.0
                                        m = max(w, h)
                                        if m > max_side:
                                            scale = max_side / float(m)
                                        if scale < 1.0:
                                            nw, nh = int(w * scale), int(h * scale)
                                            im = im.convert("RGB")
                                            im = im.resize((nw, nh))
                                        else:
                                            im = im.convert("RGB")
                                        buf = io.BytesIO()
                                        im.save(buf, format="JPEG", quality=max(1, min(95, quality)))
                                        b = buf.getvalue()
                                        mime = "image/jpeg"
                                except Exception:
                                    with open(path, "rb") as f:
                                        b = f.read()
                                    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
                            else:
                                with open(path, "rb") as f:
                                    b = f.read()
                                mime = mimetypes.guess_type(path)[0] or "image/jpeg"
                            b64 = base64.b64encode(b).decode("ascii")
                            images.append(f"data:{mime};base64,{b64}")
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            continue
    return images

# ==================== 对话触发 ====================
# 群聊需 @ 机器人或命中“主动回复”；私聊直接触发
at_cmd = P.on_regex(
    r"^(.+)$",
    name="ai_chat_at",
    display_name="@ 机器人对话",
    priority=100,
    block=False,
)
@at_cmd.handle()
async def handle_chat_auto(bot: Bot, event: MessageEvent):
    """统一处理：
    - 群聊：只有@机器人或主动回复命中时触发
    - 私聊：任意文本直接触发
    """

    # 群聊必须 @ 机器人或主动回复
    if isinstance(event, GroupMessageEvent) and not (
        _is_at_bot_robust(bot, event) or getattr(event, "to_me", False)
    ):
        return

    message = extract_plain_text(event.message)
    images = await extract_image_data_uris(bot, event.message)
    if not message and not images:
        return

    session_type = "group" if isinstance(event, GroupMessageEvent) else "private"
    session_id = get_session_id(event)
    user_id = str(event.user_id)
    user_name = get_user_name(event)
    group_id = str(getattr(event, "group_id", "")) if isinstance(event, GroupMessageEvent) else None

    try:
        response = await chat_manager.process_message(
            session_id=session_id,
            user_id=user_id,
            user_name=user_name,
            message=message,
            session_type=session_type,
            group_id=group_id,
            active_reply=(isinstance(event, GroupMessageEvent) and bool(getattr(event, "_ai_active_reply", False))),
            active_reply_suffix=(
                getattr(
                    event,
                    "_ai_active_reply_suffix",
                    "Now, a new message is coming: `{message}`. Please react to it. Only output your response and do not output any other information.",
                )
            ),
            images=images or None,
        )

        if response:
            # 兼容：可能返回 dict（包含多模态）或 str（纯文本）
            if isinstance(response, dict):
                text = str(response.get("text") or "").lstrip("\r\n")
                images = list(response.get("images") or [])
                tts_path = response.get("tts_path")
                if text:
                    await at_cmd.send(MessageSegment.text(text))
                for img in images:
                    try:
                        await at_cmd.send(MessageSegment.image(img))
                    except Exception:
                        # 忽略失败的图片发送
                        pass
                if tts_path:
                    try:
                        await at_cmd.send(MessageSegment.record(file=str(tts_path)))
                    except Exception:
                        pass
            else:
                response = str(response).lstrip("\r\n")
                await at_cmd.send(response)
    except Exception as e:
        logger.exception(f"[AI Chat] 瀵硅瘽澶勭悊澶辫触: {e}")


# ==================== 会话管理 ====================
# 清空会话
clear_cmd = P.on_regex(r"^#清空会话$", name="ai_clear_session", display_name="清空会话", priority=5, block=True, level=PermLevel.ADMIN)
@clear_cmd.handle()
async def handle_clear(event: MessageEvent):
    session_id = get_session_id(event)
    try:
        await chat_manager.clear_history(session_id)
    except Exception as e:
        logger.error(f"[AI Chat] 清空会话失败: {e}")
        await clear_cmd.finish("× 清空会话失败")
    await clear_cmd.finish("✓ 已清空当前会话的历史记录")


# 会话信息
info_cmd = P.on_regex(r"^#会话信息$", name="ai_session_info", display_name="会话信息", priority=5, block=True)
@info_cmd.handle()
async def handle_info(event: MessageEvent):
    session_id = get_session_id(event)
    session = await chat_manager.get_session_info(session_id)
    if not session:
        await info_cmd.finish("未找到当前会话")

    personas = get_personas()
    persona = personas.get(session.persona_name, personas.get("default"))

    status = "已启用" if session.is_active else "已停用"
    cfg_now = get_config()
    rounds = int(getattr(cfg_now.session, "max_rounds", 8) or 8)
    info_text = (
        f"🧾 会话信息\n"
        f"会话 ID: {session.session_id}\n"
        f"状态: {status}\n"
        f"人格: {persona.name if persona else session.persona_name}\n"
        f"最大轮数: {rounds} 轮（历史上限约 {rounds} 条）\n"
        f"创建时间: {session.created_at[:19]}\n"
        f"更新时间: {session.updated_at[:19]}"
    )
    await info_cmd.finish(info_text)
    await info_cmd.finish(info_text)


# 开启 AI（管理员）
enable_cmd = P.on_regex(r"^#(开启|关闭)AI$", name="ai_enable", display_name="开启 AI", priority=5, block=True, level=PermLevel.ADMIN)
@enable_cmd.handle()
async def handle_enable(event: MessageEvent):
    msg_text = event.get_plaintext().strip()
    if "开启" in msg_text:
        session_id = get_session_id(event)
        await chat_manager.set_session_active(session_id, True)
        await enable_cmd.finish("✓ 已开启 AI")
    else:
        session_id = get_session_id(event)
        await chat_manager.set_session_active(session_id, False)
        await enable_cmd.finish("✓ 已关闭 AI")


# ==================== 人格系统 ====================
# 人格列表
persona_list_cmd = P.on_regex(r"^#人格列表$", name="ai_persona_list", display_name="人格列表", priority=5, block=True,level=PermLevel.ADMIN)
@persona_list_cmd.handle()
async def handle_persona_list(event: MessageEvent):
    personas = get_personas()
    if not personas:
        await persona_list_cmd.finish("暂无可用人格")

    session_id = get_session_id(event)
    session = await chat_manager.get_session_info(session_id)
    if not session:
        await persona_list_cmd.finish("未找到当前会话")

    personas = get_personas()
    persona = personas.get(session.persona_name, personas.get("default"))

    info_text = (
        f"当前人格: {persona.name}\n"
    )

    persona_lines = []
    for key, persona in personas.items():
        persona_lines.append(f"- {key}: {persona.name}")
    persona_lines.append(info_text)
    info_text = "\n".join(["🎭 可用人格列表", *persona_lines])
    await persona_list_cmd.finish(info_text)


# 切换人格（管理员）
switch_persona_cmd = P.on_regex(
    r"^#切换人格\s*(.+)$",
    name="ai_switch_persona",
    display_name="切换人格",
    priority=5,
    block=True,
    level=PermLevel.ADMIN,
)
@switch_persona_cmd.handle()
async def handle_switch_persona(event: MessageEvent):
    plain_text = event.get_plaintext()
    match = re.search(r"^#切换人格\s*(.+)$", plain_text)
    if not match:
        logger.error(f"[AI Chat] 切换人格 handle 触发，但 re.search 匹配失败: {plain_text}")
        await switch_persona_cmd.finish("内部错误：无法解析人格名称")
        return

    persona_name = match.group(1).strip()
    personas = get_personas()

    if persona_name not in personas:
        available = ", ".join(personas.keys())
        await switch_persona_cmd.finish(f"人格不存在\n可用人格: {available}")

    session_id = get_session_id(event)
    await chat_manager.set_persona(session_id, persona_name)
    await switch_persona_cmd.finish(f"✓ 已切换到人格: {personas[persona_name].name}")


# ==================== 服务商管理 ====================
# 服务商列表（超管）
api_list_cmd = P.on_regex(
    r"^#服务商列表$",
    name="ai_api_list",
    display_name="服务商列表",
    priority=5,
    block=True,
    level=PermLevel.SUPERUSER,
)
@api_list_cmd.handle()
async def handle_api_list(event: MessageEvent):
    cfg = get_config()
    providers = dict(getattr(cfg, "api", {}) or {})  # { name: APIItem }

    if not providers:
        await api_list_cmd.finish("暂无服务商配置")

    active = getattr(getattr(cfg, "session", None), "api_active", "") or ""
    lines = []
    for name, item in providers.items():
        try:
            model = getattr(item, "model", "")
            base_url = getattr(item, "base_url", "")
        except Exception:
            # 兼容可能为原始 dict 的情况
            model = (item or {}).get("model", "")  # type: ignore[assignment]
            base_url = (item or {}).get("base_url", "")  # type: ignore[assignment]
        mark = "（当前）" if name == active else ""
        lines.append(f"- {name}{mark} | 模型: {model}")

    info_text = "\n".join(["🧩 服务商列表", *lines])
    await api_list_cmd.finish(info_text)


# 切换服务商（超管）
switch_api_cmd = P.on_regex(
    r"^#切换服务商\s*(.+)$",
    name="ai_switch_api",
    display_name="切换服务商",
    priority=5,
    block=True,
    level=PermLevel.SUPERUSER,
)
@switch_api_cmd.handle()
async def handle_switch_api(event: MessageEvent):
    plain_text = event.get_plaintext()
    m = re.search(r"^#切换服务商\s*(.+)$", plain_text)
    if not m:
        await switch_api_cmd.finish("内部错误：无法解析服务商名称")
        return
    target = m.group(1).strip()
    cfg = get_config()
    names = list((getattr(cfg, "api", {}) or {}).keys())
    if target not in names:
        available = ", ".join(names) if names else ""
        await switch_api_cmd.finish(f"服务商不存在\n可用: {available}")

    # 更新当前启用的服务商并保存配置
    cfg.session.api_active = target
    save_config(cfg)
    chat_manager.reset_client()
    await switch_api_cmd.finish(f"✓ 已切换到服务商 {target}")

# ==================== 系统管理 ====================
# 重载配置（超级用户）
reload_cmd = P.on_regex(
    r"^#重载AI配置$",
    name="ai_reload_config",
    display_name="重载 AI 配置",
    priority=5,
    block=True,
    level=PermLevel.SUPERUSER,
)
@reload_cmd.handle()
async def handle_reload(event: MessageEvent):
    reload_all()
    chat_manager.reset_client()
    await reload_cmd.finish("✓ 已重载所有配置并清空缓存")


# ==================== 工具管理 ====================
# 列出工具
tool_list_cmd = P.on_regex(r"^#工具列表$", name="ai_tools_list", display_name="工具列表", priority=5, block=True,level=PermLevel.SUPERUSER)
@tool_list_cmd.handle()
async def handle_tool_list(event: MessageEvent):
    cfg = get_config()
    all_tools = ai_list_tools()
    enabled = set(cfg.tools.builtin_tools or []) if getattr(cfg, "tools", None) else set()
    if not all_tools:
        await tool_list_cmd.finish("当前没有可用工具")
        return
    lines = ["🔧 工具列表"]
    for name in sorted(all_tools):
        mark = "✓ 启用" if name in enabled and cfg.tools.enabled else ("× 已禁用" if name in enabled else "× 未启用")
        lines.append(f"- {name}  {mark}")
    lines.append("")
    lines.append(f"全局工具开关：{'开启' if cfg.tools.enabled else '关闭'}")
    await tool_list_cmd.finish("\n".join(lines))


# 工具开关
tool_on_cmd = P.on_regex(r"^#(开启|关闭)工具\s*(\S+)$", name="ai_tool_on", display_name="开启工具", priority=5, block=True,level=PermLevel.SUPERUSER)
@tool_on_cmd.handle()
async def handle_tool_on(event: MessageEvent):
    plain_text = event.get_plaintext()
    m = re.search(r"^#(开启|关闭)工具\s*(\S+)$", plain_text)   
    action = m.group(1).strip()  # "开启" 或 "关闭"
    tool_name = m.group(2).strip() # 工具名
    cfg = get_config()
    if not getattr(cfg, "tools", None):
        await tool_on_cmd.finish("工具配置未初始化")
    enabled_list = set(cfg.tools.builtin_tools or [])
    if action == "开启":
        all_tools = set(ai_list_tools())
        if tool_name not in all_tools:
            await tool_on_cmd.finish(f"工具不存在：{tool_name}")    
        if tool_name in enabled_list:
            await tool_on_cmd.finish(f"工具已启用：{tool_name}")
        enabled_list.add(tool_name)
        cfg.tools.builtin_tools = sorted(enabled_list)
        save_config(cfg)
        await tool_on_cmd.finish(f"已开启工具：{tool_name}") 
    elif action == "关闭":
        if tool_name not in enabled_list:
            await tool_on_cmd.finish(f"工具未启用：{tool_name}")
        enabled_list.discard(tool_name)
        cfg.tools.builtin_tools = sorted(enabled_list)
        save_config(cfg)
        await tool_on_cmd.finish(f"已关闭工具：{tool_name}")


# TTS开关
tts_on_cmd = P.on_regex(r"^#(开启|关闭)TTS$", name="ai_tts_on", display_name="开关TTS", priority=5, block=True, level=PermLevel.SUPERUSER)
@tts_on_cmd.handle()
async def handle_tts_on(event: MessageEvent):
    cfg = get_config()
    if not getattr(cfg, "output", None):
        await tts_on_cmd.finish("TTS未配置")
    msg_text = event.get_plaintext().strip()
    
    if msg_text == "#开启TTS":
        if cfg.output.tts_enable:
            await tts_on_cmd.finish("TTS已经是开启状态，无需重复操作")
        else:
            cfg.output.tts_enable = True
            save_config(cfg)
            await tts_on_cmd.finish("TTS已成功开启")
            
    elif msg_text == "#关闭TTS":
        if not cfg.output.tts_enable:
            await tts_on_cmd.finish("TTS已经是关闭状态，无需重复操作")
        else:
            cfg.output.tts_enable = False
            save_config(cfg)
            await tts_on_cmd.finish("TTS已成功关闭")