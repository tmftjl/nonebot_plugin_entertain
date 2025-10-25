"""AI 对话命令处理

包含所有命令的处理逻辑：
- 对话触发（@ 机器人）
- 会话管理（#清空会话、#会话信息、#开启AI、#关闭AI）
- 人格系统（#人格、#人格列表、#切换人格）
- 好感度（#好感度）
- 系统管理（#重载AI配置）
"""
from __future__ import annotations
import re
from typing import Optional

from nonebot import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, MessageEvent, Message
from nonebot.params import RegexMatched
from nonebot.log import logger

from ...core.framework.registry import Plugin
from ...core.framework.perm import _is_superuser, _uid, _has_group_role
from .manager import chat_manager
from .config import get_config, get_personas, reload_all, save_config
from .tools import list_tools as ai_list_tools


# 创建插件实例（带统一权限）
P = Plugin(name="ai_chat", display_name="AI 对话", enabled=True, level="all", scene="all")


# ==================== 辅助函数 ====================


def get_session_id(event: MessageEvent) -> str:
    """获取会话 ID"""

    if isinstance(event, GroupMessageEvent):
        return f"group_{event.group_id}"
    elif isinstance(event, PrivateMessageEvent):
        return f"private_{event.user_id}"
    return f"unknown_{event.user_id}"


def get_user_name(event: MessageEvent) -> str:
    """获取用户昵称"""

    try:
        sender = getattr(event, "sender", None)
        if sender:
            # 优先使用群昵称，其次用户昵称
            return getattr(sender, "card", None) or getattr(sender, "nickname", None) or str(event.user_id)
    except Exception:
        pass
    return str(event.user_id)


def is_at_bot(bot: Bot, event: MessageEvent) -> bool:
    """检查消息是否 @ 了机器人（群聊）"""

    if not isinstance(event, GroupMessageEvent):
        return False

    try:
        for seg in event.message:
            if seg.type == "at" and seg.data.get("qq") == bot.self_id:
                return True
    except Exception:
        pass
    return False


def _is_at_bot_robust(bot: Bot, event: MessageEvent) -> bool:
    """更稳健的 @ 检测：支持 at 段、[CQ:at,qq=xxx]、[at:qq=xxx]，任意位置。"""
    if not isinstance(event, GroupMessageEvent):
        return False
    try:
        for seg in event.message:
            if seg.type == "at" and seg.data.get("qq") == bot.self_id:
                return True
        raw = str(event.message)
        if f"[CQ:at,qq={bot.self_id}]" in raw or f"[at:qq={bot.self_id}]" in raw:
            return True
    except Exception:
        pass
    return False

def extract_plain_text(message: Message) -> str:
    """提取纯文本消息"""

    text_parts = []
    for seg in message:
        if seg.type == "text":
            text_parts.append(seg.data.get("text", "").strip())
    return " ".join(text_parts).strip()


async def check_admin(event: MessageEvent) -> bool:
    """检查是否为管理员（群管/群主/超级用户）"""

    user_id = _uid(event)
    if _is_superuser(user_id):
        return True
    if isinstance(event, GroupMessageEvent):
        return _has_group_role(event, "admin") or _has_group_role(event, "owner")
    return False


async def check_superuser(event: MessageEvent) -> bool:
    """检查是否为超级用户"""

    user_id = _uid(event)
    return _is_superuser(user_id)


# ==================== 对话触发命令 ====================


