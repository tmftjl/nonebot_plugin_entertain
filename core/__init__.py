from __future__ import annotations

from nonebot import get_driver
from nonebot.log import logger

# 挂载 Web 控制台（需要在系统配置中开启）
# 注意：推迟到启动阶段再导入 console.server，避免在插件加载前提前导入其内部引用的子插件。
driver = get_driver()


@driver.on_startup
async def _mount_web_console() -> None:
    try:
        from ..console.server import setup_web_console as _setup

        _setup()
    except Exception as e:
        logger.warning(f"membership Web 控制台挂载失败: {e}")
        pass

