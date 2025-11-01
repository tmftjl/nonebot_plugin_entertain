"""AI 对话命令处理（简化配置结构后的版本）

包含所有命令的处理逻辑：
- 对话触发：群聊需 @ 或‘主动回复’命中；私聊直接触发
- 会话管理：清空/查看信息/开启AI/关闭AI
- 人格系统：查看/列表/切换人格
- 服务商管理：列表/切换
- 系统管理：重载配置
- 工具管理：列表/启用/禁用
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
from .config import get_config, get_personas, reload_all, save_config, CFG
from .tools import list_tools as ai_list_tools


# 创建插件实例（带统一权限）
P = Plugin(name="ai_chat", display_name="AI 对话", enabled=True, level="all", scene="all")


# ==================== 辅助函数 ====================


def get_session_id(event: MessageEvent) -> str:
    if isinstance(event, GroupMessageEvent):
        return f"group_{event.group_id}"
    elif isinstance(event, PrivateMessageEvent):
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

        # 主动回复（实验项，读取最新配置）
        cfg_raw = CFG.load() or {}
        sess = (cfg_raw.get("session") or {})
        if bool(sess.get("active_reply_enable", False)):
            try:
                import random as _rnd
                prob = float(sess.get("active_reply_probability", 0.0) or 0.0)
            except Exception:
                prob = 0.0
            if prob > 0.0 and _rnd.random() <= prob:
                try:
                    setattr(event, "_ai_active_reply", True)
                    setattr(event, "_ai_active_reply_suffix", sess.get("active_reply_prompt_suffix"))
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


async def check_admin(event: MessageEvent) -> bool:
    user_id = _uid(event)
    if _is_superuser(user_id):
        return True
    if isinstance(event, GroupMessageEvent):
        return _has_group_role(event, "admin") or _has_group_role(event, "owner")
    return False


async def check_superuser(event: MessageEvent) -> bool:
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
    - 群聊：仅当@机器人或命中“主动回复”时触发
    - 私聊：纯文本直接触发
    """

    # 群聊必须 @ 机器人或主动回复
    if isinstance(event, GroupMessageEvent) and not (
        _is_at_bot_robust(bot, event) or getattr(event, "to_me", False)
    ):
        return

    message = extract_plain_text(event.message)
    if not message:
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
        )

        if response:
            response = response.lstrip("\r\n")
            await at_cmd.send(response)
    except Exception as e:
        logger.exception(f"[AI Chat] 对话处理失败: {e}")


# 清空会话
clear_cmd = P.on_regex(r"^#清空会话$", name="ai_clear_session", display_name="清空会话", priority=5, block=True)


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
        f"━━━━━━━━━━━━━━━━\n"
        f"会话 ID: {session.session_id}\n"
        f"状态: {status}\n"
        f"人格: {persona.name if persona else session.persona_name}\n"
        f"最大轮数: {rounds} 轮（历史上限约 {rounds} 条）\n"
        f"创建时间: {session.created_at[:19]}\n"
        f"更新时间: {session.updated_at[:19]}"
    )
    await info_cmd.finish(info_text)


# 开启 AI（管理员）
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
    if not await check_admin(event):
        await enable_cmd.finish("需管理员可用")
    session_id = get_session_id(event)
    await chat_manager.set_session_active(session_id, True)
    await enable_cmd.finish("✓ 已开启 AI")


# 关闭 AI（管理员）
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
    if not await check_admin(event):
        await disable_cmd.finish("需管理员可用")
    session_id = get_session_id(event)
    await chat_manager.set_session_active(session_id, False)
    await disable_cmd.finish("✓ 已关闭 AI")


# ==================== 人格系统 ====================


# 查看当前人格
persona_cmd = P.on_regex(r"^#人格$", name="ai_persona", display_name="查看人格", priority=5, block=True)


@persona_cmd.handle()
async def handle_persona(event: MessageEvent):
    session_id = get_session_id(event)
    session = await chat_manager.get_session_info(session_id)
    if not session:
        await persona_cmd.finish("未找到当前会话")

    personas = get_personas()
    persona = personas.get(session.persona_name, personas.get("default"))

    if not persona:
        await persona_cmd.finish(f"人格不存在: {session.persona_name}")

    info_text = (
        f"🧠 当前人格\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"名称: {persona.name}\n"
        f"详情: {persona.details}\n"
    )
    await persona_cmd.finish(info_text)


# 人格列表
persona_list_cmd = P.on_regex(r"^#人格列表$", name="ai_persona_list", display_name="人格列表", priority=5, block=True)


@persona_list_cmd.handle()
async def handle_persona_list(event: MessageEvent):
    personas = get_personas()
    if not personas:
        await persona_list_cmd.finish("暂无可用人格")

    persona_lines = []
    for key, persona in personas.items():
        persona_lines.append(f"- {persona.name}")

    info_text = f"🧠 可用人格列表\n━━━━━━━━━━━━━━━━\n" + "\n".join(persona_lines)
    await persona_list_cmd.finish(info_text)


