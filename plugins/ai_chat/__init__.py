"""AI 对话插件

基于 NoneBot2 的高性能 AI 对话插件，支持多会话管理、用户好感度、人格系统与工具调用。

核心特性
- 高性能：多层缓存 + 异步优化
- 简洁架构：单一核心管理器
- 权限集成：完全适配统一权限系统
- 易于扩展：装饰器注册工具，JSON 配置人格
- 生产可用：完善错误处理、日志与监控
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

# 插件元信息（仅用于展示）
__plugin_name__ = "AI 对话"
__plugin_usage__ = """
AI 对话插件

基础对话:
  @机器人 <消息>  - 群聊需 @ 机器人对话

会话管理:
  #清空会话       - 清空当前会话历史
  #会话信息       - 查看当前会话配置
  #开启AI         - 启用当前会话（管理员）
  #关闭AI         - 禁用当前会话（管理员）

人格系统:
  #人格           - 查看当前人格
  #人格列表       - 列出所有可用人格
  #切换人格 <名称> - 切换会话人格（管理员）

好感度:
  #好感度         - 查看自己的好感度

系统管理:
  #重载AI配置     - 热重载配置和人格（超级用户）
  #服务商列表     - 查看当前可用服务商
  #切换服务商     - 切换服务商
"""

# 初始化日志
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
            "[AI Chat] ⚠️ 未配置 OpenAI API 密钥，请在配置文件中设置 api[*].api_key 并选择 api_active\n"
            f"配置文件位置: {get_config_path()}"
        )
    else:
        logger.info("[AI Chat] OpenAI API 已配置")

    logger.success("[AI Chat] 🚀 AI 对话插件加载成功")

except Exception as e:
    logger.exception(f"[AI Chat] 插件初始化失败: {e}")

