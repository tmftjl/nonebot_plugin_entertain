from __future__ import annotations

from pathlib import Path

from nonebot import get_driver, load_plugins
from nonebot.plugin import PluginMetadata


driver = get_driver()


__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-entertain",
    description=(
        "娱乐插件合集：注册时间查询、doro 结局、发病语录、音乐点歌、今日运势、开盒等"
    ),
    usage=(
        "- #注册时间 [@QQ 或 QQ号]\n"
        "- #doro结局 / #随机doro结局 / #今日doro结局\n"
        "- #发病语录\n"
        "- 点歌/选曲（musicshare）\n"
        "- 今日运势\n"
        "- 开盒 [@QQ 或 QQ号]"
    ),
    type="application",
    homepage="",
    supported_adapters={"~onebot.v11"},
)


# Bootstrap unified configs and permission files on startup
try:
    # moved under core.framework.config
    from .core.framework.config import bootstrap_configs

    @driver.on_startup
    async def _entertain_bootstrap_configs():
        try:
            bootstrap_configs()
        except Exception:
            pass
except Exception:
    pass


def _load_subplugins_via_nonebot() -> None:
    """Load sub-plugins using NoneBot's built-in loader.

    This scans the internal `plugins/` directory and loads any valid plugins,
    letting NoneBot handle registration rather than manual import.
    """
    try:
        base = Path(__file__).parent / "plugins"
        if base.exists():
            # NoneBot will handle recursive discovery of plugin packages in this path
            load_plugins(str(base))
    except Exception:
        # Avoid breaking plugin load on failure
        pass


_load_subplugins_via_nonebot()

# Initialize built-in framework features (non-subplugin)
try:
    # core (formerly membership) is part of the framework package
    from . import core as _core  # noqa: F401
except Exception:
    # Keep other plugins working even if this optional feature fails to init
    pass