# 切换人格（管理员）
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
    plain_text = event.get_plaintext().strip()
    match = re.search(r"^#切换人格\s+(.+)$", plain_text)
    if not match:
        logger.error(f"[AI Chat] 切换人格 handle 触发但未匹配: {plain_text}")
        await switch_persona_cmd.finish("内部错误：无法解析人格名字")
        return

    persona_name = match.group(1).strip()
    personas = get_personas()
    # 严格使用名字，不再兼容旧的代号/显示名混用
    if persona_name not in personas:
        available = ', '.join(sorted([p.name for p in personas.values()]))
        await switch_persona_cmd.finish(f"人格不存在\n可用人格: {available}")

    if persona_name not in personas:

        _k = None

        for k, p in personas.items():

            if p.name == persona_name:

                _k = k

                break

        if _k:

            persona_name = _k

        else:

            available = ', '.join(sorted([p.name for p in personas.values()]))

            await switch_persona_cmd.finish(f'人格不存在\n可用人格: {available}')


    session_id = get_session_id(event)
    await chat_manager.set_persona(session_id, persona_name)
    await switch_persona_cmd.finish(f"✓ 已切换到人格: {personas[persona_name].name}")


# ==================== 服务商切换 ====================


# 服务商列表
api_list_cmd = P.on_regex(
    r"^#服务商列表",
    name="ai_api_list",
    display_name="服务商列表",
    priority=5,
    block=True,
)


@api_list_cmd.handle()
async def handle_api_list(event: MessageEvent):
    cfg = get_config()
    providers = getattr(cfg, "api", {}) or {}
    # 当前激活服务商
    active_name = cfg.session.api_active

    if not providers:
        await api_list_cmd.finish("暂无服务商配置")

    lines = []
    for name, item in providers.items():
        model = item.model
        base_url = item.base_url
        current = "（当前）" if (active_name and name == active_name) else ""
        lines.append(f"- {name}{current} | 模型: {model} | 地址: {base_url}")

    info_text = "🧩 服务商列表\n━━━━━━━━━━━━━━━━\n" + "\n".join(lines)
    await api_list_cmd.finish(info_text)


# 切换服务商（管理员）
switch_api_cmd = P.on_regex(
    r"^#切换服务商\s+(.+)$",
    name="ai_switch_api",
    display_name="切换服务商",
    priority=5,
    block=True,
    level="admin",
)


@switch_api_cmd.handle()
async def handle_switch_api(event: MessageEvent):
    plain_text = event.get_plaintext().strip()
    m = re.search(r"^#切换服务商\s+(.+)$", plain_text)
    if not m:
        await switch_api_cmd.finish("内部错误：无法解析服务商名称")
        return
    target = m.group(1).strip()
    cfg = get_config()
    names = list((cfg.api or {}).keys())
    if target not in names:
        available = ", ".join(names) if names else ""
        await switch_api_cmd.finish(f"服务商不存在\n可用: {available}")

    # 更新当前启用的服务商并保存配置
    cfg.session.api_active = target
    save_config(cfg)
    # 重建客户端以应用新的服务商配置
    chat_manager.reset_client()
    await switch_api_cmd.finish(f"✓ 已切换到服务商 {target}")


# ==================== 系统管理命令 ====================


# 重载配置（超管）
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
    if not await check_superuser(event):
        await reload_cmd.finish("需超管可用")

    reload_all()
    chat_manager.reset_client()
    await reload_cmd.finish("✓ 已重载所有配置并清空缓存")


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
    lines = ["🛠️ 工具列表", "━━━━━━━━━━━━━━━━"]
    for name in sorted(all_tools):
        mark = "✓ 启用" if name in enabled and cfg.tools.enabled else ("× 已停用" if name in enabled else "× 未启用")
        lines.append(f"- {name}  {mark}")
    lines.append("")
    lines.append(f"全局工具开关：{'开启' if cfg.tools.enabled else '关闭'}")
    await tool_list_cmd.finish("\n".join(lines))


# 启用工具（管理员，且打开全局开关）
tool_on_cmd = P.on_regex(r"^#启用工具\s+(\S+)$", name="ai_tool_on", display_name="启用工具", priority=5, block=True)


@tool_on_cmd.handle()
async def handle_tool_on(event: MessageEvent):
    if not await check_admin(event):
        await tool_on_cmd.finish("需管理员可用")
    plain_text = event.get_plaintext().strip()
    m = re.search(r"^#启用工具\s+(\S+)$", plain_text)
    if not m:
        await tool_on_cmd.finish("格式错误：请使用 #启用工具 工具名")
    tool_name = m.group(1).strip()
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
    await tool_on_cmd.finish(f"已启用工具：{tool_name}")


# 关闭工具（管理员，仅从启用列表移除，不改全局开关）
tool_off_cmd = P.on_regex(r"^#关闭工具\s+(\S+)$", name="ai_tool_off", display_name="关闭工具", priority=5, block=True)


@tool_off_cmd.handle()
async def handle_tool_off(event: MessageEvent):
    if not await check_admin(event):
        await tool_off_cmd.finish("需管理员可用")
    plain_text = event.get_plaintext().strip()
    m = re.search(r"^#关闭工具\s+(\S+)$", plain_text)
    if not m:
        await tool_off_cmd.finish("格式错误：请使用 #关闭工具 工具名")
    tool_name = m.group(1).strip()
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