# 统一触发（群聊需@，私聊无需@）
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
    - 群聊：只有@机器人才触发
    - 私聊：任意文本直接触发
    """

    # 群聊必须 @ 机器人
    if isinstance(event, GroupMessageEvent) and not (
        _is_at_bot_robust(bot, event) or getattr(event, "to_me", False)
    ):
        return

    # 获取纯文本消息
    message = extract_plain_text(event.message)
    if not message:
        return

    # 获取会话信息
    session_type = "group" if isinstance(event, GroupMessageEvent) else "private"
    session_id = get_session_id(event)
    user_id = str(event.user_id)
    user_name = get_user_name(event)
    group_id = str(getattr(event, "group_id", "")) if isinstance(event, GroupMessageEvent) else None

    # 处理消息
    try:
        response = await chat_manager.process_message(
            session_id=session_id,
            user_id=user_id,
            user_name=user_name,
            message=message,
            session_type=session_type,
            group_id=group_id,
        )

        if response:
            # 去除可能的首行换行，避免开头多一个回车
            response = response.lstrip("\r\n")
            if session_type == "group":
                cfg = get_config()
                if cfg.response.enable_at_reply:
                    await at_cmd.send(Message(f"[CQ:at,qq={user_id}] {response}"))
                else:
                    await at_cmd.send(response)
            else:
                await at_cmd.send(response)
    except Exception as e:
        logger.exception(f"[AI Chat] 对话处理失败: {e}")

# 清空会话
clear_cmd = P.on_regex(r"^#清空会话$", name="ai_clear_session", display_name="清空会话", priority=5, block=True)


@clear_cmd.handle()
async def handle_clear(event: MessageEvent):
    """清空当前会话的历史记录"""

    session_id = get_session_id(event)
    try:
        await chat_manager.clear_history(session_id)
    except Exception as e:
        logger.error(f"[AI Chat] 清空会话失败: {e}")
        await clear_cmd.finish("❌ 清空会话失败")
    await clear_cmd.finish("✅ 已清空当前会话的历史记录")


# 会话信息
info_cmd = P.on_regex(r"^#会话信息$", name="ai_session_info", display_name="会话信息", priority=5, block=True)


@info_cmd.handle()
async def handle_info(event: MessageEvent):
    """查看当前会话信息"""

    session_id = get_session_id(event)
    session = await chat_manager.get_session_info(session_id)
    if not session:
        await info_cmd.finish("未找到当前会话")

    personas = get_personas()
    persona = personas.get(session.persona_name, personas.get("default"))

    status = "已启用" if session.is_active else "已禁用"
    info_text = (
        f"📊 会话信息\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"会话 ID: {session.session_id}\n"
        f"状态: {status}\n"
        f"人格: {persona.name if persona else session.persona_name}\n"
        f"最大历史: {session.max_history} 条\n"
        f"创建时间: {session.created_at[:19]}\n"
        f"更新时间: {session.updated_at[:19]}"
    )
    await info_cmd.finish(info_text)


# 开启 AI
enable_cmd = P.on_regex(
    r"^#开启AI$",
    name="ai_enable",
    display_name="开启 AI",
    priority=5,
    block=True,
    level="admin",
)


@enable_cmd.handle()
async def handle_enable(event: MessageEvent):
    """开启当前会话的 AI"""

    if not await check_admin(event):
        await enable_cmd.finish("仅管理员可用")

    session_id = get_session_id(event)
    await chat_manager.set_session_active(session_id, True)
    await enable_cmd.finish("✅ 已开启 AI")


# 关闭 AI
disable_cmd = P.on_regex(
    r"^#关闭AI$",
    name="ai_disable",
    display_name="关闭 AI",
    priority=5,
    block=True,
    level="admin",
)


@disable_cmd.handle()
async def handle_disable(event: MessageEvent):
    """关闭当前会话的 AI"""

    if not await check_admin(event):
        await disable_cmd.finish("仅管理员可用")

    session_id = get_session_id(event)
    await chat_manager.set_session_active(session_id, False)
    await disable_cmd.finish("✅ 已关闭 AI")


# ==================== 人格系统命令 ====================


# 查看当前人格
persona_cmd = P.on_regex(r"^#人格$", name="ai_persona", display_name="查看人格", priority=5, block=True)


@persona_cmd.handle()
async def handle_persona(event: MessageEvent):
    """查看当前人格"""

    session_id = get_session_id(event)
    session = await chat_manager.get_session_info(session_id)
    if not session:
        await persona_cmd.finish("未找到当前会话")

    personas = get_personas()
    persona = personas.get(session.persona_name, personas.get("default"))

    if not persona:
        await persona_cmd.finish(f"人格不存在: {session.persona_name}")

    info_text = (
        f"🎭 当前人格\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"名称: {persona.name}\n"
        f"描述: {persona.description}\n"
    )
    await persona_cmd.finish(info_text)


# 人格列表
persona_list_cmd = P.on_regex(r"^#人格列表$", name="ai_persona_list", display_name="人格列表", priority=5, block=True)


@persona_list_cmd.handle()
async def handle_persona_list(event: MessageEvent):
    """查看所有可用人格"""

    personas = get_personas()
    if not personas:
        await persona_list_cmd.finish("暂无可用人格")

    persona_lines = []
    for key, persona in personas.items():
        persona_lines.append(f"- {key}: {persona.name} - {persona.description}")

    info_text = f"🎭 可用人格列表\n━━━━━━━━━━━━━━━━\n" + "\n".join(persona_lines)
    await persona_list_cmd.finish(info_text)


# 切换人格
switch_persona_cmd = P.on_regex(
    r"^#切换人格\s+(.+)$",
    name="ai_switch_persona",
    display_name="切换人格",
    priority=5,
    block=True,
    level="admin",
)


@switch_persona_cmd.handle()
async def handle_switch_persona(event: MessageEvent):
    """切换会话人格"""
    plain_text = event.get_plaintext().strip()
    match = re.search(r"^#切换人格\s+(.+)$", plain_text)
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
    await switch_persona_cmd.finish(f"✅ 已切换到人格: {personas[persona_name].name}")


# ==================== 服务商切换命令 ====================

# 服务商列表
api_list_cmd = P.on_regex(
    r"^#服务商列表$",
    name="ai_api_list",
    display_name="服务商列表",
    priority=5,
    block=True,
)


@api_list_cmd.handle()
async def handle_api_list(event: MessageEvent):
    """查看当前配置的服务商列表"""

    cfg = get_config()
    providers = getattr(cfg, "api", []) or []

    if not providers:
        await api_list_cmd.finish("暂无服务商配置")

    lines = []
    for item in providers:
        current = "（当前）" if item.name == cfg.api_active else ""
        lines.append(
            f"- {item.name}{current} | 模型: {item.model} | 地址: {item.base_url}"
        )

    info_text = "🧩 服务商列表\n━━━━━━━━━━━━━━━━\n" + "\n".join(lines)
    await api_list_cmd.finish(info_text)


# 切换服务商
switch_api_cmd = P.on_regex(
    r"^#切换服务商\s+(.+)$",
    name="ai_switch_api",
    display_name="切换服务商",
    priority=5,
    block=True,
    level="admin",
)


@switch_api_cmd.handle()
async def handle_switch_api(event: MessageEvent, matched: str = RegexMatched()):
    """切换当前生效的 AI 服务商（按名称）"""

    plain_text = event.get_plaintext().strip()
    match = re.search(r"^#切换服务商\s+(.+)$", plain_text)
    if not match:
        logger.error(f"[AI Chat] 切换服务商 handle 触发，但 re.search 匹配失败: {plain_text}")
        await switch_persona_cmd.finish("内部错误：无法解析人格名称")
        return
    target = match.group(1).strip()
    cfg = get_config()
    names = [it.name for it in cfg.api]
    if target not in names:
        available = ", ".join(names) if names else "无"
        await switch_api_cmd.finish(f"服务商不存在\n可用: {available}")

    chat_manager.reset_client()
    await switch_api_cmd.finish(f"✅ 已切换到服务商: {target}")


# ==================== 好感度命令 ====================


# 查看好感度
favo_cmd = P.on_regex(r"^#好感度$", name="ai_favorability", display_name="查看好感度", priority=5, block=True)


@favo_cmd.handle()
async def handle_favorability(event: MessageEvent):
    """查看自己的好感度"""

    from .models import UserFavorability
    from ...db.base_models import async_maker
    from sqlmodel import select, and_

    session_id = get_session_id(event)
    user_id = str(event.user_id)

    async with async_maker() as session:
        stmt = select(UserFavorability).where(
            and_(UserFavorability.user_id == user_id, UserFavorability.session_id == session_id)
        )
        result = await session.execute(stmt)
        favo = result.scalar_one_or_none()

        if not favo:
            await favo_cmd.finish("暂无好感度记录")

        # 好感度等级
        if favo.favorability >= 80:
            level = "💕 深厚"
        elif favo.favorability >= 60:
            level = "💖 亲密"
        elif favo.favorability >= 40:
            level = "😊 友好"
        elif favo.favorability >= 20:
            level = "😐 普通"
        else:
            level = "😒 冷淡"

        info_text = (
            f"💝 好感度信息\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"好感度: {favo.favorability}/100\n"
            f"等级: {level}\n"
            f"互动次数: {favo.interaction_count}\n"
            f"正面情感: {favo.positive_count}\n"
            f"负面情感: {favo.negative_count}\n"
            f"最后互动: {favo.last_interaction[:19]}"
        )
    await favo_cmd.finish(info_text)


# ==================== 系统管理命令 ====================


# 重载配置
reload_cmd = P.on_regex(
    r"^#重载AI配置$",
    name="ai_reload_config",
    display_name="重载 AI 配置",
    priority=5,
    block=True,
    level="superuser",
)


@reload_cmd.handle()
async def handle_reload(event: MessageEvent):
    """重载 AI 配置和人格"""

    if not await check_superuser(event):
        await reload_cmd.finish("仅超级用户可用")

    reload_all()
    chat_manager.reset_client()
    await reload_cmd.finish("✅ 已重载所有配置并清空缓存")


# ==================== 工具管理 ====================

# 列出工具
tool_list_cmd = P.on_regex(r"^#工具列表$", name="ai_tools_list", display_name="工具列表", priority=5, block=True)


@tool_list_cmd.handle()
async def handle_tool_list(event: MessageEvent):
    cfg = get_config()
    all_tools = ai_list_tools()
    enabled = set(cfg.tools.builtin_tools or []) if getattr(cfg, "tools", None) else set()
    if not all_tools:
        await tool_list_cmd.finish("当前没有可用工具")
        return
    lines = ["🔧 工具列表", "━━━━━━━━━━━━━━━━"]
    for name in sorted(all_tools):
        mark = "✅ 启用" if name in enabled and cfg.tools.enabled else ("⛔ 已禁用" if name in enabled else "❌ 未启用")
        lines.append(f"- {name}  {mark}")
    lines.append("")
    lines.append(f"全局工具开关：{'开启' if cfg.tools.enabled else '关闭'}")
    await tool_list_cmd.finish("\n".join(lines))


# 开启工具（同时打开全局工具开关）
tool_on_cmd = P.on_regex(r"^#开启工具\s+(\S+)$", name="ai_tool_on", display_name="开启工具", priority=5, block=True)


@tool_on_cmd.handle()
async def handle_tool_on(event: MessageEvent, match: RegexMatched):
    if not await check_admin(event):
        await tool_on_cmd.finish("仅管理员可用")
    tool_name = match.group(1).strip()
    all_tools = set(ai_list_tools())
    if tool_name not in all_tools:
        await tool_on_cmd.finish(f"工具不存在：{tool_name}")
    cfg = get_config()
    if not getattr(cfg, "tools", None):
        await tool_on_cmd.finish("工具配置未初始化")
    enabled_list = set(cfg.tools.builtin_tools or [])
    if tool_name in enabled_list and cfg.tools.enabled:
        await tool_on_cmd.finish(f"工具已启用：{tool_name}")
    enabled_list.add(tool_name)
    cfg.tools.builtin_tools = sorted(enabled_list)
    cfg.tools.enabled = True
    save_config(cfg)
    await tool_on_cmd.finish(f"已开启工具：{tool_name}")


# 关闭工具（仅从启用列表移除，不改全局开关）
tool_off_cmd = P.on_regex(r"^#关闭工具\s+(\S+)$", name="ai_tool_off", display_name="关闭工具", priority=5, block=True)


@tool_off_cmd.handle()
async def handle_tool_off(event: MessageEvent, match: RegexMatched):
    if not await check_admin(event):
        await tool_off_cmd.finish("仅管理员可用")
    tool_name = match.group(1).strip()
    cfg = get_config()
    if not getattr(cfg, "tools", None):
        await tool_off_cmd.finish("工具配置未初始化")
    enabled_list = set(cfg.tools.builtin_tools or [])
    if tool_name not in enabled_list:
        await tool_off_cmd.finish(f"工具未启用：{tool_name}")
    enabled_list.discard(tool_name)
    cfg.tools.builtin_tools = sorted(enabled_list)
    save_config(cfg)
    await tool_off_cmd.finish(f"已关闭工具：{tool_name}")

