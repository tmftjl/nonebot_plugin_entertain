from importlib import import_module

from nonebot import get_driver
from nonebot.plugin import PluginMetadata

from .config import Config


driver = get_driver()
global_config = driver.config
plugin_config = Config.parse_obj(global_config.dict())


__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-entertain",
    description=(
        "娱乐插件合集：注册时间查询、每日 doro 结局、发病语录、音乐点歌、今日运势、开盒"
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
    config=Config,
    supported_adapters={"~onebot.v11"},
)


def _conditional_import(module: str) -> None:
    try:
        # Use package-relative import so it works under plugin dirs
        import_module(module, __name__)
    except Exception as e:
        # Import errors should not crash whole bot; log via driver logger if available
        try:
            from nonebot import logger
            logger.opt(exception=e).error(f"Failed to import subplugin: {module}")
        except Exception:
            pass


# Conditionally register sub-plugins (converted from JS)
if plugin_config.entertain_enable_reg_time:
    _conditional_import(".plugins.reg_time")

if plugin_config.entertain_enable_doro:
    _conditional_import(".plugins.doro")

if plugin_config.entertain_enable_sick:
    _conditional_import(".plugins.sick")

# Conditionally register existing Python plugins (now unified under plugins/*)
if plugin_config.entertain_enable_musicshare:
    _conditional_import(".plugins.musicshare")

if plugin_config.entertain_enable_fortune:
    _conditional_import(".plugins.fortune")

if plugin_config.entertain_enable_box:
    _conditional_import(".plugins.box")

if plugin_config.entertain_enable_welcome:
    _conditional_import(".plugins.welcome")

if getattr(plugin_config, "entertain_enable_taffy", True):
    _conditional_import(".plugins.taffy")

if getattr(plugin_config, "entertain_enable_panel", True):
    _conditional_import(".plugins.panel")

# DF-Plugin (ported) integration
if getattr(plugin_config, "entertain_enable_df", True):
    _conditional_import(".plugins.df")
