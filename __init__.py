from __future__ import annotations

from pathlib import Path
from nonebot.log import logger
from nonebot import get_driver, load_plugins
from nonebot.plugin import PluginMetadata


driver = get_driver()


__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-entertain",
    description=(
        "娱乐合集：注册时间查询、doro 抽卡、打卡、点歌、群工具等"
    ),
    usage=(
        "- #注册时间 [@QQ 或 QQ号]\n"
        "- #doro抽卡 / #十连doro抽卡 / #百连doro抽卡\n"
        "- #每日打卡\n"
        "- 点歌/选歌（musicshare）\n"
        "- 群工具\n"
        "- 踢出 [@QQ 或 QQ号]"
    ),
    type="application",
    homepage="",
    supported_adapters={"~onebot.v11"},
)


# 启动时初始化统一配置与权限文件
try:
    from .core.framework.config import bootstrap_configs

    @driver.on_startup
    async def _entertain_bootstrap_configs():
        try:
            bootstrap_configs()
        except Exception:
            pass
except Exception:
    pass

# 启动时初始化数据库（SQLite/SQLModel）
try:
    from .db.base_models import init_database

    @driver.on_startup
    async def _entertain_init_database():
        try:
            logger.info("--> 正在执行 nonebot-plugin-entertain 的数据库初始化...")
            await init_database()
            logger.success("--> nonebot-plugin-entertain 数据库初始化完成。")
        except Exception as e:
            # 修改这里！打印详细的错误信息和堆栈跟踪
            logger.error("!!! nonebot-plugin-entertain 数据库初始化失败，请检查下面的错误 !!!")
            logger.exception(e)
except Exception:
    pass


def _load_subplugins_via_nonebot() -> None:
    """加载内部 plugins 目录下的子插件（交给 NoneBot 处理）。"""
    try:
        base = Path(__file__).parent / "plugins"
        if base.exists():
            load_plugins(str(base))
    except Exception:
        # 避免因单个插件失败影响整体加载
        pass


_load_subplugins_via_nonebot()

def _load_system_via_nonebot() -> None:
    """加载内部 commands 目录下的系统插件（交给 NoneBot 处理）。"""
    try:
        base = Path(__file__).parent / "commands"
        if base.exists():
            load_plugins(str(base))
    except Exception:
        # 避免因单个插件失败影响整体加载
        pass

_load_system_via_nonebot()


# 启动时尝试将旧版 JSON 数据迁移至数据库（仅在数据库为空时执行）
try:
    from .db.migrate import migrate_legacy_json_on_startup

    @driver.on_startup
    async def _entertain_migrate_legacy_json():
        try:
            await migrate_legacy_json_on_startup()
        except Exception as e:
            logger.debug("[membership] 旧版数据迁移过程出现异常（已忽略）")
            logger.exception(e)
except Exception:
    pass
