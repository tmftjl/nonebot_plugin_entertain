"""AI 对话插件

基于 NoneBot2 的高性能 AI 对话插件，支持多会话管理、人设与工具调用。
"""
from nonebot import require
from nonebot.log import logger

# 确保框架与数据库已初始化
require("nonebot_plugin_entertain")

# 注册并加载配置与人格
from . import config as _config  # noqa: F401
from .config import load_config, load_personas, get_config_path, get_active_api
from .manager import chat_manager  # noqa: F401

# 导入命令（注册所有命令处理器）
from . import commands  # noqa: F401

__plugin_name__ = "AI 对话"
__plugin_usage__ = (
    "AI 对话插件\n"
    "\n"
    "基础对话:\n"
    "  @机器人 <消息>  - 群聊需 @ 机器人触发；私聊直接发送\n"
    "会话管理:\n"
    "  #清空会话 / #会话信息 / #开启AI / #关闭AI\n"
    "人格系统:\n"
    "  #人格 / #人格列表 / #切换人格 <名>\n"
    "系统管理:\n"
    "  #重载AI配置 / #服务商列表 / #切换服务商 <名>\n"
)

try:
    # 加载配置
    config = load_config()
    logger.info("[AI Chat] 配置加载完成")

    # 加载人格
    personas = load_personas()
    logger.info(f"[AI Chat] 人格加载完成，共 {len(personas)} 个")

    # 检查 API 密钥（按当前启用服务商）
    active_api = get_active_api()
    if not active_api.api_key:
        logger.warning(
            "[AI Chat] ⚠️ 未配置 OpenAI API 密钥，请在配置文件中为 api 数组中的目标项设置 api_key，并选择 session.api_active\n"
            f"配置文件位置: {get_config_path()}"
        )
    else:
        logger.info("[AI Chat] OpenAI API 已配置")

    logger.success("[AI Chat] ✅ AI 对话插件加载成功")

except Exception as e:
    logger.exception(f"[AI Chat] 插件初始化失败: {e}")

