from typing import Optional

from pydantic import BaseModel, Extra


class Config(BaseModel, extra=Extra.ignore):
    """Configuration for nonebot-plugin-entertain.

    Use environment variables or .env to override, e.g.:
    - ENTERTAIN_ENABLE_REG_TIME=true/false
    - ENTERTAIN_ENABLE_DORO=true/false
    - ENTERTAIN_ENABLE_SICK=true/false
    - ENTERTAIN_ENABLE_MUSICSHARE=true/false
    - ENTERTAIN_ENABLE_FORTUNE=true/false
    - ENTERTAIN_ENABLE_BOX=true/false
    - ENTERTAIN_ENABLE_WELCOME=true/false
    - ENTERTAIN_ENABLE_TAFFY=true/false
    - ENTERTAIN_ENABLE_PANEL=true/false
    - ENTERTAIN_QQ_REG_TIME_API_KEY=xxxx
    - ENTERTAIN_PERM_DEFAULT=all|admin|superuser
    - ENTERTAIN_PERM_REG_TIME=all|admin|superuser
    - ENTERTAIN_PERM_DORO=all|admin|superuser
    - ENTERTAIN_PERM_SICK=all|admin|superuser
    - ENTERTAIN_PERM_MUSICSHARE=all|admin|superuser
    - ENTERTAIN_PERM_FORTUNE=all|admin|superuser
    - ENTERTAIN_PERM_BOX=all|admin|superuser
    - ENTERTAIN_PERM_WELCOME=all|admin|superuser
    """

    entertain_enable_reg_time: bool = True
    entertain_enable_doro: bool = True
    entertain_enable_sick: bool = True

    # Optional API key for QQ 注册时间查询; falls back to the one used in original JS
    entertain_qq_reg_time_api_key: Optional[str] = None

    # Also manage existing Python plugins
    entertain_enable_musicshare: bool = True
    entertain_enable_fortune: bool = True
    entertain_enable_box: bool = True
    entertain_enable_welcome: bool = True
    entertain_enable_taffy: bool = True
    entertain_enable_panel: bool = True

    # DF-Plugin integration toggle
    entertain_enable_df: bool = True

    # Permission control (external, centralized)
    # values: "all" (default), "admin" (group admin/owner), "superuser"
    entertain_perm_default: str = "all"
    entertain_perm_reg_time: Optional[str] = None
    entertain_perm_doro: Optional[str] = None
    entertain_perm_sick: Optional[str] = None
    entertain_perm_musicshare: Optional[str] = None
    entertain_perm_fortune: Optional[str] = None
    entertain_perm_box: Optional[str] = None
    entertain_perm_welcome: Optional[str] = "admin"
    # Default stricter permissions for write operations
    entertain_perm_welcome_set: str = "admin"
    entertain_perm_welcome_clear: str = "admin"
